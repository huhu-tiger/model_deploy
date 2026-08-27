#!/usr/bin/env bash
# DeepSeek-V4-Flash-vLLM 双节点入口（本机 master + 远程 worker）
# 必须在 master（cluster.env 的 MASTER_IP，默认 172.31.0.43）上执行
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/cluster.sh
source "${ROOT}/lib/cluster.sh"

usage() {
  cat <<EOF
DeepSeek-V4-Flash-vLLM 双节点部署（配置: cluster.env，推荐 make 入口）
必须在 master (${MASTER_IP}) 上执行。

用法:
  make restart          # 推荐：重启双节点
  ./run.sh restart      # 等价于 make restart
  ./run.sh start        # 启动双节点
  ./run.sh stop         # 停止双节点
  ./run.sh check        # 环境检测（含 hosts / ufw / IB / 镜像）
  ./run.sh hosts        # 仅配置 /etc/hosts
  ./run.sh firewall     # 仅配置 ufw 集群互通
  ./run.sh status       # 容器状态
  ./run.sh logs [svc]   # 本机日志（默认 deepseek-v4-flash-vllm）
  ./run.sh master       # 仅本机 master
  ./run.sh sync         # scp worker compose + cluster.env
  ./run.sh worker       # 仅远程 worker

首次部署:
  make init             # 复制 cluster.env.example → cluster.env
  编辑 cluster.env      # 填写 MASTER_IP / WORKER_IP
  两端准备镜像          # docker pull ${DOCKER_IMAGE}
  make config-check
  make restart

cluster.env 主要字段:
  MASTER_IP / WORKER_IP           双节点 IP（必填）
  MASTER_DIST_PORT                vLLM --master-port（默认 29501）
  REMOTE_USER / REMOTE_DEPLOY_DIR SSH 与远程 compose 目录

可选环境变量（可写在 cluster.env）:
  MASTER_DIST_WAIT_SEC  等待 master-port 秒数（默认 900）
  MODEL_HOST_PATH       模型路径
  DOCKER_IMAGE          vLLM 镜像
EOF
}

main() {
  local cmd="${1:-restart}"
  case "${cmd}" in
    start)        start_all ;;
    restart)      restart_all ;;
    stop|down)    stop_all ;;
    check)        preflight_check ;;
    hosts)        ensure_cluster_hosts ;;
    firewall)     ensure_cluster_firewall ;;
    status|ps)    ensure_env local; show_status ;;
    logs)         show_master_logs "${2:-${COMPOSE_LLM_SVC}}" ;;
    master)       start_master ;;
    sync)         sync_worker ;;
    worker)       start_worker ;;
    -h|--help|help) usage ;;
    *)
      usage
      die "未知命令: ${cmd}"
      ;;
  esac
}

main "$@"
