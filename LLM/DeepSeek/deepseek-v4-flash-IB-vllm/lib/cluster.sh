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

check_dist_port_reachable() {
  # 仅事后提示，不阻塞：DP=2+TP=8+nnodes=2 时 master 的 EngineCore 要等
  # worker 侧的 DP 协调握手才会 bind master-port，反过来等 master-port
  # 就绪再启动 worker 会互相等死（两端都不会先动）。所以两端必须几乎
  # 同时启动，这里只做启动后的存活播报。
  local host port elapsed=0
  host="${MASTER_DIST_ADDR%%:*}"
  port="${MASTER_DIST_ADDR##*:}"
  log "已并行启动两端，等待 ${host}:${port} 就绪（最多 ${MASTER_DIST_WAIT_SEC}s，仅播报不阻塞下一步）..."
  while (( elapsed < MASTER_DIST_WAIT_SEC )); do
    if port_is_listening "${host}" "${port}" || port_is_listening "127.0.0.1" "${port}"; then
      log "master-port 已监听（${elapsed}s），两端应已开始 NCCL rendezvous"
      return 0
    fi
    sleep "${MASTER_DIST_POLL_SEC}"
    elapsed=$((elapsed + MASTER_DIST_POLL_SEC))
  done
  log "警告：${MASTER_DIST_ADDR} 在 ${MASTER_DIST_WAIT_SEC}s 内未监听，请检查两端日志: docker logs ${CONTAINER_LLM} / ssh ${REMOTE_HOST} docker logs ${CONTAINER_LLM}"
}

launch_worker_after_master() {
  wait_master_container
  # 不等 master-port：DP=2+TP=8+nnodes=2 下必须两端几乎同时起，
  # 否则 master 卡在等 worker 的 DP 握手，worker 又卡在等 master-port，死锁。
  worker_up "${1:-}"
  check_dist_port_reachable
}

start_all() {
  ensure_env full
  worker_sync
  master_up
  launch_worker_after_master
  log "全部完成。查看日志: ./run.sh logs"
}

restart_all() {
  log "======== 重启 DeepSeek-V4-Flash-vLLM 双节点 ========"
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

  log "重启完成。查看日志: ./run.sh logs"
}

stop_all() {
  worker_down 0
  master_down
}

show_status() {
  show_master_status
  show_worker_status
}
