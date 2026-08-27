#!/usr/bin/env bash
# 从 cluster.env 加载集群 IP（主机名运行时通过 hostname 命令获取）

load_cluster_env() {
  CLUSTER_ENV_FILE="${ROOT}/cluster.env"
  if [[ ! -f "${CLUSTER_ENV_FILE}" ]]; then
    echo "ERROR: 缺少 ${CLUSTER_ENV_FILE}，请执行: make init && 编辑 cluster.env" >&2
    exit 1
  fi
  set -a
  # shellcheck source=/dev/null
  source "${CLUSTER_ENV_FILE}"
  set +a

  [[ -n "${MASTER_IP:-}" ]] || { echo "ERROR: cluster.env 缺少 MASTER_IP" >&2; exit 1; }
  [[ -n "${WORKER_IP:-}" ]] || { echo "ERROR: cluster.env 缺少 WORKER_IP" >&2; exit 1; }

  MASTER_DIST_PORT="${MASTER_DIST_PORT:-29501}"
  REMOTE_USER="${REMOTE_USER:-root}"
  REMOTE_DEPLOY_DIR="${REMOTE_DEPLOY_DIR:-/tmp/minimax-m3-awq-IB/node-44}"

  LOCAL_IP="${MASTER_IP}"
  REMOTE_IP="${WORKER_IP}"
  REMOTE_HOST="${WORKER_IP}"
  MASTER_DIST_ADDR="${MASTER_IP}:${MASTER_DIST_PORT}"
}

load_cluster_env
