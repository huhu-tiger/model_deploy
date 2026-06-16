#!/usr/bin/env bash
# 在对端 (172.31.0.43) 运行：检查 IB 链路状态
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

print_banner "IB 链路检查" "${PEER_IP}"
echo

print_section "所有 IB 端口"
show_active_ports

print_section "${IB_DEV} 详情"
ibstat "${IB_DEV}"

print_section "RDMA 链路"
rdma link show 2>/dev/null || log_warn "rdma 命令不可用"

print_section "ibping 本机自测"
modprobe ib_umad 2>/dev/null || true
ibping -S -C "${IB_DEV}" -P "${IB_PORT}" &
_srv_pid=$!
sleep 1
_local_lid=$(get_lid "${IB_DEV}")
ibping -c 3 -C "${IB_DEV}" -P "${IB_PORT}" -L "${_local_lid}"
kill "${_srv_pid}" 2>/dev/null || true
wait "${_srv_pid}" 2>/dev/null || true

echo
lid=$(get_lid "${IB_DEV}")
log_info "本机 LID: $(printf '%d (0x%x)' "${lid}" "${lid}")"
log_ok "对端链路检查完成"
