#!/usr/bin/env bash
# 本机入口 (172.31.0.44 / bjdb-h20-node-044)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${DIR}/.." && pwd)"

usage() {
  cat <<EOF
本机 IB 测试 (172.31.0.44)

用法:
  bash run.sh check          # 仅检查本机 IB 链路
  bash run.sh check-all      # 本机 + 自动 SSH 对端，完成双端检测（推荐）
  bash run.sh sync           # 同步脚本到对端 172.31.0.43
  bash run.sh start-peer     # 同步并在对端启动 IB 监听
  bash run.sh client         # 向对端发起 IB 测试

一键双端检测:
  bash run.sh check-all

跨节点 IB 通信测试:
  终端1: bash run.sh start-peer
  终端2: bash run.sh client

环境变量:
  IB_DEV=mlx5_0    指定 IB 设备
  PEER_LID=260     手动指定对端 LID
EOF
}

case "${1:-}" in
  check)
    bash "${DIR}/check.sh"
    ;;
  check-all)
    bash "${DIR}/check_all.sh"
    ;;
  sync)
    # shellcheck source=../common.sh
    source "${ROOT}/common.sh"
    load_config
    IB_ROLE=LOCAL
    run_preflight peer
    bash "${DIR}/sync_peer.sh"
    ;;
  start-peer)
    # shellcheck source=../common.sh
    source "${ROOT}/common.sh"
    load_config
    IB_ROLE=LOCAL
    run_preflight start-peer
    bash "${DIR}/sync_peer.sh"
    echo
    log_info "在对端 ${PEER_IP} 启动 IB 监听，按 Ctrl+C 停止..."
    ssh -t "root@${PEER_IP}" "IB_ROLE=PEER bash ${PEER_DEPLOY_DIR}/run.sh server"
    ;;
  client)
    bash "${DIR}/client.sh"
    ;;
  *)
    usage
    exit 1
    ;;
esac
