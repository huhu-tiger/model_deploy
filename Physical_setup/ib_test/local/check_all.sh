#!/usr/bin/env bash
# 在本机运行：自动 SSH 到对端，完成本机 + 对端 IB 检测
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../common.sh
source "${ROOT}/common.sh"
load_config
IB_ROLE=LOCAL

# 双端总览 banner
clr_main="${C_BLUE}"
sep='══════════════════════════════════════════════════════'
printf "\n${clr_main}${C_BOLD}%s${C_RESET}\n" "${sep}"
printf "${clr_main}${C_BOLD}  IB 双端检测${C_RESET}\n"
printf "${clr_main}  本机 : %-20s (%s)${C_RESET}\n" "${LOCAL_HOST}" "${LOCAL_IP}"
printf "${clr_main}  对端 : %-20s (%s)${C_RESET}\n" "${PEER_HOST}"  "${PEER_IP}"
printf "${clr_main}${C_BOLD}%s${C_RESET}\n\n" "${sep}"

# 1. 预检
run_preflight start-peer

# 2. 同步对端脚本
print_section "同步脚本到对端"
bash "${ROOT}/local/sync_peer.sh"

# 3. 本机 IB 检测
bash "${ROOT}/local/check.sh"

# 4. SSH 到对端执行检测
run_remote_check

# 5. RDMA 模式分析（IB vs RoCE）与 NCCL 推荐
run_rdma_mode_analysis

# 6. 汇总：卡数量、对应关系、RDMA 测试
run_summary

printf "${clr_main}${C_BOLD}%s${C_RESET}\n"  "${sep}"
printf "${clr_main}${C_BOLD}  双端检测完成${C_RESET}\n"
printf "${clr_main}${C_BOLD}%s${C_RESET}\n\n" "${sep}"
