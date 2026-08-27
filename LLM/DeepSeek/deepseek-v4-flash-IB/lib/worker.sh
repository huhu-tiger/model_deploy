#!/usr/bin/env bash
# 远程 worker (node-44) 操作

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
# shellcheck source=check.sh
source "$(dirname "${BASH_SOURCE[0]}")/check.sh"

worker_sync() {
  log "同步 worker 配置 → ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DEPLOY_DIR}/"
  remote "mkdir -p '${REMOTE_DEPLOY_DIR}'"
  scp "${WORKER_COMPOSE}" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DEPLOY_DIR}/docker-compose.yml"
  scp "${CLUSTER_ENV_FILE}" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DEPLOY_DIR}/cluster.env"
  log "同步完成（docker-compose.yml + cluster.env）"
}

require_remote_compose_cmd() {
  [[ -n "${REMOTE_COMPOSE_CMD}" ]] \
    || die "REMOTE_COMPOSE_CMD 未初始化，请先执行 ensure_env remote / full"
}

worker_up() {
  local extra_flags="${1:-}"
  require_remote_compose_cmd
  log "SSH 远程启动 worker: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DEPLOY_DIR}"
  remote "cd '${REMOTE_DEPLOY_DIR}' && \
    WORKER_HOSTNAME=\$(hostname -s 2>/dev/null || hostname) && \
    export WORKER_HOSTNAME && \
    ${REMOTE_COMPOSE_CMD} --env-file cluster.env -f docker-compose.yml up -d ${extra_flags}"
  log "远程 worker 已提交启动"
}

worker_down() {
  local strict="${1:-0}"
  log "SSH ${REMOTE_USER}@${REMOTE_HOST} 检查并停止 worker..."
  local result=""
  if ! result="$(remote "
    if ! docker ps -a --format '{{.Names}}' | grep -qx '${CONTAINER_LLM}'; then
      echo SKIP
      exit 0
    fi
    if cd '${REMOTE_DEPLOY_DIR}' 2>/dev/null; then
      docker-compose --env-file cluster.env -f docker-compose.yml down 2>/dev/null || \
        docker compose --env-file cluster.env -f docker-compose.yml down 2>/dev/null || true
    fi
    if docker ps -a --format '{{.Names}}' | grep -qx '${CONTAINER_LLM}'; then
      if ! docker rm -f '${CONTAINER_LLM}' >/dev/null; then
        echo FAILED >&2
        exit 1
      fi
    fi
    REMAINING=\$(docker ps -a --format '{{.Names}}') || exit 1
    if printf '%s\n' \"\${REMAINING}\" | grep -qx '${CONTAINER_LLM}'; then
      echo FAILED >&2
      exit 1
    fi
    echo STOPPED
    exit 0
  " 2>/dev/null)"; then
    if [[ "${strict}" == "1" ]]; then
      die "远程 worker 停止失败或无法连接 ${REMOTE_HOST}"
    fi
    log "WARN: 远程 worker 停止失败，跳过（${REMOTE_HOST}）"
    return 0
  fi
  if [[ "${result}" == SKIP ]]; then
    log "远程无 ${CONTAINER_LLM} 容器，跳过停止"
  else
    log "远程 worker 已停止"
  fi
}

worker_container_running() {
  remote "docker ps --format '{{.Names}}' | grep -qx '${CONTAINER_LLM}'"
}

sync_worker() {
  ensure_env sync
  worker_sync
}

start_worker() {
  ensure_env remote_worker
  worker_up "${1:-}"
}

stop_worker() {
  worker_down "${1:-0}"
}

show_worker_status() {
  log "── 远程 node-44 (${REMOTE_HOST}) ──"
  remote "cd '${REMOTE_DEPLOY_DIR}' && \
    (docker-compose --env-file cluster.env -f docker-compose.yml ps 2>/dev/null \
      || docker compose --env-file cluster.env -f docker-compose.yml ps 2>/dev/null \
      || true)" || \
    log "WARN: 无法连接远程 ${REMOTE_HOST}"
}
