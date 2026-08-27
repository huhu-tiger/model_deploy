#!/usr/bin/env bash
# 本机 master (node-43) 操作

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
# shellcheck source=check.sh
source "$(dirname "${BASH_SOURCE[0]}")/check.sh"

master_containers_exist() {
  container_exists_local "${CONTAINER_LLM}" || container_exists_local "${CONTAINER_NGINX}"
}

master_up() {
  local extra_flags="${1:-}"
  mkdir -p "${NODE43_DIR}/logs"
  log "启动本机 node-43: ${COMPOSE_FILE}"
  # shellcheck disable=SC2086
  compose -f "${COMPOSE_FILE}" up -d ${extra_flags}
  log "本机服务已提交启动（API: nginx 30001 / SGLang 30003 / distributed rendezvous ${MASTER_DIST_PORT}）"
}

master_down() {
  if ! master_containers_exist; then
    log "本机无相关容器，跳过停止"
    return 0
  fi
  log "停止本机 node-43..."
  compose -f "${COMPOSE_FILE}" down || die "本机 master 停止失败"
  master_containers_exist && die "本机相关容器停止后仍然存在"
  log "本机 master 已停止"
}

start_master() {
  ensure_env master
  master_up
}

show_master_status() {
  log "── 本机 node-43 ──"
  compose -f "${COMPOSE_FILE}" ps || true
}

show_master_logs() {
  local svc="${1:-${COMPOSE_LLM_SVC}}"
  compose -f "${COMPOSE_FILE}" logs -f "${svc}"
}
