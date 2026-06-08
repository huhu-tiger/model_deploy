#!/usr/bin/env bash
# 从远程仓库同步 Docker 镜像到内网仓库 model.vnet.com/sjhl
#
# 模式:
#   direct - skopeo copy  registry 直传，不落盘（默认，需 skopeo）
#   local  - docker pull → tag → push → rmi（需 Docker）
#
# 用法:
#   ./pull_and_push.sh [选项] <镜像> [<镜像> ...]
#
# 示例:
#   ./pull_and_push.sh vllm/vllm-openai:v0.22.1
#   ./pull_and_push.sh -j 3 -p linux/amd64 vllm/vllm-openai:v0.22.1
#   ./pull_and_push.sh --mode local vllm/vllm-openai:v0.22.1

set -euo pipefail

REGISTRY="model.vnet.com/sjhl"
DEFAULT_SKOPEO_PROXY="http://172.22.220.21:20171"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECORD_FILE="${SCRIPT_DIR}/pushed_images.txt"
RECORD_LOCK="${RECORD_FILE}.lock"

MODE="direct"
PARALLEL_JOBS=1
PLATFORM=""
CHECK_REMOTE=0
SRC_PREFIX="${SRC_PREFIX:-}"
DOCKER_AUTH_FILE=""
DEST_TLS_VERIFY="${DEST_TLS_VERIFY:-false}"

usage() {
    cat <<EOF
用法: $(basename "$0") [选项] <镜像> [<镜像> ...]

同步镜像到 ${REGISTRY}，成功后写入 pushed_images.txt。
支持空格或逗号分隔多个镜像。

模式:
  --mode direct        skopeo copy  registry 直传，不落盘（默认，需 skopeo）
  --mode local         docker pull → tag → push → rmi（需 Docker）

选项:
  -j, --jobs N         并行处理镜像数（默认 1）
  -p, --platform PLAT  指定平台（如 linux/amd64）
      --src-prefix URL  源镜像前缀/镜像站（如 docker.m.daocloud.io）
      --check-remote   目标仓库已有该镜像则跳过
  -h, --help           显示此帮助

环境变量:
  HTTP_PROXY / HTTPS_PROXY / ALL_PROXY   访问 Docker Hub 的代理
  SKOPEO_PROXY                         专用于 skopeo 的 HTTP 代理（默认 ${DEFAULT_SKOPEO_PROXY}）
  SRC_PREFIX                             同 --src-prefix
  未设置代理时，自动读取 Docker daemon 的 systemd 代理配置

示例:
  $(basename "$0") vllm/vllm-openai:v0.22.1
  $(basename "$0") -j 3 -p linux/amd64 nvidia/cuda:12.0.0-base
  $(basename "$0") --src-prefix docker.m.daocloud.io vllm/vllm-openai:v0.22.1
  $(basename "$0") --mode local vllm/vllm-openai:v0.22.1
EOF
    exit 1
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --mode)
                [[ $# -ge 2 ]] || usage
                MODE="$2"
                shift 2
                ;;
            -j|--jobs)
                [[ $# -ge 2 ]] || usage
                PARALLEL_JOBS="$2"
                shift 2
                ;;
            -p|--platform)
                [[ $# -ge 2 ]] || usage
                PLATFORM="$2"
                shift 2
                ;;
            --check-remote)
                CHECK_REMOTE=1
                shift
                ;;
            --src-prefix)
                [[ $# -ge 2 ]] || usage
                SRC_PREFIX="$2"
                shift 2
                ;;
            -h|--help)
                usage
                ;;
            --)
                shift
                break
                ;;
            -*)
                echo "错误: 未知选项: $1" >&2
                usage
                ;;
            *)
                break
                ;;
        esac
    done

    if [[ $# -lt 1 ]]; then
        usage
    fi

    case "$MODE" in
        local|direct) ;;
        *)
            echo "错误: --mode 须为 local 或 direct，当前: $MODE" >&2
            exit 1
            ;;
    esac

    if ! [[ "$PARALLEL_JOBS" =~ ^[1-9][0-9]*$ ]]; then
        echo "错误: --jobs 须为正整数，当前: $PARALLEL_JOBS" >&2
        exit 1
    fi

    IMAGE_ARGS=("$@")
}

