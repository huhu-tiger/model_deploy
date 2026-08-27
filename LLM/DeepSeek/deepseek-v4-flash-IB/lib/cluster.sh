#!/usr/bin/env bash
# 双节点编排

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
# shellcheck source=check.sh
source "$(dirname "${BASH_SOURCE[0]}")/check.sh"
# shellcheck source=master.sh
source "$(dirname "${BASH_SOURCE[0]}")/master.sh"
# shellcheck source=worker.sh
source "$(dirname "${BASH_SOURCE[0]}")/worker.sh"

wait_master_container() {
  local max_wait=120 elapsed=0
  log "等待本机 master 容器 ${CONTAINER_LLM} 运行..."
  while (( elapsed < max_wait )); do
    if master_container_running; then
      log "master 容器已运行（${elapsed}s）"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  log "ERROR: master 容器 ${CONTAINER_LLM} 未在 ${max_wait}s 内启动" >&2
  return 1
}

wait_dist_port() {
  local host port elapsed=0 last_log=0
  host="${MASTER_DIST_ADDR%%:*}"
  port="${MASTER_DIST_ADDR##*:}"
  # TP8 + PP2 使用标准 torch.distributed rendezvous 端口；master 会在此阻塞等待 worker。
  log "等待 SGLang distributed rendezvous ${host}:${port}（最多 ${MASTER_DIST_WAIT_SEC}s，就绪后立即启动 worker）..."
  while (( elapsed < MASTER_DIST_WAIT_SEC )); do
    if port_is_listening "${host}" "${port}" || port_is_listening "127.0.0.1" "${port}"; then
      log "distributed rendezvous 端口已监听（${elapsed}s）→ 启动远程 worker"
      return 0
    fi
    if (( elapsed - last_log >= 15 )); then
      log "仍在等待 distributed rendezvous 端口... (${elapsed}s / ${MASTER_DIST_WAIT_SEC}s)"
      last_log=${elapsed}
    fi
    sleep "${MASTER_DIST_POLL_SEC}"
    elapsed=$((elapsed + MASTER_DIST_POLL_SEC))
  done
  log "ERROR: ${host}:${port} 未在 ${MASTER_DIST_WAIT_SEC}s 内就绪" >&2
  return 1
}

wait_worker_container() {
  local max_wait=120 elapsed=0
  log "等待远程 worker 容器 ${CONTAINER_LLM} 运行..."
  while (( elapsed < max_wait )); do
    if worker_container_running; then
      log "worker 容器已运行（${elapsed}s）"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  log "ERROR: worker 容器 ${CONTAINER_LLM} 未在 ${max_wait}s 内启动" >&2
  return 1
}

wait_cluster_ready() {
  local elapsed=0 last_log=0
  wait_worker_container || return 1
  log "等待双节点服务健康（最多 ${SERVICE_READY_WAIT_SEC}s）..."
  while (( elapsed < SERVICE_READY_WAIT_SEC )); do
    if ! master_container_running; then
      log "ERROR: master 容器已退出" >&2
      return 1
    fi
    if ! worker_container_running; then
      log "ERROR: worker 容器已退出" >&2
      return 1
    fi
    if curl -fsS --max-time 5 http://127.0.0.1:30003/health >/dev/null 2>&1; then
      log "双节点 SGLang 服务已健康（${elapsed}s）"
      return 0
    fi
    if (( elapsed - last_log >= 30 )); then
      log "模型仍在加载或初始化... (${elapsed}s / ${SERVICE_READY_WAIT_SEC}s)"
      last_log=${elapsed}
    fi
    sleep 5
    elapsed=$((elapsed + 5))
  done
  log "ERROR: SGLang /health 未在 ${SERVICE_READY_WAIT_SEC}s 内就绪" >&2
  return 1
}

cleanup_failed_start() {
  log "启动失败，清理双节点残留容器..."
  worker_down 0 || true
  master_down || true
}

launch_worker_after_master() {
  if ! wait_master_container || ! wait_dist_port; then
    cleanup_failed_start
    return 1
  fi
  if ! worker_up "${1:-}" || ! wait_cluster_ready; then
    cleanup_failed_start
    return 1
  fi
}

start_all() {
  ensure_env full
  worker_sync
  master_up
  launch_worker_after_master
  log "全部完成。查看日志: ./run.sh logs"
}

restart_all() {
  log "======== 重启 DeepSeek-V4-Flash 双节点 ========"
  ensure_env full

  log "[1/5] SSH 停止远程 worker (${REMOTE_HOST})..."
  worker_down 1

  log "[2/5] 停止本机 master..."
  master_down
  sleep 3

  log "[3/5] 重新拷贝 worker 启动文件到远程..."
  worker_sync

  log "[4/5] 启动本机 master..."
  master_up "--force-recreate"

  log "[5/5] 启动远程 worker..."
  launch_worker_after_master "--force-recreate"

  log "重启完成。查看日志: ./run.sh logs"
}

stop_all() {
  worker_down 1
  master_down
}

show_status() {
  show_master_status
  show_worker_status
}
