#!/usr/bin/env bash

IB_APT_PACKAGES=(infiniband-diags ibutils rdmacm-utils)

# ---------------------------------------------------------------------------
# 颜色 / 输出系统
# ---------------------------------------------------------------------------

# IB_ROLE: LOCAL（本机）或 PEER（对端），各脚本在 load_config 后设置
IB_ROLE="${IB_ROLE:-LOCAL}"

# 终端支持颜色时（TTY 或强制开启）初始化颜色变量
_init_colors() {
  if [[ -t 1 ]] || [[ "${FORCE_COLOR:-0}" == "1" ]]; then
    C_RESET='\e[0m'
    C_BOLD='\e[1m'
    C_DIM='\e[2m'
    C_RED='\e[1;31m'
    C_GREEN='\e[1;32m'
    C_YELLOW='\e[1;33m'
    C_BLUE='\e[1;34m'
    C_CYAN='\e[1;36m'
    C_WHITE='\e[1;37m'
  else
    C_RESET='' C_BOLD='' C_DIM=''
    C_RED='' C_GREEN='' C_YELLOW=''
    C_BLUE='' C_CYAN='' C_WHITE=''
  fi
}
_init_colors

# 根据角色返回前景色：本机=青色，对端=黄色
_role_color() {
  [[ "${IB_ROLE}" == "PEER" ]] && printf '%s' "${C_YELLOW}" || printf '%s' "${C_CYAN}"
}

# 角色标签：本机 | 对端
_role_tag() {
  [[ "${IB_ROLE}" == "PEER" ]] && printf '对端' || printf '本机'
}

# 开头大 banner：显示角色、标题、主机名、IP
# 用法: print_banner "标题" "IP"
print_banner() {
  local title="$1"
  local ip="${2:-}"
  local tag; tag="$(_role_tag)"
  local clr; clr="$(_role_color)"
  local sep='══════════════════════════════════════════════════════'
  printf "\n${clr}${C_BOLD}%s${C_RESET}\n" "${sep}"
  printf "${clr}${C_BOLD}  【%s】%s${C_RESET}\n" "${tag}" "${title}"
  printf "${clr}  主机 : %s${C_RESET}\n" "$(hostname)"
  [[ -n "${ip}" ]] && printf "${clr}  IP   : %s${C_RESET}\n" "${ip}"
  printf "${clr}  设备 : %s${C_RESET}\n" "${IB_DEV}"
  printf "${clr}${C_BOLD}%s${C_RESET}\n\n" "${sep}"
}

# 分节标题：带角色前缀的彩色小标题
# 用法: print_section "标题"
print_section() {
  local title="$1"
  local tag; tag="$(_role_tag)"
  local clr; clr="$(_role_color)"
  printf "\n${clr}${C_BOLD}── [%s] %s ──${C_RESET}\n" "${tag}" "${title}"
}

# 日志辅助：成功 / 警告 / 错误 / 信息
log_ok()    { printf "${C_GREEN}  ✔ %s${C_RESET}\n" "$*"; }
log_warn()  { printf "${C_YELLOW}  ⚠ %s${C_RESET}\n" "$*"; }
log_error() { printf "${C_RED}  ✖ %s${C_RESET}\n" "$*"; }
log_info()  { local clr; clr="$(_role_color)"; printf "${clr}  ▸ %s${C_RESET}\n" "$*"; }

# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------

load_config() {
  local root
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  # shellcheck source=config.sh
  source "${root}/config.sh"
}

# ---------------------------------------------------------------------------
# apt 包检测 / 安装
# ---------------------------------------------------------------------------

_pkg_installed() {
  dpkg -s "$1" >/dev/null 2>&1
}

