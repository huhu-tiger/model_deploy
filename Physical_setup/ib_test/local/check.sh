#!/usr/bin/env bash
# 在本机 (172.31.0.44) 运行：检查 IB 链路状态
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../common.sh
source "${ROOT}/common.sh"
load_config
IB_ROLE=LOCAL
run_preflight local

print_banner "IB 链路检查" "${LOCAL_IP}"
log_info "对端: ${PEER_HOST} (${PEER_IP})"
echo

print_section "所有 IB 端口"
show_active_ports

print_section "${IB_DEV} 详情"
ibstat "${IB_DEV}"

print_section "RDMA 链路"
rdma link show | grep -E 'mlx5_' || rdma link show

print_section "ibping 本机自测"
ibping -S -C "${IB_DEV}" -P "${IB_PORT}" &
_srv_pid=$!
sleep 1
_local_lid=$(get_lid "${IB_DEV}")
ibping -c 3 -C "${IB_DEV}" -P "${IB_PORT}" -L "${_local_lid}"
kill "${_srv_pid}" 2>/dev/null || true
wait "${_srv_pid}" 2>/dev/null || true

print_section "对端管理网连通性"
if detect_ssh_peer; then
  log_ok "对端 SSH 可用，跨节点测试就绪"
else
  log_warn "${SSH_DETECT_MSG:-对端 SSH 不可用}，跨节点测试需先配置"
fi

echo
log_ok "本机链路检查完成"
