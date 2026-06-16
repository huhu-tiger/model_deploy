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
  die "master 容器 ${CONTAINER_LLM} 未在 ${max_wait}s 内启动"
}

wait_dist_port() {
  local host port elapsed=0 last_log=0
  host="${MASTER_DIST_ADDR%%:*}"
  port="${MASTER_DIST_ADDR##*:}"
  log "等待 dist-init 端口 ${host}:${port}（最多 ${MASTER_DIST_WAIT_SEC}s，就绪后立即启动 worker）..."
  while (( elapsed < MASTER_DIST_WAIT_SEC )); do
    if port_is_listening "${host}" "${port}" || port_is_listening "127.0.0.1" "${port}"; then
      log "dist-init 端口已监听（${elapsed}s）→ 启动远程 worker"
      return 0
    fi
    if (( elapsed - last_log >= 15 )); then
      log "仍在等待 dist-init 端口... (${elapsed}s / ${MASTER_DIST_WAIT_SEC}s)"
      last_log=${elapsed}
    fi
    sleep "${MASTER_DIST_POLL_SEC}"
    elapsed=$((elapsed + MASTER_DIST_POLL_SEC))
  done
  die "超时：${MASTER_DIST_ADDR} 未就绪，请检查本机 sg-llm 日志: docker logs ${CONTAINER_LLM}"
}

# master 就绪后启动 worker（双节点必须尽快拉起 rank 1）
launch_worker_after_master() {
  wait_master_container
  wait_dist_port
  worker_up "${1:-}"
}

start_all() {
  ensure_env full
  worker_sync
  master_up
  launch_worker_after_master
  log "全部完成。查看日志: ./run logs"
}

restart_all() {
  log "======== 重启 MiniMax-M3 双节点 ========"
  ensure_env full

  log "[1/5] SSH 停止远程 worker (${REMOTE_HOST})..."
  worker_down 0

  log "[2/5] 停止本机 master..."
  master_down
  sleep 3

  log "[3/5] 重新拷贝 worker 启动文件到远程..."
  worker_sync

  log "[4/5] 启动本机 master..."
  master_up "--force-recreate"

  log "[5/5] 启动远程 worker..."
  launch_worker_after_master "--force-recreate"

  log "重启完成。查看日志: ./run logs"
}

stop_all() {
  worker_down 0
  master_down
}

show_status() {
  show_master_status
  show_worker_status
}
