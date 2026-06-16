#!/usr/bin/env bash
# IB 连通性测试公共配置

# 本机 (node-044)
# shellcheck disable=SC2034
LOCAL_IP="172.31.0.44"
# shellcheck disable=SC2034
LOCAL_HOST="bjdb-h20-node-044"

# 对端 (node-043)
# shellcheck disable=SC2034
PEER_IP="172.31.0.43"
# shellcheck disable=SC2034
PEER_HOST="bjdb-h20-node-043"

# IB 设备（Active 的 ConnectX-7，按需修改）
IB_DEV="${IB_DEV:-mlx5_0}"
IB_PORT="${IB_PORT:-1}"

# 测试参数
IBPING_COUNT="${IBPING_COUNT:-10}"
BW_DURATION="${BW_DURATION:-5}"

# 对端脚本部署路径（同步 peer/ 目录时使用）
PEER_DEPLOY_DIR="${PEER_DEPLOY_DIR:-/tmp/ib_test_peer}"
