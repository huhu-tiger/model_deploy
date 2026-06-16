#!/usr/bin/env bash
# 在本机 (172.31.0.44) 运行：向对端发起 IB 通信测试
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../common.sh
source "${ROOT}/common.sh"
load_config
IB_ROLE=LOCAL
run_preflight peer

print_banner "IB 通信测试（客户端）" "${LOCAL_IP}"
log_info "对端: ${PEER_HOST} (${PEER_IP})"
echo

get_peer_lid() {
  local lid
  if lid=$(ssh -o BatchMode=yes -o ConnectTimeout=5 "root@${PEER_IP}" \
    "cat /sys/class/infiniband/${IB_DEV}/ports/1/lid" 2>/dev/null); then
    echo "${lid}"
    return 0
  fi
  log_error "无法 SSH 获取对端 LID，请在对端查看:"
  log_info "  cat /sys/class/infiniband/${IB_DEV}/ports/1/lid"
  log_info "然后: PEER_LID=<LID> bash client.sh"
  return 1
}

PEER_LID="${PEER_LID:-$(get_peer_lid)}"
printf "${C_CYAN}  ▸ 对端 LID: %d (0x%x)${C_RESET}\n\n" "${PEER_LID}" "${PEER_LID}"

print_section "ibping 跨节点测试（对端须先运行 server）"
_ibping_ok=0
ibping -c "${IBPING_COUNT}" -C "${IB_DEV}" -P "${IB_PORT}" -L "${PEER_LID}" || _ibping_ok=$?
if [[ ${_ibping_ok} -ne 0 ]]; then
  log_warn "ibping 失败（exit ${_ibping_ok}），请确认对端已运行 run.sh start-peer"
else
  log_ok "ibping 通过"
fi

print_section "ib_write_bw 带宽测试"
if command -v ib_write_bw >/dev/null 2>&1; then
  ib_write_bw -d "${IB_DEV}" --duration="${BW_DURATION}" "${PEER_IP}"
  log_ok "带宽测试完成"
else
  log_warn "未安装 perftest，跳过带宽测试"
  log_info "安装: sudo apt install -y perftest"
fi

echo
log_ok "通信测试完成"
