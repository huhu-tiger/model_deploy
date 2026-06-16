#!/usr/bin/env bash
# /etc/hosts 自动维护（双节点 NCCL / c10d 解析）

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# 仅删除双节点相关 IP 的旧行，保留 /etc/hosts 其余条目，再追加标准映射
_hosts_rewrite() {
  local hosts_file="$1"
  local lip="$2" lname="$3" rip="$4" rname="$5"
  local tmp="${hosts_file}.minimax-m3.$$"

  [[ -e "${hosts_file}" ]] || touch "${hosts_file}"
  [[ -w "${hosts_file}" ]] || die "${hosts_file} 不可写（需 root 权限）"

  awk -v lip="${lip}" -v rip="${rip}" '
    $1 == lip || $1 == rip { next }
    { print }
  ' "${hosts_file}" > "${tmp}"

  {
    printf '%s %s\n' "${lip}" "${lname}"
    printf '%s %s\n' "${rip}" "${rname}"
  } >> "${tmp}"

  cp "${tmp}" "${hosts_file}"
  rm -f "${tmp}"
}

_hosts_verify() {
  local hosts_file="$1" lip="$2" lname="$3" rip="$4" rname="$5"
  _hosts_has_mapping "${hosts_file}" "${lip}" "${lname}" \
    && _hosts_has_mapping "${hosts_file}" "${rip}" "${rname}"
}

_hosts_has_mapping() {
  local hosts_file="$1" ip="$2" name="$3"
  [[ -f "${hosts_file}" ]] || return 1
  awk -v ip="${ip}" -v name="${name}" '
    /^[[:space:]]*#/ { next }
    $1 == ip {
      for (i = 2; i <= NF; i++)
        if ($i == name) found = 1
    }
    END { exit(found ? 0 : 1) }
  ' "${hosts_file}"
}

ensure_local_hosts() {
  resolve_cluster_hostnames
  log "配置本机 /etc/hosts（hostname: 本机=$(local_hostname), worker=${REMOTE_HOSTNAME}）..."
  _hosts_rewrite "/etc/hosts" "${LOCAL_IP}" "${LOCAL_HOSTNAME}" "${REMOTE_IP}" "${REMOTE_HOSTNAME}"
  _hosts_verify "/etc/hosts" "${LOCAL_IP}" "${LOCAL_HOSTNAME}" "${REMOTE_IP}" "${REMOTE_HOSTNAME}" \
    || die "本机 /etc/hosts 写入后校验失败"
  log "本机 /etc/hosts 已就绪: ${LOCAL_IP} ${LOCAL_HOSTNAME}, ${REMOTE_IP} ${REMOTE_HOSTNAME}"
}

ensure_remote_hosts() {
  resolve_cluster_hostnames
  log "配置远程 /etc/hosts ${REMOTE_HOST}（hostname: master=${LOCAL_HOSTNAME}, worker=${REMOTE_HOSTNAME}）..."
  if ! remote "bash -s -- '${LOCAL_IP}' '${LOCAL_HOSTNAME}' '${REMOTE_IP}' '${REMOTE_HOSTNAME}'" <<'REMOTE_HOSTS_ENSURE_EOF'
set -euo pipefail
lip=$1 lname=$2 rip=$3 rname=$4
hosts_file=/etc/hosts
tmp="${hosts_file}.minimax-m3.$$"

[[ -e "$hosts_file" ]] || touch "$hosts_file"
[[ -w "$hosts_file" ]] || { echo "ERROR: $hosts_file not writable" >&2; exit 1; }

awk -v lip="$lip" -v rip="$rip" '
  $1 == lip || $1 == rip { next }
  { print }
' "$hosts_file" > "$tmp"

printf '%s %s\n' "$lip" "$lname" >> "$tmp"
printf '%s %s\n' "$rip" "$rname" >> "$tmp"
cp "$tmp" "$hosts_file"
rm -f "$tmp"

verify() {
  awk -v ip="$1" -v name="$2" '
    /^[[:space:]]*#/ { next }
    $1 == ip {
      for (i = 2; i <= NF; i++)
        if ($i == name) found = 1
    }
    END { exit(found ? 0 : 1) }
  ' "$hosts_file"
}
verify "$lip" "$lname"
verify "$rip" "$rname"
REMOTE_HOSTS_ENSURE_EOF
  then
    die "远程 /etc/hosts 配置失败（${REMOTE_HOST}，需 root SSH）"
  fi
  log "远程 /etc/hosts 已就绪: ${LOCAL_IP} ${LOCAL_HOSTNAME}, ${REMOTE_IP} ${REMOTE_HOSTNAME}"
}

ensure_cluster_hosts() {
  ensure_local_hosts
  check_remote_ssh
  ensure_remote_hosts
}
