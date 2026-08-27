#!/usr/bin/env bash
# UFW：双节点集群 peer 间全端口入站互通（master-port / NCCL / Gloo 控制面）

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

UFW_CLUSTER_COMMENT="${UFW_CLUSTER_COMMENT:-minimax-m3-awq cluster peer}"

_ufw_rule_exists() {
  local peer_ip="$1"
  ufw status 2>/dev/null | grep -F "${peer_ip}" | grep -q ALLOW
}

ensure_local_firewall() {
  if ! command -v ufw &>/dev/null; then
    log "本机未安装 ufw，跳过防火墙配置"
    return 0
  fi
  if _ufw_rule_exists "${REMOTE_IP}"; then
    log "本机 ufw 已允许 ${REMOTE_IP} 入站（全端口）"
    return 0
  fi
  log "本机 ufw 允许 ${REMOTE_IP} 入站（全端口）..."
  ufw allow from "${REMOTE_IP}" comment "${UFW_CLUSTER_COMMENT}" \
    || die "本机 ufw 规则添加失败"
  _ufw_rule_exists "${REMOTE_IP}" || die "本机 ufw 规则写入后校验失败"
  log "本机 ufw 已就绪: allow from ${REMOTE_IP}"
}

ensure_remote_firewall() {
  log "检查远程 ufw ${REMOTE_HOST}..."
  if ! remote "command -v ufw >/dev/null 2>&1"; then
    log "远程未安装 ufw，跳过防火墙配置"
    return 0
  fi
  if ! remote "ufw status 2>/dev/null | head -1 | grep -q '^Status: active'"; then
    log "远程 ufw 未激活，跳过防火墙配置"
    return 0
  fi
  if remote "ufw status 2>/dev/null | grep -F '${LOCAL_IP}' | grep -q ALLOW"; then
    log "远程 ufw 已允许 ${LOCAL_IP} 入站（全端口）"
    return 0
  fi
  log "远程 ufw 已激活，允许 ${LOCAL_IP} 入站（全端口）..."
  remote "ufw allow from '${LOCAL_IP}' comment '${UFW_CLUSTER_COMMENT}'" \
    || die "远程 ufw 规则添加失败（${REMOTE_HOST}）"
  remote "ufw status 2>/dev/null | grep -F '${LOCAL_IP}' | grep -q ALLOW" \
    || die "远程 ufw 规则写入后校验失败（${REMOTE_HOST}）"
  log "远程 ufw 已就绪: allow from ${LOCAL_IP}"
}

ensure_cluster_firewall() {
  ensure_local_firewall
  check_remote_ssh
  ensure_remote_firewall
}