load_proxy_from_docker_daemon() {
    local conf_dir="/etc/systemd/system/docker.service.d"
    local conf line key val
    local loaded=0

    [[ -d "$conf_dir" ]] || return 1

    for conf in "$conf_dir"/*.conf; do
        [[ -f "$conf" ]] || continue
        while IFS= read -r line || [[ -n "$line" ]]; do
            [[ "$line" =~ ^Environment=\"([A-Za-z_]+)=([^\"]+)\"$ ]] || continue
            key="${BASH_REMATCH[1]}"
            val="${BASH_REMATCH[2]}"
            export "${key}=${val}"
            loaded=1
        done < "$conf"
    done

    [[ "$loaded" -eq 1 ]]
}

setup_proxy() {
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

resolve_docker_authfile() {
    if [[ -n "${DOCKER_CONFIG:-}" && -f "${DOCKER_CONFIG}/config.json" ]]; then
        DOCKER_AUTH_FILE="${DOCKER_CONFIG}/config.json"
    elif [[ -f "${HOME}/.docker/config.json" ]]; then
        DOCKER_AUTH_FILE="${HOME}/.docker/config.json"
    else
        DOCKER_AUTH_FILE=""
    fi
}

resolve_src_ref() {
    local src="$1"
    local prefix="${SRC_PREFIX:-}"

    if [[ -z "$prefix" ]]; then
        echo "$src"
        return 0
    fi

    prefix="${prefix#docker://}"
    prefix="${prefix%/}"
    src="${src#docker.io/}"
    src="${src#registry-1.docker.io/}"
    echo "${prefix}/${src}"
}

append_skopeo_dest_args() {
    local -n _args=$1
    if [[ "${DEST_TLS_VERIFY}" != "true" ]]; then
        _args+=(--dest-tls-verify=false)
    fi
}

append_skopeo_auth_args() {
    local -n _args=$1
    if [[ -n "$DOCKER_AUTH_FILE" ]]; then
        _args+=(--src-authfile "$DOCKER_AUTH_FILE" --dest-authfile "$DOCKER_AUTH_FILE")
    fi
}

skopeo_inspect_dest() {
    local dest="$1"
    local -a args=(inspect)

    if [[ "${DEST_TLS_VERIFY}" != "true" ]]; then
        args+=(--tls-verify=false)
    fi

    skopeo "${args[@]}" "docker://${dest}"
}

ensure_dependencies() {
    if [[ "$MODE" == "direct" ]]; then
        if ! command -v skopeo >/dev/null 2>&1; then
            echo "错误: direct 模式需要 skopeo，请安装: sudo apt install skopeo" >&2
            exit 1
        fi
        setup_proxy
        resolve_docker_authfile
        if [[ -z "${HTTP_PROXY:-}${HTTPS_PROXY:-}${ALL_PROXY:-}" ]]; then
            echo "警告: 未检测到代理，访问 Docker Hub 可能超时；可先执行 setproxy 或设置 HTTP_PROXY" >&2
        fi
    elif ! command -v docker >/dev/null 2>&1; then
        echo "错误: local 模式需要 docker" >&2
        exit 1
    fi
}

collect_images() {
    local -n _out=$1
    shift
    local arg item

    _out=()
    for arg in "$@"; do
        arg="${arg//,/ }"
        for item in $arg; do
            if [[ -n "$item" ]]; then
                _out+=("$item")
            fi
        done
    done
}

to_local_image() {
    local src="$1"
    local image_part tag image_name

    if [[ "$src" == *@* ]]; then
        echo "错误: 暂不支持带 digest 的镜像引用: $src" >&2
        return 1
    fi

    if [[ "$src" == *:* ]]; then
        tag="${src##*:}"
        image_part="${src%:*}"
    else
        tag="latest"
        image_part="$src"
    fi

    image_name="${image_part##*/}"
    echo "${REGISTRY}/${image_name}:${tag}"
}

