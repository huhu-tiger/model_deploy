#!/usr/bin/env bash
# 对端入口 (172.31.0.43 / bjdb-h20-node-043)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"


usage() {
  cat <<EOF
对端 IB 测试 (172.31.0.43)

用法:
  bash run.sh check     # 检查对端 IB 链路
  bash run.sh server    # 启动 IB 监听（等待本机测试）

在本机 (172.31.0.44) 执行 client 前，需先在本脚本运行 server。

环境变量:
  IB_DEV=mlx5_0    指定 IB 设备
EOF
}

case "${1:-}" in
  check)   bash "${DIR}/check.sh" ;;
  server)  bash "${DIR}/server.sh" ;;
  *)       usage; exit 1 ;;
esac
