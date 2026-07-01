#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/defaults.env"

# -----------------------------
# 配置变量（可通过环境变量覆盖，见 Makefile / ufw.sh help）
# -----------------------------
if [[ -z "${TARGET_PORTS+x}" ]]; then
    TARGET_PORTS="$UFW_DEFAULT_TARGET_PORTS"
fi
# 支持逗号分隔，与 WHITELIST_IPS 一致
TARGET_PORTS="${TARGET_PORTS//,/ }"

# 未设置 WHITELIST_IPS 时用默认值；显式传空字符串视为空（enable 时会报错退出）
parse_list_env() {
    # 将 "a,b c d" 解析为 bash 数组
    local raw="${1//,/ }"
    read -ra WHITELIST_IPS <<< "$raw"
}

if [[ -z "${WHITELIST_IPS+x}" ]]; then
    parse_list_env "$UFW_DEFAULT_WHITELIST"
else
    parse_list_env "$WHITELIST_IPS"
fi
unset UFW_DEFAULT_TARGET_PORTS UFW_DEFAULT_WHITELIST

# 自动检测默认出口网卡（用于区分外网入站 vs 容器出站）
EXTERNAL_INTERFACE="${EXTERNAL_INTERFACE:-$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}')}"

# -----------------------------
# 通配符 / CIDR 归一化
# -----------------------------
to_cidr() {
    local entry="$1"
    if [[ "$entry" == */* ]]; then
        echo "$entry"
        return
    fi
    if [[ "$entry" != *"*"* ]]; then
        echo "$entry"
        return
    fi
    local a b c d
    IFS='.' read -r a b c d <<< "$entry"
    [[ -z "$a" || "$a" == "*" ]] && { echo "错误：无效白名单条目 $entry" >&2; return 1; }
    if   [[ "$b" == "*" ]]; then echo "${a}.0.0.0/8"
    elif [[ "$c" == "*" ]]; then echo "${a}.${b}.0.0/16"
    elif [[ "$d" == "*" ]]; then echo "${a}.${b}.${c}.0/24"
    else                          echo "${a}.${b}.${c}.${d}/32"
    fi
}

is_ipv4_cidr() {
    [[ "$1" != *:* && "$1" =~ ^[0-9] ]]
}

is_ipv6_cidr() {
    [[ "$1" == *:* ]]
}

# 判断 IP 是否落在白名单 CIDR 内（需 python3）
ip_in_cidr() {
    local ip="$1" cidr="$2"
    python3 - "$ip" "$cidr" <<'PY'
import ipaddress, sys
ip, cidr = sys.argv[1], sys.argv[2]
try:
    addr = ipaddress.ip_address(ip)
    net = ipaddress.ip_network(cidr, strict=False)
    sys.exit(0 if addr in net else 1)
except ValueError:
    sys.exit(1)
PY
}

# 检测 Docker 网桥（docker0 + br-*）
detect_docker_interfaces() {
    ip -o link show type bridge 2>/dev/null \
        | awk -F': ' '{print $2}' \
        | grep -E '^(docker0|br-)' \
        || true
}

# TARGET_PORTS / WHITELIST_IPS 不能为空
validate_config() {
    local port ip has_port=false has_ip=false

    for port in ${TARGET_PORTS//,/ }; do
        [[ -n "$port" ]] && has_port=true && break
    done
    if ! $has_port; then
        echo "错误：TARGET_PORTS 不能为空，请至少指定一个端口" >&2
        exit 1
    fi

    for ip in "${WHITELIST_IPS[@]}"; do
        [[ -n "$ip" ]] && has_ip=true && break
    done
    if ! $has_ip; then
        echo "错误：WHITELIST_IPS 不能为空，请至少指定一个 IP 或网段" >&2
        exit 1
    fi
}

# SSH 会话来源 IP 必须在白名单内，避免误配锁死
assert_ssh_whitelisted() {
    [[ -z "${SSH_CONNECTION:-}" ]] && return 0
    local ssh_ip="${SSH_CONNECTION%% *}"
    local ip cidr
    for ip in "${WHITELIST_IPS[@]}"; do
        cidr=$(to_cidr "$ip") || return 1
        is_ipv4_cidr "$cidr" || continue
        if ip_in_cidr "$ssh_ip" "$cidr"; then
            echo "SSH 来源 ${ssh_ip} 在白名单内（${cidr}）"
            return 0
        fi
    done
    echo "错误：当前 SSH 来源 ${ssh_ip} 不在白名单，拒绝应用规则以免锁死连接" >&2
    echo "请先将 ${ssh_ip} 加入 WHITELIST_IPS 后再运行" >&2
    exit 1
}

ensure_forward_policy() {
    local ufw_default="/etc/default/ufw"
    if grep -q 'DEFAULT_FORWARD_POLICY="ACCEPT"' "$ufw_default"; then
        return 0
    fi
    if grep -q 'DEFAULT_FORWARD_POLICY="DROP"' "$ufw_default"; then
        sudo sed -i 's/DEFAULT_FORWARD_POLICY="DROP"/DEFAULT_FORWARD_POLICY="ACCEPT"/' "$ufw_default"
        echo "已将 DEFAULT_FORWARD_POLICY 设为 ACCEPT（Docker 转发需要）"
        return 0
    fi
    echo "警告：无法在 ${ufw_default} 中设置 DEFAULT_FORWARD_POLICY=ACCEPT，Docker 转发可能异常" >&2
}

DOCKER_USER_LOG_PREFIX="[DOCKER-USER DROP] "
DOCKER_USER_LOG_LIMIT="${DOCKER_USER_LOG_LIMIT:-30/min}"
DOCKER_USER_LOG_BURST="${DOCKER_USER_LOG_BURST:-50}"

# DOCKER-USER：LOG（限速）+ DROP，拦截记录写入 /var/log/kern.log
docker_user_drop_with_log() {
    local ipt="$1"
    shift
    sudo "$ipt" -A DOCKER-USER "$@" \
        -m limit --limit "$DOCKER_USER_LOG_LIMIT" --limit-burst "$DOCKER_USER_LOG_BURST" \
        -j LOG --log-prefix "$DOCKER_USER_LOG_PREFIX" --log-level 4
    sudo "$ipt" -A DOCKER-USER "$@" -j DROP
}

# -----------------------------
# 配置 iptables/ip6tables 的 DOCKER-USER 链
# -----------------------------
configure_docker_user_chain() {
    local ipt="$1"  # iptables 或 ip6tables
    local is_v6=false
    [[ "$ipt" == "ip6tables" ]] && is_v6=true

    if ! sudo "$ipt" -L DOCKER-USER -n &>/dev/null; then
        echo "警告：$ipt DOCKER-USER 链不存在（Docker 未运行？），跳过" >&2
        echo "      Docker 启动后请重新执行: $0 enable" >&2
        return 0
    fi

    sudo "$ipt" -F DOCKER-USER
    sudo "$ipt" -A DOCKER-USER -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN

    local port ip cidr has_v6_rule=false
    for port in $TARGET_PORTS; do
        for ip in "${WHITELIST_IPS[@]}"; do
            cidr=$(to_cidr "$ip") || return 1
            if $is_v6; then
                is_ipv6_cidr "$cidr" || continue
                has_v6_rule=true
            else
                is_ipv4_cidr "$cidr" || continue
            fi
            sudo "$ipt" -A DOCKER-USER -i "$EXTERNAL_INTERFACE" -p tcp \
                -m conntrack --ctorigdstport "$port" -s "$cidr" -j ACCEPT
        done
    done

    # 统一 DROP 外网入站 TCP（白名单已在上方 ACCEPT，无需 per-port 重复 DROP）
    docker_user_drop_with_log "$ipt" -i "$EXTERNAL_INTERFACE" -p tcp \
        -m conntrack --ctorigdstport 1:65535

    sudo "$ipt" -A DOCKER-USER -j RETURN

    if $is_v6 && ! $has_v6_rule; then
        echo "$ipt DOCKER-USER 已配置（无 IPv6 白名单，外网 IPv6 访问 Docker 端口将被拒绝；DROP 写入 kern.log）"
    else
        echo "$ipt DOCKER-USER 已配置（DROP 写入 kern.log，make log 查看）"
    fi
}

allow_docker_bridges() {
    local iface
    while IFS= read -r iface; do
        [[ -z "$iface" ]] && continue
        echo "允许 Docker 网桥: $iface"
        sudo ufw allow in  on "$iface"
        sudo ufw allow out on "$iface"
    done < <(detect_docker_interfaces)
}

cmd_enable() {
    validate_config

    if [[ -z "$EXTERNAL_INTERFACE" ]]; then
        echo "错误：无法自动检测出口网卡，请设置 EXTERNAL_INTERFACE 环境变量" >&2
        exit 1
    fi
    echo "出口网卡：$EXTERNAL_INTERFACE"

    assert_ssh_whitelisted

    echo "重置 UFW..."
    sudo ufw --force reset

    ensure_forward_policy

    echo "设置默认策略：拒绝入站，出站与转发不受限"
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    sudo ufw default allow routed

    echo "允许 Docker 网桥内部流量..."
    allow_docker_bridges

    echo "配置 UFW 白名单规则（TARGET_PORTS）..."
    local port ip cidr
    for port in $TARGET_PORTS; do
        for ip in "${WHITELIST_IPS[@]}"; do
            cidr=$(to_cidr "$ip") || exit 1
            if is_ipv4_cidr "$cidr"; then
                sudo ufw allow from "$cidr" to any port "$port" proto tcp
            elif is_ipv6_cidr "$cidr"; then
                sudo ufw allow from "$cidr" to any port "$port" proto tcp
            fi
        done
    done

    echo "启用 UFW..."
    sudo ufw --force enable

    configure_docker_user_chain "iptables"
    configure_docker_user_chain "ip6tables"

    echo ""
    echo "完成！"
    echo "  - TARGET_PORTS（${TARGET_PORTS}）：仅白名单 IP 可从外网访问"
    echo "  - 其他所有入站端口：拒绝"
    echo "  - 本机与容器访问公网：不受限制"
    echo ""
    sudo ufw status verbose
    echo ""
    echo "=== iptables DOCKER-USER ==="
    sudo iptables  -L DOCKER-USER -n --line-numbers 2>/dev/null || echo "（链不存在）"
    echo ""
    echo "=== ip6tables DOCKER-USER ==="
    sudo ip6tables -L DOCKER-USER -n --line-numbers 2>/dev/null || echo "（链不存在）"
}

cmd_disable() {
    echo "关闭 UFW..."
    sudo ufw disable

    local ipt
    for ipt in iptables ip6tables; do
        if sudo "$ipt" -L DOCKER-USER -n &>/dev/null; then
            echo "清空 ${ipt} DOCKER-USER 链，恢复 Docker 默认放行"
            sudo "$ipt" -F DOCKER-USER
            sudo "$ipt" -A DOCKER-USER -j RETURN
        fi
    done

    echo "完成：UFW 已关闭，DOCKER-USER 已恢复为默认 RETURN"
    sudo ufw status 2>/dev/null || true
}

grep_docker_drop_logs() {
    local f=/var/log/kern.log
    {
        if [[ -f "$f" ]]; then
            sudo grep -hF "$DOCKER_USER_LOG_PREFIX" "$f" 2>/dev/null || true
        fi
        for rot in "$f".* "$f"-*; do
            [[ -e "$rot" ]] || continue
            if [[ "$rot" == *.gz ]]; then
                sudo zgrep -hF "$DOCKER_USER_LOG_PREFIX" "$rot" 2>/dev/null || true
            elif [[ -f "$rot" ]]; then
                sudo grep -hF "$DOCKER_USER_LOG_PREFIX" "$rot" 2>/dev/null || true
            fi
        done
    } | sort -u
}

format_cutoff_cst() {
    local cutoff_utc="$1"
    TZ=Asia/Shanghai date -d "${cutoff_utc} UTC" '+%Y-%m-%dT%H:%M:%S %Z' 2>/dev/null \
        || echo "${cutoff_utc} CST"
}

format_since_window() {
    local since="$1" cutoff="$2" cutoff_cst
    cutoff_cst="$(format_cutoff_cst "$cutoff")"
    if [[ "$since" =~ ^([0-9]+)[[:space:]]+days?$ ]]; then
        echo "统计窗口: 最近 ${BASH_REMATCH[1]} 天（>= ${cutoff_cst}）"
    elif [[ "$since" =~ ^([0-9]+)[[:space:]]+hours?$ ]]; then
        echo "统计窗口: 最近 ${BASH_REMATCH[1]} 小时（>= ${cutoff_cst}）"
    else
        echo "统计窗口: >= ${cutoff_cst}（BLOCKED_SINCE=${since}）"
    fi
}

# 将 BLOCKED_SINCE（如 "1 day" / "24 hours" / ISO 时间）转为可比较的 UTC 时间前缀（kern.log 为 UTC）
# ISO 无时区后缀时按中国时区（Asia/Shanghai）理解；带 Z / +00:00 / +08:00 等则按字面解析
blocked_since_cutoff() {
    local since="$1" cutoff normalized
    if [[ "$since" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2} ]]; then
        if [[ "$since" =~ [Zz]$|[+-][0-9]{2}:[0-9]{2}$ ]]; then
            if ! cutoff=$(date -u -d "$since" '+%Y-%m-%dT%H:%M:%S' 2>/dev/null); then
                echo "错误：无效的 BLOCKED_SINCE=${since}" >&2
                return 1
            fi
        else
            normalized="${since//T/ }"
            normalized="${normalized%%.*}"
            if ! cutoff=$(TZ=Asia/Shanghai date -u -d "${normalized} CST" '+%Y-%m-%dT%H:%M:%S' 2>/dev/null); then
                echo "错误：无效的 BLOCKED_SINCE=${since}（ISO 示例: 2026-06-30T17:00:00 或 2026-06-30T09:00:00+00:00）" >&2
                return 1
            fi
        fi
        echo "$cutoff"
        return 0
    fi
    if ! cutoff=$(date -u -d "$since ago" '+%Y-%m-%dT%H:%M:%S' 2>/dev/null); then
        echo "错误：无效的 BLOCKED_SINCE=${since}（示例: \"1 day\", \"24 hours\"）" >&2
        return 1
    fi
    echo "$cutoff"
}

filter_logs_since() {
    local logs="$1" since="$2"
    [[ -z "$since" ]] && { echo "$logs"; return 0; }
    local cutoff
    cutoff="$(blocked_since_cutoff "$since")" || return 1
    echo "$logs" | awk -v since="$cutoff" '
        {
            ts = $1
            sub(/\+.*$/, "", ts)
            sub(/\..*$/, "", ts)
            if (ts >= since) print
        }'
}

cmd_blocked_ips() {
    local limit="${1:-50}"
    local since="${BLOCKED_SINCE:-}"
    local logs cutoff
    logs="$(grep_docker_drop_logs)"
    if [[ -n "$since" ]]; then
        cutoff="$(blocked_since_cutoff "$since")" || exit 1
        logs="$(filter_logs_since "$logs" "$since")" || exit 1
        format_since_window "$since" "$cutoff"
        echo ""
    fi

    if [[ -z "$logs" ]]; then
        if [[ -n "$since" ]]; then
            echo "（该时间窗口内暂无拦截记录）"
        else
            echo "（暂无 LOG 记录）"
            echo "  说明：需先 make enable / make h20-43 / make h20-44 应用带 LOG 的规则，之后新的拦截才会写入 /var/log/kern.log；用 make log 查看统计"
            echo ""
            echo "=== iptables DROP 计数（历史累计，不含 IP）==="
            sudo iptables -L DOCKER-USER -n -v 2>/dev/null | grep DROP || echo "（链不存在）"
        fi
        return 0
    fi

    printf '%s\n' "$logs" | python3 "${SCRIPT_DIR}/blocked_ips_report.py"

    if [[ "$limit" != "0" ]]; then
        echo "=== 最近 ${limit} 条拦截明细 ==="
        echo "$logs" | tail -n "$limit"
    fi
}

usage() {
    cat <<EOF
用法: $0 <enable|disable|blocked-ips [N]|log [N]>

  enable        重置并应用 UFW + DOCKER-USER 白名单规则（默认）
  disable       关闭 UFW，清空 DOCKER-USER 自定义规则
  blocked-ips   从 kern.log 汇总 DOCKER-USER 拦截（表格；配合 BLOCKED_SINCE 过滤）
                ISO 时间无时区时按中国时区理解，统计窗口以中国时区显示

Makefile 示例:
  make log                  最近 1 天拦截统计（表格）
  make log DAYS=3           最近 3 天
  make log BLOCKED_SINCE="24 hours"
  make log BLOCKED_SINCE="2026-06-30T17:00:00"        # 中国时区
  make log BLOCKED_SINCE="2026-06-30T09:00:00+00:00"  # 显式 UTC
  make enable TARGET_PORTS="22 8080" WHITELIST_IPS="1.2.3.4,10.0.0.0/8"
EOF
}

main() {
    local action="${1:-enable}"
    case "$action" in
        enable)  cmd_enable ;;
        disable) cmd_disable ;;
        blocked-ips) cmd_blocked_ips "${2:-50}" ;;
        -h|--help|help) usage ;;
        *)
            echo "错误：未知命令 $action" >&2
            usage >&2
            exit 1
            ;;
    esac
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
