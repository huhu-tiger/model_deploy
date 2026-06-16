#!/usr/bin/env bash
# 在对端 (172.31.0.43) 运行：启动 IB 监听
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../common.sh" ]]; then
  # shellcheck source=../common.sh
  source "${SCRIPT_DIR}/../common.sh"
else
  # shellcheck source=common.sh
  source "${SCRIPT_DIR}/common.sh"
fi
load_config
IB_ROLE=PEER
run_preflight local

lid=$(get_lid "${IB_DEV}")
print_banner "IB 服务端监听" "${PEER_IP}"
log_info "IB 设备 : ${IB_DEV}  端口 : ${IB_PORT}"
log_info "本机 LID: $(printf '%d (0x%x)' "${lid}" "${lid}")"
log_info "等待本机 (${LOCAL_IP}) 发起测试 ... 按 Ctrl+C 停止"
echo

cleanup() {
  echo
  log_warn "停止所有监听..."
  jobs -p | xargs -r kill 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

print_section "启动监听"
log_info "[1] ibping 监听: ibping -S -C ${IB_DEV} -P ${IB_PORT}"
ibping -S -C "${IB_DEV}" -P "${IB_PORT}" &
IBPING_PID=$!

if command -v ib_write_bw >/dev/null 2>&1; then
  log_info "[2] ib_write_bw 监听: ib_write_bw -d ${IB_DEV}"
  ib_write_bw -d "${IB_DEV}" &
  BW_PID=$!
else
  log_warn "[2] 跳过 ib_write_bw（未安装 perftest，可执行: sudo apt install -y perftest）"
  BW_PID=""
fi

log_ok "监听中..."

if [[ -n "${BW_PID}" ]]; then
  wait "${IBPING_PID}" "${BW_PID}"
else
  wait "${IBPING_PID}"
fi
