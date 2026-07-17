#!/usr/bin/env bash
# 代理加载、NO_PROXY、按源仓直连的 skopeo 封装
# （由 pull_and_push.sh source，勿直接执行；依赖 registry.sh）

load_proxy_from_docker_daemon() {
    local conf_dir="/etc/systemd/system/docker.service.d"
    local conf line key val
    local loaded=0
    local prev_noproxy="${NO_PROXY:-${no_proxy:-}}"

    [[ -d "$conf_dir" ]] || return 1

    for conf in "$conf_dir"/*.conf; do
        [[ -f "$conf" ]] || continue
        while IFS= read -r line || [[ -n "$line" ]]; do
            [[ "$line" =~ ^Environment=\"([A-Za-z_]+)=([^\"]+)\"$ ]] || continue
            key="${BASH_REMATCH[1]}"
            val="${BASH_REMATCH[2]}"
            if [[ "$key" == "NO_PROXY" || "$key" == "no_proxy" ]]; then
                export NO_PROXY="$val"
                export no_proxy="$val"
                if [[ -n "$prev_noproxy" ]]; then
                    merge_noproxy "$prev_noproxy"
                fi
            else
                export "${key}=${val}"
            fi
            loaded=1
        done < "$conf"
    done

    [[ "$loaded" -eq 1 ]]
}

merge_noproxy() {
    local extra="$1"
    local cur="${NO_PROXY:-${no_proxy:-}}"
    local part
    local IFS=','

    for part in $extra; do
        part="${part// /}"
        [[ -n "$part" ]] || continue
        if [[ -z "$cur" ]]; then
            cur="$part"
        elif [[ ",${cur}," != *",${part},"* ]]; then
            cur="${cur},${part}"
        fi
    done
    export NO_PROXY="$cur"
    export no_proxy="$cur"
}

ensure_dest_noproxy() {
    # 目标仓必须直连；代理通常无法访问内网 Harbor
    local dest_host="${REGISTRY%%/*}"
    merge_noproxy "${dest_host},.${dest_host#*.},localhost,127.0.0.1"
}

# 国内源仓：对该次 skopeo 调用清除代理（比仅靠 NO_PROXY 更可靠）
run_skopeo() {
    local src_ref="$1"
    shift
    local host
    host="$(registry_host_from_ref "$src_ref")"

    if is_domestic_registry "$host"; then
        merge_noproxy "${host},.${host#*.}"
        env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
            -u ALL_PROXY -u all_proxy \
            skopeo "$@"
    else
        # 海外源走代理，但目标仓仍须在 NO_PROXY 中
        ensure_dest_noproxy
        skopeo "$@"
    fi
}

setup_proxy() {
    # SKOPEO_PROXY 未定义 → 用默认；显式空字符串 → 不设默认，可回退到 shell / daemon
    if [[ -z "${SKOPEO_PROXY+x}" ]]; then
        SKOPEO_PROXY="${DEFAULT_SKOPEO_PROXY}"
    fi

    if [[ -n "${SKOPEO_PROXY}" ]]; then
        export HTTP_PROXY="${SKOPEO_PROXY}"
        export HTTPS_PROXY="${SKOPEO_PROXY}"
        unset ALL_PROXY all_proxy
        log "" "使用 SKOPEO_PROXY: ${HTTP_PROXY}"
    elif [[ -z "${HTTP_PROXY:-}" && -z "${HTTPS_PROXY:-}" && -z "${ALL_PROXY:-}" ]]; then
        if load_proxy_from_docker_daemon; then
            log "" "已从 Docker daemon 加载代理: ${HTTP_PROXY:-${ALL_PROXY:-unknown}}"
        fi
    fi

    if [[ -n "${HTTP_PROXY:-}${HTTPS_PROXY:-}${ALL_PROXY:-}" ]]; then
        ensure_dest_noproxy
        log "" "NO_PROXY: ${NO_PROXY}"
    fi

    if [[ -n "${HTTP_PROXY:-}" ]]; then
        export http_proxy="${HTTP_PROXY}"
    fi
    if [[ -n "${HTTPS_PROXY:-}" ]]; then
        export https_proxy="${HTTPS_PROXY}"
    fi
    if [[ -n "${NO_PROXY:-}" ]]; then
        export no_proxy="${NO_PROXY}"
    fi

    if [[ -z "${ALL_PROXY:-}" && -n "${HTTP_PROXY:-}" && "${HTTP_PROXY}" == socks5://* ]]; then
        export ALL_PROXY="${HTTP_PROXY}"
        export all_proxy="${HTTP_PROXY}"
        log "" "提示: skopeo 对 SOCKS5 支持有限，若失败请 setproxy 或设置 SKOPEO_PROXY=http://..." >&2
    fi
    if [[ -n "${ALL_PROXY:-}" ]]; then
        export all_proxy="${ALL_PROXY}"
    fi
}
