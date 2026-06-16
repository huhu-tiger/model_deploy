#!/usr/bin/env bash
# MiniMax-M3 双节点入口（本机 master + 远程 worker）
# 集群 IP / 主机名见 cluster.env（make init 创建）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/cluster.sh
source "${ROOT}/lib/cluster.sh"

usage() {
  cat <<EOF
MiniMax-M3 双节点部署（配置: cluster.env，推荐 make 入口）

用法:
  make restart          # 推荐：重启双节点
  ./run restart         # 等价于 make restart
  ./run start           # 启动双节点
  ./run stop            # 停止双节点
  ./run check           # 环境检测（含 hosts / ufw）
  ./run hosts           # 仅配置 /etc/hosts
  ./run firewall        # 仅配置 ufw 集群互通
  ./run status          # 容器状态
  ./run logs [svc]      # 本机日志（默认 sg-llm）
  ./run master          # 仅本机 master
  ./run sync            # scp worker compose + cluster.env
  ./run worker          # 仅远程 worker

首次部署:
  make init             # 复制 cluster.env.example → cluster.env
  编辑 cluster.env      # 填写 MASTER_IP / WORKER_IP
  make config-check     # 校验配置
  make restart

cluster.env 主要字段:
  MASTER_IP / WORKER_IP           双节点 IP（必填）
  MASTER_DIST_PORT                dist-init 端口（默认 20000）
  REMOTE_USER / REMOTE_DEPLOY_DIR SSH 与远程 compose 目录

主机名不在 cluster.env 配置；./run hosts / check 时通过
  hostname（本机）与 ssh worker hostname 获取，并写入 /etc/hosts。

可选环境变量（可写在 cluster.env）:
  MASTER_DIST_WAIT_SEC  等待 dist 端口秒数（默认 900）
  MODEL_HOST_PATH       模型路径
  DOCKER_IMAGE          SGLang 镜像

模块（lib/）:
  config.sh   加载 cluster.env
  common.sh   compose / ssh
  check.sh    ensure_env
  hosts.sh    /etc/hosts
  firewall.sh ufw
  cluster.sh  双节点编排
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
    logs)         show_master_logs "${2:-sg-llm}" ;;
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