log() {
    local src="${1:-}"
    shift || true
    if [[ -n "$src" ]]; then
        echo "[${src}] $*"
    else
        echo "$*"
    fi
}

is_recorded() {
    local dest="$1"
    [[ -f "$RECORD_FILE" ]] && grep -qxF "$dest" "$RECORD_FILE"
}

is_remote_exists() {
    local dest="$1"
    if [[ "$MODE" == "direct" ]]; then
        skopeo_inspect_dest "$dest" >/dev/null 2>&1
    else
        docker manifest inspect "$dest" >/dev/null 2>&1
    fi
}

record_image() {
    local dest="$1"
    (
        flock -x 9
        grep -qxF "$dest" "$RECORD_FILE" 2>/dev/null || echo "$dest" >> "$RECORD_FILE"
    ) 9>>"$RECORD_LOCK"
}

should_skip() {
    local src="$1"
    local dest="$2"

    if is_recorded "$dest"; then
        log "$src" "跳过: $src -> $dest （已在 $RECORD_FILE 中）"
        return 0
    fi

    if [[ "$CHECK_REMOTE" -eq 1 ]] && is_remote_exists "$dest"; then
        log "$src" "跳过: $src -> $dest （目标仓库已存在，写入记录）"
        record_image "$dest"
        return 0
    fi

    return 1
}

