#!/usr/bin/env bash
# 公共配置与基础工具

LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${LIB_DIR}/.." && pwd)"

# shellcheck source=config.sh
source "${LIB_DIR}/config.sh"

NODE44_DIR="${ROOT}/node-44"
NODE43_DIR="${ROOT}/node-43"
COMPOSE_FILE="${NODE44_DIR}/docker-compose.yml"
WORKER_COMPOSE="${NODE43_DIR}/docker-compose.yml"

REMOTE_DEPLOY_DIR="${REMOTE_DEPLOY_DIR:-${NODE43_DIR}}"

MASTER_DIST_WAIT_SEC="${MASTER_DIST_WAIT_SEC:-900}"
MASTER_DIST_POLL_SEC="${MASTER_DIST_POLL_SEC:-2}"

MODEL_HOST_PATH="${MODEL_HOST_PATH:-/media/llm/MiniMax/MiniMax-M3}"
DOCKER_IMAGE="${DOCKER_IMAGE:-model.vnet.com/sjhl/sglang:dev-minimax-m3}"

CONTAINER_LLM="${CONTAINER_LLM:-sg-minimax-m3}"
CONTAINER_NGINX="${CONTAINER_NGINX:-nginx-llm-proxy}"

REMOTE_COMPOSE_CMD=""

log() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

remote() {
  ssh -o BatchMode=yes -o ConnectTimeout=10 "${REMOTE_USER}@${REMOTE_HOST}" "$@"
}

# 本机主机名（短名优先）
local_hostname() {
  hostname -s 2>/dev/null || hostname
}

# SSH 获取 worker 主机名
fetch_remote_hostname() {
  remote "hostname -s 2>/dev/null || hostname"
}

# 本机 hostname → compose MASTER_HOSTNAME / LOCAL_HOSTNAME
resolve_local_hostnames() {
  LOCAL_HOSTNAME="$(local_hostname)"
  MASTER_HOSTNAME="${LOCAL_HOSTNAME}"
  export LOCAL_HOSTNAME MASTER_HOSTNAME
}

# 双节点 hostname（写 /etc/hosts 前调用，需 SSH 可达 worker）
resolve_cluster_hostnames() {
  resolve_local_hostnames
  REMOTE_HOSTNAME="$(fetch_remote_hostname)" \
    || die "无法获取 worker 主机名（${REMOTE_USER}@${REMOTE_HOST}）"
  WORKER_HOSTNAME="${REMOTE_HOSTNAME}"
  export REMOTE_HOSTNAME WORKER_HOSTNAME
}

compose() {
  command -v docker-compose &>/dev/null || die "未找到 docker-compose"
  resolve_local_hostnames
  docker-compose --env-file "${CLUSTER_ENV_FILE}" "$@"
}

container_exists_local() {
  docker ps -a --format '{{.Names}}' | grep -qx "$1"
}

# 检测 TCP 端口是否已监听（本机优先 ss，再 nc /dev/tcp）
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