# 检测 apt 包是否已安装（仅检测，不安装）
# 用法: detect_apt_packages [标签]
# 返回: 0=已全部安装  1=有缺失（缺失包列表写入 APT_MISSING_PACKAGES 数组）
detect_apt_packages() {
  local label="${1:-本地}"
  APT_MISSING_PACKAGES=()
  local pkg

  for pkg in "${IB_APT_PACKAGES[@]}"; do
    _pkg_installed "${pkg}" || APT_MISSING_PACKAGES+=("${pkg}")
  done

  if [[ ${#APT_MISSING_PACKAGES[@]} -eq 0 ]]; then
    log_ok "${label} apt 包已安装: ${IB_APT_PACKAGES[*]}"
    return 0
  fi

  log_warn "${label} 缺少 apt 包: ${APT_MISSING_PACKAGES[*]}"
  return 1
}

# 检测并安装本地 apt 包
check_apt_packages() {
  if detect_apt_packages "本地"; then
    return 0
  fi
  log_info "执行: sudo apt install -y ${IB_APT_PACKAGES[*]}"
  sudo apt install -y "${IB_APT_PACKAGES[@]}"
  log_ok "本地 apt 包安装完成"
}

# 检测并安装对端 apt 包（需 SSH 可达）
check_apt_packages_remote() {
  local pkgs_str="${IB_APT_PACKAGES[*]}"
  log_info "检测对端 apt 包 ..."
  ssh -o BatchMode=yes -o ConnectTimeout=5 "root@${PEER_IP}" bash -s -- "${pkgs_str}" <<'REMOTE_EOF'
set -euo pipefail
read -r -a pkgs <<< "$1"
missing=()
for pkg in "${pkgs[@]}"; do
  dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if [[ ${#missing[@]} -eq 0 ]]; then
  printf "  \e[1;32m✔ 对端 apt 包已安装: %s\e[0m\n" "${pkgs[*]}"
  exit 0
fi
printf "  \e[1;33m⚠ 对端缺少 apt 包: %s\e[0m\n" "${missing[*]}"
printf "  \e[1;36m▸ 执行: sudo apt install -y %s\e[0m\n" "${pkgs[*]}"
sudo apt install -y "${pkgs[@]}"
printf "  \e[1;32m✔ 对端 apt 包安装完成\e[0m\n"
REMOTE_EOF
}

# ---------------------------------------------------------------------------
# SSH 检测
# ---------------------------------------------------------------------------

# 检测 SSH 到对端是否正常（仅检测，不退出）
# 返回: 0=正常  1=失败（详情写入 SSH_DETECT_MSG）
detect_ssh_peer() {
  SSH_DETECT_MSG=""

  if ! ping -c 2 -W 2 "${PEER_IP}" >/dev/null 2>&1; then
    SSH_DETECT_MSG="ping ${PEER_IP} 失败"
    log_warn "${SSH_DETECT_MSG}"
    return 1
  fi
  log_ok "ping ${PEER_IP} OK"

  local peer_host
  if ! peer_host=$(ssh -o BatchMode=yes -o ConnectTimeout=5 "root@${PEER_IP}" "hostname" 2>/dev/null); then
    SSH_DETECT_MSG="SSH root@${PEER_IP} 失败，请确认免密或密钥已配置"
    log_warn "${SSH_DETECT_MSG}"
    return 1
  fi

  log_ok "SSH root@${PEER_IP} OK  (${peer_host})"
  return 0
}

# 检测 SSH，失败则退出
check_ssh_peer() {
  detect_ssh_peer || {
    log_error "${SSH_DETECT_MSG:-SSH 检测失败}"
    exit 1
  }
}

# ---------------------------------------------------------------------------
# IB 环境初始化
# ---------------------------------------------------------------------------

_setup_ib_kernel() {
  modprobe ib_umad 2>/dev/null || true
  command -v ibstat >/dev/null 2>&1 || {
    log_error "ibstat 不可用，请确认 infiniband-diags 已正确安装"
    exit 1
  }
}

# ---------------------------------------------------------------------------
# 统一预检入口
# ---------------------------------------------------------------------------

# 用法: run_preflight <mode>
#   local       - 仅本机 apt + IB 内核模块 + 设备存在性
#   peer        - 以上 + SSH 连通性
#   start-peer  - 以上 + 对端 apt
run_preflight() {
  local mode="${1:-local}"
  local tag; tag="$(_role_tag)"
  local clr; clr="$(_role_color)"

  printf "\n${clr}${C_BOLD}── [%s] 预检 (%s) ──${C_RESET}\n" "${tag}" "${mode}"

  case "${mode}" in
    local)
      check_apt_packages
      _setup_ib_kernel
      check_ib_dev_exists
      ;;
    peer)
      check_apt_packages
      _setup_ib_kernel
      check_ib_dev_exists
      check_ssh_peer
      ;;
    start-peer)
      check_apt_packages
      _setup_ib_kernel
      check_ib_dev_exists
      check_ssh_peer
      check_apt_packages_remote
      ;;
    *)
      log_error "未知预检模式: ${mode}（可选: local / peer / start-peer）"
      exit 1
      ;;
  esac

  log_ok "预检通过"
  echo
}

# 兼容旧接口
preflight_local()       { run_preflight local; }
preflight_with_peer()   { run_preflight peer; }
preflight_start_peer()  { run_preflight start-peer; }
require_ib_tools()      { run_preflight local; }

# ---------------------------------------------------------------------------
# IB 工具函数
# ---------------------------------------------------------------------------

show_active_ports() {
  local ib_dir="/sys/class/infiniband"
  local dev state lid sm_lid rate layer mark mark_color
  local found=0

  for dev in "${ib_dir}"/*/; do
    [[ -d "${dev}" ]] || continue
    dev="$(basename "${dev}")"
    found=1

    state=$(cat "${ib_dir}/${dev}/ports/1/state"      2>/dev/null || echo "unknown")
    lid=$(cat   "${ib_dir}/${dev}/ports/1/lid"         2>/dev/null || echo "?")
    sm_lid=$(cat "${ib_dir}/${dev}/ports/1/sm_lid"     2>/dev/null || echo "?")
    rate=$(cat  "${ib_dir}/${dev}/ports/1/rate"        2>/dev/null || echo "?")
    layer=$(cat "${ib_dir}/${dev}/ports/1/link_layer"  2>/dev/null || echo "?")

    if [[ "${state}" == *"DOWN"* ]] || [[ "${state}" == *"Down"* ]]; then
      mark="*** DOWN ***"
      mark_color="${C_RED}"
    else
      mark=""
      mark_color="${C_GREEN}"
    fi

    printf "  ${mark_color}${C_BOLD}%-14s${C_RESET}" "${dev}"
    printf "  state=%-14s" "${state}"
    printf "  lid=%-6s  sm_lid=%-6s  rate=%s  [%s]" "${lid}" "${sm_lid}" "${rate}" "${layer}"
    [[ -n "${mark}" ]] && printf "  ${C_RED}${C_BOLD}%s${C_RESET}" "${mark}"
    printf "\n"
  done

  if [[ ${found} -eq 0 ]]; then
    log_warn "/sys/class/infiniband 下未发现任何 IB 设备"
  fi
}

# 检查 IB_DEV 对应的 IB 设备是否存在
check_ib_dev_exists() {
  if [[ ! -d "/sys/class/infiniband/${IB_DEV}" ]]; then
    log_error "IB 设备 ${IB_DEV} 不存在，请检查 IB_DEV 配置"
    local avail
    avail=$(find /sys/class/infiniband/ -maxdepth 1 -mindepth 1 -printf '%f ' 2>/dev/null || true)
    log_info "可用设备: ${avail:-（无）}"
    exit 1
  fi
}

get_lid() {
  local dev="${1:-${IB_DEV}}"
  cat "/sys/class/infiniband/${dev}/ports/1/lid"
}

# SSH 到对端执行 IB 检测（需先 sync_peer）
run_remote_check() {
  local clr="${C_YELLOW}"
  local sep='══════════════════════════════════════════════════════'
  printf "\n${clr}${C_BOLD}%s${C_RESET}\n" "${sep}"
  printf "${clr}${C_BOLD}  【对端】SSH 远程检测  →  %s${C_RESET}\n" "${PEER_IP}"
  printf "${clr}${C_BOLD}%s${C_RESET}\n\n" "${sep}"

  ssh -o BatchMode=yes -o ConnectTimeout=5 "root@${PEER_IP}" \
    "FORCE_COLOR=1 IB_ROLE=PEER bash ${PEER_DEPLOY_DIR}/run.sh check"
  echo
}

# ---------------------------------------------------------------------------
# RDMA 模式检测（原生 IB vs RoCE）
# ---------------------------------------------------------------------------

# 解析端口速率（Gb/sec），失败返回 0
_parse_rate_gbps() {
  local rate_raw="$1"
  echo "${rate_raw}" | awk '{gsub(/[^0-9.]/,"",$1); print $1+0}'
}

# 查找 RoCE v2 GID 索引（IPv4 映射优先），未找到返回空
_find_roce_v2_gid_index() {
  local dev="$1"
  local idx typ gid
  for idx in /sys/class/infiniband/"${dev}"/ports/1/gid_attrs/types/*; do
    [[ -f "${idx}" ]] || continue
    idx="$(basename "${idx}")"
    typ=$(cat "/sys/class/infiniband/${dev}/ports/1/gid_attrs/types/${idx}" 2>/dev/null || true)
    gid=$(cat "/sys/class/infiniband/${dev}/ports/1/gids/${idx}"             2>/dev/null || true)
    [[ "${gid}" == "0000:0000:0000:0000:0000:0000:0000:0000" ]] && continue
    [[ "${typ}" == *"RoCE v2"* ]] || continue
    if [[ "${gid}" == *":ffff:"* ]]; then
      echo "${idx}"
      return 0
    fi
  done
  for idx in /sys/class/infiniband/"${dev}"/ports/1/gid_attrs/types/*; do
    [[ -f "${idx}" ]] || continue
    idx="$(basename "${idx}")"
    typ=$(cat "/sys/class/infiniband/${dev}/ports/1/gid_attrs/types/${idx}" 2>/dev/null || true)
    [[ "${typ}" == *"RoCE v2"* ]] || continue
    echo "${idx}"
    return 0
  done
  return 1
}

# 收集本机全部 ACTIVE RDMA 端口 → _RDMA_DEVS _RDMA_LAYERS _RDMA_RATES _RDMA_LIDS _RDMA_GID_IDX
_collect_local_rdma_ports() {
  _RDMA_DEVS=(); _RDMA_LAYERS=(); _RDMA_RATES=(); _RDMA_LIDS=(); _RDMA_GID_IDX=()
  local dev state layer rate_raw rate lid gid_idx
  for dev in /sys/class/infiniband/*/; do
    [[ -d "${dev}" ]] || continue
    dev="$(basename "${dev}")"
    state=$(cat "/sys/class/infiniband/${dev}/ports/1/state"      2>/dev/null || echo "?")
    layer=$(cat "/sys/class/infiniband/${dev}/ports/1/link_layer" 2>/dev/null || echo "?")
    [[ "${state}" == *"ACTIVE"* ]] || continue
    rate_raw=$(cat "/sys/class/infiniband/${dev}/ports/1/rate" 2>/dev/null || echo "?")
    rate=$(_parse_rate_gbps "${rate_raw}")
    lid=$(cat "/sys/class/infiniband/${dev}/ports/1/lid" 2>/dev/null || echo "?")
    gid_idx=""
    if [[ "${layer}" == "Ethernet" ]]; then
      gid_idx=$(_find_roce_v2_gid_index "${dev}" 2>/dev/null || echo "?")
    else
      gid_idx="0"
    fi
    _RDMA_DEVS+=("${dev}")
    _RDMA_LAYERS+=("${layer}")
    _RDMA_RATES+=("${rate}")
    _RDMA_LIDS+=("${lid}")
    _RDMA_GID_IDX+=("${gid_idx}")
  done
}

# 通过 SSH 收集对端 ACTIVE RDMA 端口 → _PEER_RDMA_DEVS 等数组
_collect_peer_rdma_ports() {
  _PEER_RDMA_DEVS=(); _PEER_RDMA_LAYERS=(); _PEER_RDMA_RATES=(); _PEER_RDMA_LIDS=(); _PEER_RDMA_GID_IDX=()
  local raw
  raw=$(ssh -o BatchMode=yes -o ConnectTimeout=10 "root@${PEER_IP}" bash <<'REMOTE' 2>/dev/null || true
parse_rate() { echo "$1" | awk '{gsub(/[^0-9.]/,"",$1); print $1+0}'; }
find_roce_gid() {
  local dev="$1" idx typ gid
  for idx in /sys/class/infiniband/"${dev}"/ports/1/gid_attrs/types/*; do
    [[ -f "${idx}" ]] || continue
    idx="$(basename "${idx}")"
    typ=$(cat "/sys/class/infiniband/${dev}/ports/1/gid_attrs/types/${idx}" 2>/dev/null || true)
    gid=$(cat "/sys/class/infiniband/${dev}/ports/1/gids/${idx}" 2>/dev/null || true)
    [[ "${gid}" == "0000:0000:0000:0000:0000:0000:0000:0000" ]] && continue
    [[ "${typ}" == *"RoCE v2"* ]] || continue
    if [[ "${gid}" == *":ffff:"* ]]; then echo "${idx}"; return; fi
  done
  for idx in /sys/class/infiniband/"${dev}"/ports/1/gid_attrs/types/*; do
    [[ -f "${idx}" ]] || continue
    idx="$(basename "${idx}")"
    typ=$(cat "/sys/class/infiniband/${dev}/ports/1/gid_attrs/types/${idx}" 2>/dev/null || true)
    [[ "${typ}" == *"RoCE v2"* ]] || continue
    echo "${idx}"; return
  done
  echo "?"
}
for dev in /sys/class/infiniband/*/; do
  [[ -d "${dev}" ]] || continue
  dn="$(basename "${dev}")"
  st=$(cat "${dev}/ports/1/state" 2>/dev/null || echo "?")
  layer=$(cat "${dev}/ports/1/link_layer" 2>/dev/null || echo "?")
  [[ "${st}" == *"ACTIVE"* ]] || continue
  rate_raw=$(cat "${dev}/ports/1/rate" 2>/dev/null || echo "?")
  rate=$(parse_rate "${rate_raw}")
  lid=$(cat "${dev}/ports/1/lid" 2>/dev/null || echo "?")
  if [[ "${layer}" == "Ethernet" ]]; then
    gid_idx=$(find_roce_gid "${dn}")
  else
    gid_idx="0"
  fi
  printf '%s %s %s %s %s\n' "${dn}" "${layer}" "${rate}" "${lid}" "${gid_idx}"
done
REMOTE
)
  while IFS=' ' read -r pdev player prate plid pgid; do
    [[ -n "${pdev}" ]] || continue
    _PEER_RDMA_DEVS+=("${pdev}")
    _PEER_RDMA_LAYERS+=("${player}")
    _PEER_RDMA_RATES+=("${prate}")
    _PEER_RDMA_LIDS+=("${plid}")
    _PEER_RDMA_GID_IDX+=("${pgid}")
  done <<< "${raw}"
}

# 统计指定链路层的活跃端口数与总带宽（写入 RDMA_STAT_* 全局变量）
_rdma_layer_stats() {
  local layer="$1"
  shift
  local -a devs=("$@")
  local -a layers=()
  local -a rates=()
  local side="${1:-}"
  # 参数: layer dev1 layer1 rate1 dev2 layer2 rate2 ...
  # 简化：直接传入三个数组名前缀，改用索引遍历全局数组
  local i count=0 total=0 dev_list=""
  local -n _devs_ref="$2"
  local -n _layers_ref="$3"
  local -n _rates_ref="$4"
  for i in "${!_devs_ref[@]}"; do
    [[ "${_layers_ref[$i]}" == "${layer}" ]] || continue
    count=$(( count + 1 ))
    total=$(awk "BEGIN {printf \"%.0f\", ${total} + ${_rates_ref[$i]}}")
    dev_list="${dev_list:+$dev_list,}${_devs_ref[$i]}"
  done
  RDMA_STAT_COUNT="${count}"
  RDMA_STAT_TOTAL_GBPS="${total}"
  RDMA_STAT_DEV_LIST="${dev_list}"
}

# 输出 RDMA 模式分析与 NCCL 推荐配置
run_rdma_mode_analysis() {
  print_section "RDMA 链路模式 (IB vs RoCE)"
  _collect_local_rdma_ports
  _collect_peer_rdma_ports

  local side i
  for side in "本机" "对端"; do
    if [[ "${side}" == "本机" ]]; then
      local clr="${C_CYAN}"
      _rdma_layer_stats "InfiniBand" x _RDMA_DEVS _RDMA_LAYERS _RDMA_RATES
    else
      local clr="${C_YELLOW}"
      _rdma_layer_stats "InfiniBand" x _PEER_RDMA_DEVS _PEER_RDMA_LAYERS _PEER_RDMA_RATES
    fi
    local ib_n="${RDMA_STAT_COUNT}" ib_bw="${RDMA_STAT_TOTAL_GBPS}" ib_devs="${RDMA_STAT_DEV_LIST}"

    if [[ "${side}" == "本机" ]]; then
      _rdma_layer_stats "Ethernet" x _RDMA_DEVS _RDMA_LAYERS _RDMA_RATES
    else
      _rdma_layer_stats "Ethernet" x _PEER_RDMA_DEVS _PEER_RDMA_LAYERS _PEER_RDMA_RATES
    fi
    local roce_n="${RDMA_STAT_COUNT}" roce_bw="${RDMA_STAT_TOTAL_GBPS}" roce_devs="${RDMA_STAT_DEV_LIST}"

    printf "\n${clr}${C_BOLD}  %s:${C_RESET}\n" "${side}"
    if [[ "${ib_n}" -gt 0 ]]; then
      log_ok "${side} 原生 IB: ${ib_n} 张, 合计 ~${ib_bw} Gbps, 设备=${ib_devs}"
    else
      log_warn "${side} 未发现活跃原生 IB 端口"
    fi
    if [[ "${roce_n}" -gt 0 ]]; then
      log_info "${side} RoCE: ${roce_n} 张, 合计 ~${roce_bw} Gbps, 设备=${roce_devs}"
      if [[ "${side}" == "本机" ]]; then
        for i in "${!_RDMA_DEVS[@]}"; do
          [[ "${_RDMA_LAYERS[$i]}" == "Ethernet" ]] || continue
          printf "${clr}      %-14s  RoCE v2 GID index=%s${C_RESET}\n" \
            "${_RDMA_DEVS[$i]}" "${_RDMA_GID_IDX[$i]}"
        done
      else
        for i in "${!_PEER_RDMA_DEVS[@]}"; do
          [[ "${_PEER_RDMA_LAYERS[$i]}" == "Ethernet" ]] || continue
          printf "${clr}      %-14s  RoCE v2 GID index=%s${C_RESET}\n" \
            "${_PEER_RDMA_DEVS[$i]}" "${_PEER_RDMA_GID_IDX[$i]}"
        done
      fi
    else
      log_info "${side} 未发现活跃 RoCE 端口"
    fi
  done

  # 重新用本机数据做推荐
  _rdma_layer_stats "InfiniBand" x _RDMA_DEVS _RDMA_LAYERS _RDMA_RATES
  local rec_ib_n="${RDMA_STAT_COUNT}" rec_ib_bw="${RDMA_STAT_TOTAL_GBPS}" rec_ib_devs="${RDMA_STAT_DEV_LIST}"
  _rdma_layer_stats "Ethernet" x _RDMA_DEVS _RDMA_LAYERS _RDMA_RATES
  local rec_roce_n="${RDMA_STAT_COUNT}" rec_roce_bw="${RDMA_STAT_TOTAL_GBPS}" rec_roce_devs="${RDMA_STAT_DEV_LIST}"

  printf "\n${C_BOLD}  性能建议:${C_RESET}\n"
  if [[ "${rec_ib_n}" -gt 0 ]] && [[ "${rec_roce_n}" -gt 0 ]]; then
    if awk "BEGIN {exit !(${rec_ib_bw} > ${rec_roce_bw})}"; then
      log_ok "推荐使用原生 InfiniBand（~${rec_ib_bw} Gbps），优于 RoCE（~${rec_roce_bw} Gbps）"
      log_warn "切换 RoCE 不会提升性能，带宽仅为 IB 的 $(awk "BEGIN {printf \"%.1f\", (${rec_roce_bw}/${rec_ib_bw})*100}")%"
      RECOMMENDED_RDMA_MODE="ib"
      RECOMMENDED_NCCL_IB_HCA="${rec_ib_devs}"
      RECOMMENDED_NCCL_IB_GID_INDEX="0"
    elif awk "BEGIN {exit !(${rec_roce_bw} > ${rec_ib_bw})}"; then
      log_ok "推荐使用 RoCE（~${rec_roce_bw} Gbps），优于当前 IB（~${rec_ib_bw} Gbps）"
      RECOMMENDED_RDMA_MODE="roce"
      RECOMMENDED_NCCL_IB_HCA="${rec_roce_devs}"
      for i in "${!_RDMA_DEVS[@]}"; do
        [[ "${_RDMA_LAYERS[$i]}" == "Ethernet" ]] || continue
        RECOMMENDED_NCCL_IB_GID_INDEX="${_RDMA_GID_IDX[$i]}"
        break
      done
    else
      log_info "IB 与 RoCE 带宽接近，优先使用原生 IB（延迟更低）"
      RECOMMENDED_RDMA_MODE="ib"
      RECOMMENDED_NCCL_IB_HCA="${rec_ib_devs}"
      RECOMMENDED_NCCL_IB_GID_INDEX="0"
    fi
  elif [[ "${rec_ib_n}" -gt 0 ]]; then
    log_ok "仅检测到原生 IB（~${rec_ib_bw} Gbps），应使用 InfiniBand RDMA"
    RECOMMENDED_RDMA_MODE="ib"
    RECOMMENDED_NCCL_IB_HCA="${rec_ib_devs}"
    RECOMMENDED_NCCL_IB_GID_INDEX="0"
  elif [[ "${rec_roce_n}" -gt 0 ]]; then
    log_ok "仅检测到 RoCE（~${rec_roce_bw} Gbps），应使用 RoCE RDMA"
    RECOMMENDED_RDMA_MODE="roce"
    RECOMMENDED_NCCL_IB_HCA="${rec_roce_devs}"
    for i in "${!_RDMA_DEVS[@]}"; do
      [[ "${_RDMA_LAYERS[$i]}" == "Ethernet" ]] || continue
      RECOMMENDED_NCCL_IB_GID_INDEX="${_RDMA_GID_IDX[$i]}"
      break
    done
  else
    log_warn "未检测到可用 RDMA 端口"
    RECOMMENDED_RDMA_MODE="none"
    RECOMMENDED_NCCL_IB_HCA=""
    RECOMMENDED_NCCL_IB_GID_INDEX="0"
  fi

  RECOMMENDED_NCCL_IB_GID_INDEX="${RECOMMENDED_NCCL_IB_GID_INDEX:-0}"
  RECOMMENDED_NCCL_IB_HCA="${RECOMMENDED_NCCL_IB_HCA:-mlx5_0,mlx5_3,mlx5_4,mlx5_7}"

  printf "\n${C_BOLD}  NCCL 推荐配置 (模型启动):${C_RESET}\n"
  printf "    NCCL_IB_DISABLE=0\n"
  printf "    NCCL_IB_HCA=${RECOMMENDED_NCCL_IB_HCA}\n"
  printf "    NCCL_IB_GID_INDEX=${RECOMMENDED_NCCL_IB_GID_INDEX}\n"
  printf "    NCCL_SOCKET_IFNAME=bond0\n"
  if [[ "${RECOMMENDED_RDMA_MODE}" == "ib" ]]; then
    log_info "模式: 原生 InfiniBand RDMA（非 RoCE）"
  elif [[ "${RECOMMENDED_RDMA_MODE}" == "roce" ]]; then
    log_info "模式: RoCE v2 over Ethernet"
  fi
  echo
}

# ---------------------------------------------------------------------------
# 汇总：本机 vs 对端活跃 IB 卡数量、对应关系、RDMA 测试
# ---------------------------------------------------------------------------

# 收集本地活跃 IB 设备，结果写入全局数组 _IB_DEVS _IB_LIDS _IB_RATES
_collect_local_ib() {
  _IB_DEVS=(); _IB_LIDS=(); _IB_RATES=()
  local dev state lid rate layer
  for dev in /sys/class/infiniband/*/; do
    [[ -d "${dev}" ]] || continue
    dev="$(basename "${dev}")"
    state=$(cat "/sys/class/infiniband/${dev}/ports/1/state"      2>/dev/null || echo "?")
    layer=$(cat "/sys/class/infiniband/${dev}/ports/1/link_layer" 2>/dev/null || echo "?")
    [[ "${state}" == *"ACTIVE"* ]] && [[ "${layer}" == "InfiniBand" ]] || continue
    lid=$(cat  "/sys/class/infiniband/${dev}/ports/1/lid"  2>/dev/null || echo "?")
    rate=$(cat "/sys/class/infiniband/${dev}/ports/1/rate" 2>/dev/null | awk '{print $1}' || echo "?")
    _IB_DEVS+=("${dev}"); _IB_LIDS+=("${lid}"); _IB_RATES+=("${rate}")
  done
}

# 通过 SSH 收集对端活跃 IB 设备，写入 _PEER_DEVS _PEER_LIDS _PEER_RATES
_collect_peer_ib() {
  _PEER_DEVS=(); _PEER_LIDS=(); _PEER_RATES=()
  local raw
  raw=$(ssh -o BatchMode=yes -o ConnectTimeout=10 "root@${PEER_IP}" bash <<'REMOTE' 2>/dev/null || true
for dev in /sys/class/infiniband/*/; do
  [[ -d "${dev}" ]] || continue
  dn="$(basename "${dev}")"
  st=$(cat "${dev}/ports/1/state"      2>/dev/null || echo "?")
  layer=$(cat "${dev}/ports/1/link_layer" 2>/dev/null || echo "?")
  [[ "${st}" == *"ACTIVE"* ]] && [[ "${layer}" == "InfiniBand" ]] || continue
  lid=$(cat "${dev}/ports/1/lid"  2>/dev/null || echo "?")
  rate=$(cat "${dev}/ports/1/rate" 2>/dev/null | awk '{print $1}' || echo "?")
  printf '%s %s %s\n' "${dn}" "${lid}" "${rate}"
done
REMOTE
)
  while IFS=' ' read -r pdev plid prate; do
    [[ -n "${pdev}" ]] || continue
    _PEER_DEVS+=("${pdev}"); _PEER_LIDS+=("${plid}"); _PEER_RATES+=("${prate}")
  done <<< "${raw}"
}

# 在对端后台启动全部活跃 IB 设备的 ibping 服务端，返回 PID 列表（空格分隔）
_start_peer_ibping() {
  ssh -o BatchMode=yes -o ConnectTimeout=10 "root@${PEER_IP}" bash <<'REMOTE' 2>/dev/null || true
modprobe ib_umad 2>/dev/null || true
pids=()
for dev in /sys/class/infiniband/*/; do
  [[ -d "${dev}" ]] || continue
  dn="$(basename "${dev}")"
  st=$(cat "${dev}/ports/1/state" 2>/dev/null || echo "?")
  layer=$(cat "${dev}/ports/1/link_layer" 2>/dev/null || echo "?")
  [[ "${st}" == *"ACTIVE"* ]] && [[ "${layer}" == "InfiniBand" ]] || continue
  ibping -S -C "${dn}" -P 1 &>/tmp/"ibping_${dn}.log" &
  pids+=("$!")
done
echo "${pids[*]}"
REMOTE
}

# 停止对端 ibping 进程
_stop_peer_ibping() {
  local pids="$1"
  [[ -z "${pids}" ]] && return
  ssh -o BatchMode=yes -o ConnectTimeout=5 "root@${PEER_IP}" \
    "kill ${pids} 2>/dev/null; true" &>/dev/null || true
}

# 主汇总函数：在 check_all.sh 末尾调用
run_summary() {
  local sep='══════════════════════════════════════════════════════'
  printf "\n${C_WHITE}${C_BOLD}%s${C_RESET}\n"      "${sep}"
  printf "${C_WHITE}${C_BOLD}  IB 连通性汇总${C_RESET}\n"
  printf "${C_WHITE}${C_BOLD}%s${C_RESET}\n\n"      "${sep}"

  # ── 收集两端设备信息 ───────────────────────────────
  log_info "正在收集两端 IB 设备信息..."
  _collect_local_ib
  _collect_peer_ib

  local n_local="${#_IB_DEVS[@]}"
  local n_peer="${#_PEER_DEVS[@]}"

  # ── 本机活跃卡 ────────────────────────────────────
  printf "\n${C_CYAN}${C_BOLD}  本机活跃 IB 卡: %d 张${C_RESET}\n" "${n_local}"
  for i in "${!_IB_DEVS[@]}"; do
    local lid_dec; lid_dec=$(printf '%d' "${_IB_LIDS[$i]}")
    printf "${C_CYAN}    %-14s LID=%-5d  %s Gbps${C_RESET}\n" \
      "${_IB_DEVS[$i]}" "${lid_dec}" "${_IB_RATES[$i]}"
  done

  # ── 对端活跃卡 ────────────────────────────────────
  printf "\n${C_YELLOW}${C_BOLD}  对端活跃 IB 卡: %d 张${C_RESET}\n" "${n_peer}"
  for i in "${!_PEER_DEVS[@]}"; do
    local plid_dec; plid_dec=$(printf '%d' "${_PEER_LIDS[$i]}")
    printf "${C_YELLOW}    %-14s LID=%-5d  %s Gbps${C_RESET}\n" \
      "${_PEER_DEVS[$i]}" "${plid_dec}" "${_PEER_RATES[$i]}"
  done

  # ── 对应关系 ──────────────────────────────────────
  printf "\n${C_BOLD}  设备对应关系 (按设备名匹配):${C_RESET}\n"
  local min_n; min_n=$(( n_local < n_peer ? n_local : n_peer ))

  if [[ "${n_local}" -ne "${n_peer}" ]]; then
    log_warn "两端活跃 IB 卡数量不一致: 本机 ${n_local} 张 vs 对端 ${n_peer} 张"
  fi

  for (( i=0; i<min_n; i++ )); do
    local l_lid_d; l_lid_d=$(printf '%d' "${_IB_LIDS[$i]}")
    local p_lid_d; p_lid_d=$(printf '%d' "${_PEER_LIDS[$i]}")
    printf "    ${C_CYAN}%-12s (LID=%4d)${C_RESET}  ↔  ${C_YELLOW}%-12s (LID=%4d)${C_RESET}\n" \
      "${_IB_DEVS[$i]}" "${l_lid_d}" "${_PEER_DEVS[$i]}" "${p_lid_d}"
  done

  # ── RDMA 跨节点 ibping 测试 ───────────────────────
  printf "\n${C_BOLD}  RDMA 跨节点 ibping 测试:${C_RESET}\n"
  log_info "在对端启动 ibping 服务端..."

  local peer_pids
  peer_pids=$(_start_peer_ibping)
  sleep 1

  local rdma_pass=0 rdma_fail=0
  for (( i=0; i<min_n; i++ )); do
    local l_dev="${_IB_DEVS[$i]}"
    local p_lid_d; p_lid_d=$(printf '%d' "${_PEER_LIDS[$i]}")
    local p_dev="${_PEER_DEVS[$i]}"
    local ibping_out
    ibping_out=$(ibping -c 5 -C "${l_dev}" -P 1 -L "${p_lid_d}" 2>&1 || true)

    if echo "${ibping_out}" | grep -q "0% packet loss"; then
      printf "${C_GREEN}  ✔ ${C_CYAN}%s${C_RESET}${C_GREEN} → ${C_YELLOW}%s (LID=%d)${C_GREEN}  ✔ 0%% 丢包，RDMA 正常${C_RESET}\n" \
        "${l_dev}" "${p_dev}" "${p_lid_d}"
      rdma_pass=$(( rdma_pass + 1 ))
    else
      local loss; loss=$(echo "${ibping_out}" | grep -oE '[0-9]+% packet loss' || echo "无响应")
      log_warn "${l_dev} → ${p_dev} (LID=${p_lid_d})  ✖ ${loss}"
      rdma_fail=$(( rdma_fail + 1 ))
    fi
  done

  _stop_peer_ibping "${peer_pids}"

  # ── 总体结论 ──────────────────────────────────────
  printf "\n${C_BOLD}  总体结论:${C_RESET}\n"

  local card_ok=false rdma_ok=false
  [[ "${n_local}" -gt 0 ]] && [[ "${n_local}" -eq "${n_peer}" ]] && card_ok=true
  [[ "${rdma_fail}" -eq 0 ]] && [[ "${rdma_pass}" -gt 0 ]] && rdma_ok=true

  if ${card_ok}; then
    log_ok "IB 卡对应: 本机 ${n_local} 张 ↔ 对端 ${n_peer} 张，数量一致"
  else
    log_warn "IB 卡对应: 本机 ${n_local} 张 vs 对端 ${n_peer} 张，数量不一致"
  fi

  if ${rdma_ok}; then
    log_ok "RDMA 通信: ${rdma_pass}/${min_n} 路径全部正常"
  elif [[ "${rdma_pass}" -gt 0 ]]; then
    log_warn "RDMA 通信: ${rdma_pass} 正常 / ${rdma_fail} 失败，请检查失败路径"
  else
    log_warn "RDMA 通信: 全部失败，请先运行 'bash run.sh start-peer' 再测试"
  fi

  printf "\n${C_WHITE}${C_BOLD}%s${C_RESET}\n\n" "${sep}"
}
