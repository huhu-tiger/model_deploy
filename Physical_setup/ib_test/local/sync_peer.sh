#!/usr/bin/env bash
# 在本机运行：将对端脚本同步到 172.31.0.43
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../common.sh
source "${ROOT}/common.sh"
load_config

IB_ROLE=LOCAL
PEER_DIR="${ROOT}/peer"

log_info "同步 peer/ → root@${PEER_IP}:${PEER_DEPLOY_DIR}"
ssh "root@${PEER_IP}" "mkdir -p ${PEER_DEPLOY_DIR}"
scp -r "${PEER_DIR}/." "root@${PEER_IP}:${PEER_DEPLOY_DIR}/"
scp "${ROOT}/config.sh" "${ROOT}/common.sh" "root@${PEER_IP}:${PEER_DEPLOY_DIR}/"
ssh "root@${PEER_IP}" "chmod +x ${PEER_DEPLOY_DIR}/*.sh"
log_ok "同步完成"