append_skopeo_platform_args() {
    local -n _args=$1
    local plat="$2"
    local os arch rest

    if [[ -z "$plat" ]]; then
        return 0
    fi

    if [[ "$plat" != */* ]]; then
        echo "错误: 平台格式须为 os/arch（如 linux/amd64），当前: $plat" >&2
        return 1
    fi

    os="${plat%%/*}"
    rest="${plat#*/}"
    arch="${rest%%/*}"

    _args+=(--override-os "$os" --override-arch "$arch")

    if [[ "$rest" == */* ]]; then
        _args+=(--override-variant "${rest#*/}")
    fi
}

docker_pull() {
    local src="$1"
    local -a args=(pull)

    if [[ -n "$PLATFORM" ]]; then
        args+=(--platform "$PLATFORM")
    fi

    docker "${args[@]}" "$src"
}

process_image_local() {
    local src="$1"
    local dest
    local start_ts elapsed

    dest="$(to_local_image "$src")" || return 1
    start_ts=$(date +%s)

    log "$src" "========================================"
    log "$src" "模式:     local (docker pull/tag/push)"
    log "$src" "源镜像:   $src"
    log "$src" "目标镜像: $dest"
    [[ -n "$PLATFORM" ]] && log "$src" "平台:     $PLATFORM"
    log "$src" "========================================"

    log "$src" "[1/4] docker pull $src"
    if ! docker_pull "$src"; then
        log "$src" "错误: pull 失败: $src" >&2
        return 1
    fi

    log "$src" "[2/4] docker tag $src $dest"
    if ! docker tag "$src" "$dest"; then
        log "$src" "错误: tag 失败: $src -> $dest" >&2
        return 1
    fi

    log "$src" "[3/4] docker push $dest"
    if ! docker push "$dest"; then
        log "$src" "错误: push 失败: $dest" >&2
        return 1
    fi

    record_image "$dest"
    log "$src" "已记录: $dest -> $RECORD_FILE"

    log "$src" "[4/4] docker rmi -f $dest $src"
    if ! docker rmi -f "$dest" "$src"; then
        log "$src" "警告: 删除本地镜像失败（推送已成功）: $dest, $src" >&2
    else
        log "$src" "已删除本地镜像: $dest, $src"
    fi

    elapsed=$(( $(date +%s) - start_ts ))
    log "$src" "完成，耗时 ${elapsed}s"
}

process_image_direct() {
    local src="$1"
    local dest
    local skopeo_src
    local start_ts elapsed
    local -a copy_args=(copy --retry-times 3)

    dest="$(to_local_image "$src")" || return 1
    skopeo_src="$(resolve_src_ref "$src")"
    append_skopeo_platform_args copy_args "$PLATFORM" || return 1
    append_skopeo_auth_args copy_args
    append_skopeo_dest_args copy_args
    start_ts=$(date +%s)

    log "$src" "========================================"
    log "$src" "模式:     direct (skopeo copy，不落盘)"
    log "$src" "源镜像:   docker://${skopeo_src}"
    log "$src" "目标镜像: docker://${dest}"
    [[ -n "$PLATFORM" ]] && log "$src" "平台:     $PLATFORM"
    [[ -n "${HTTP_PROXY:-}" ]] && log "$src" "代理:     ${HTTP_PROXY}"
    [[ -n "$SRC_PREFIX" && "$skopeo_src" != "$src" ]] && log "$src" "原始源:   $src"
    log "$src" "========================================"

    log "$src" "[1/1] skopeo copy docker://${skopeo_src} docker://${dest}"
    if ! skopeo "${copy_args[@]}" "docker://${skopeo_src}" "docker://${dest}"; then
        log "$src" "错误: skopeo copy 失败: $src -> $dest" >&2
        log "$src" "提示: 若 TLS 超时，请先 setproxy 或使用 --src-prefix 指定镜像站" >&2
        return 1
    fi

    record_image "$dest"
    log "$src" "已记录: $dest -> $RECORD_FILE"

    elapsed=$(( $(date +%s) - start_ts ))
    log "$src" "完成，耗时 ${elapsed}s"
}

process_image() {
    if [[ "$MODE" == "direct" ]]; then
        process_image_direct "$1"
    else
        process_image_local "$1"
    fi
}

run_image() {
    local image="$1"
    local dest

    dest="$(to_local_image "$image")" || return 1

    if should_skip "$image" "$dest"; then
        echo "skipped" >> "${STATS_DIR}/skipped"
        return 0
    fi

    if process_image "$image"; then
        echo "processed" >> "${STATS_DIR}/processed"
    else
        echo "failed" >> "${STATS_DIR}/failed"
        log "$image" "失败: $image" >&2
        return 1
    fi
}

count_stats() {
    local file="$1"
    if [[ -f "$file" ]]; then
        wc -l < "$file" | tr -d ' '
    else
        echo 0
    fi
}

main() {
    parse_args "$@"
    ensure_dependencies

    local images=()
    collect_images images "${IMAGE_ARGS[@]}"

    if [[ ${#images[@]} -eq 0 ]]; then
        usage
    fi

    touch "$RECORD_FILE"
    STATS_DIR=$(mktemp -d)
    trap 'rm -rf "$STATS_DIR"' EXIT

    local failed=0
    local image
    local running=0

    for image in "${images[@]}"; do
        if ! to_local_image "$image" >/dev/null; then
            failed=1
            continue
        fi

        if [[ "$PARALLEL_JOBS" -gt 1 ]]; then
            while (( running >= PARALLEL_JOBS )); do
                if ! wait -n; then
                    failed=1
                fi
                running=$((running - 1))
            done
            run_image "$image" &
            running=$((running + 1))
        else
            if ! run_image "$image"; then
                failed=1
            fi
        fi
    done

    if [[ "$PARALLEL_JOBS" -gt 1 ]]; then
        while (( running > 0 )); do
            if ! wait -n; then
                failed=1
            fi
            running=$((running - 1))
        done
    fi

    local processed skipped
    processed=$(count_stats "${STATS_DIR}/processed")
    skipped=$(count_stats "${STATS_DIR}/skipped")

    if [[ $failed -ne 0 ]]; then
        echo "部分镜像处理失败（已处理: ${processed}, 已跳过: ${skipped}）" >&2
        exit 1
    fi

    if [[ $processed -eq 0 && $skipped -gt 0 ]]; then
        echo "全部镜像均已推送过，无需重复处理（已跳过: ${skipped}）"
    elif [[ $skipped -gt 0 ]]; then
        echo "全部镜像处理完成（已处理: ${processed}, 已跳过: ${skipped}）"
    else
        echo "全部镜像处理完成（共 ${processed} 个，模式: ${MODE}）"
    fi
}

main "$@"
