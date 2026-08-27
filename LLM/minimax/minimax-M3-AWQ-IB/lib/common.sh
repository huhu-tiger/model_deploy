#!/usr/bin/env bash
# 公共配置与基础工具

LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${LIB_DIR}/.." && pwd)"

# shellcheck source=config.sh
source "${LIB_DIR}/config.sh"

NODE43_DIR="${ROOT}/node-43"
NODE44_DIR="${ROOT}/node-44"
COMPOSE_FILE="${NODE43_DIR}/docker-compose.yml"
WORKER_COMPOSE="${NODE44_DIR}/docker-compose.yml"
PARSER_FILE="${ROOT}/minimax_m3_reasoning_parser.py"

REMOTE_DEPLOY_DIR="${REMOTE_DEPLOY_DIR:-${NODE44_DIR}}"

MASTER_DIST_WAIT_SEC="${MASTER_DIST_WAIT_SEC:-900}"
MASTER_DIST_POLL_SEC="${MASTER_DIST_POLL_SEC:-2}"

MODEL_HOST_PATH="${MODEL_HOST_PATH:-/media/llm/cyankiwi/MiniMax-M3-AWQ-INT4}"
DOCKER_IMAGE="${DOCKER_IMAGE:-model.vnet.com/sjhl/vllm-openai:minimax-m3-awq}"

CONTAINER_LLM="${CONTAINER_LLM:-MiniMax-M3-AWQ-INT4-vLLM}"
CONTAINER_NGINX="${CONTAINER_NGINX:-nginx-minimax-m3-proxy}"
COMPOSE_LLM_SVC="${COMPOSE_LLM_SVC:-minimax-m3-awq-int4-vllm}"

REMOTE_COMPOSE_CMD=""
LOCAL_COMPOSE_CMD=""

log() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

remote() {
  ssh -o BatchMode=yes -o ConnectTimeout=10 "${REMOTE_USER}@${REMOTE_HOST}" "$@"
}

local_hostname() {
  hostname -s 2>/dev/null || hostname
}

fetch_remote_hostname() {
  remote "hostname -s 2>/dev/null || hostname"
}

resolve_local_hostnames() {
  LOCAL_HOSTNAME="$(local_hostname)"
  MASTER_HOSTNAME="${LOCAL_HOSTNAME}"
  export LOCAL_HOSTNAME MASTER_HOSTNAME
}

resolve_cluster_hostnames() {
  resolve_local_hostnames
  REMOTE_HOSTNAME="$(fetch_remote_hostname)" \
    || die "无法获取 worker 主机名（${REMOTE_USER}@${REMOTE_HOST}）"
  WORKER_HOSTNAME="${REMOTE_HOSTNAME}"
  export REMOTE_HOSTNAME WORKER_HOSTNAME
}

detect_compose_cmd() {
  if command -v docker-compose &>/dev/null; then
    printf '%s' "docker-compose"
  elif docker compose version &>/dev/null; then
    printf '%s' "docker compose"
  else
    return 1
  fi
}

compose() {
  if [[ -z "${LOCAL_COMPOSE_CMD}" ]]; then
    LOCAL_COMPOSE_CMD="$(detect_compose_cmd)" \
      || die "未找到 docker-compose / docker compose"
  fi
  resolve_local_hostnames
  : "${WORKER_HOSTNAME:=${LOCAL_HOSTNAME}}"
  export WORKER_HOSTNAME
  # shellcheck disable=SC2086
  ${LOCAL_COMPOSE_CMD} --env-file "${CLUSTER_ENV_FILE}" "$@"
}

container_exists_local() {
  docker ps -a --format '{{.Names}}' | grep -qx "$1"
}

port_is_listening() {
  local host="$1" port="$2"
  if ss -tlnH "sport = :${port}" 2>/dev/null | grep -q .; then
    return 0
  fi
  if command -v nc &>/dev/null && nc -z -w 2 "${host}" "${port}" 2>/dev/null; then
    return 0
  fi
  if (echo >/dev/tcp/"${host}"/"${port}") 2>/dev/null; then
    return 0
  fi
  return 1
}

master_container_running() {
  docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_LLM}"
}

local_has_ip() {
  ip -4 addr show | grep -Eq "inet ${MASTER_IP}/"
}
