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
COMMON_DIR="${SCRIPT_DIR}/common"
RECORD_FILE="${SCRIPT_DIR}/pushed_images.txt"
RECORD_LOCK="${RECORD_FILE}.lock"
DOMESTIC_REGISTRIES_FILE="${DOMESTIC_REGISTRIES_FILE:-${SCRIPT_DIR}/domestic_registries.conf}"

MODE="direct"
PARALLEL_JOBS=1
PLATFORM=""
CHECK_REMOTE=0
SRC_PREFIX="${SRC_PREFIX:-}"
DOCKER_AUTH_FILE=""
DEST_TLS_VERIFY="${DEST_TLS_VERIFY:-false}"
# 国内仓库匹配规则（由 load_domestic_registries 填充）
DOMESTIC_PATTERNS=()
DOMESTIC_LOADED=0

# shellcheck source=common/log.sh
source "${COMMON_DIR}/log.sh"
# shellcheck source=common/registry.sh
source "${COMMON_DIR}/registry.sh"
# shellcheck source=common/proxy.sh
source "${COMMON_DIR}/proxy.sh"
# shellcheck source=common/record.sh
source "${COMMON_DIR}/record.sh"
# shellcheck source=common/sync.sh
source "${COMMON_DIR}/sync.sh"

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
  HTTP_PROXY / HTTPS_PROXY / ALL_PROXY   访问海外源的代理
  SKOPEO_PROXY                         skopeo 专用代理（默认 ${DEFAULT_SKOPEO_PROXY}；空=不设默认）
  SRC_PREFIX                             同 --src-prefix
  DOMESTIC_REGISTRIES_FILE               国内仓名单（默认 ${SCRIPT_DIR}/domestic_registries.conf）
  未设置代理时，自动读取 Docker daemon 的 systemd 代理配置
  源匹配国内仓名单时自动直连，不走代理

示例:
  $(basename "$0") vllm/vllm-openai:v0.22.1
  $(basename "$0") -j 3 -p linux/amd64 nvidia/cuda:12.0.0-base
  $(basename "$0") --src-prefix docker.m.daocloud.io vllm/vllm-openai:v0.22.1
  $(basename "$0") --mode local vllm/vllm-openai:v0.22.1
  $(basename "$0") swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/myscale/myscaledb:1.6.4
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

ensure_dependencies() {
    if [[ "$MODE" == "direct" ]]; then
        if ! command -v skopeo >/dev/null 2>&1; then
            echo "错误: direct 模式需要 skopeo，请安装: sudo apt install skopeo" >&2
            exit 1
        fi
        load_domestic_registries "$DOMESTIC_REGISTRIES_FILE" || true
        if [[ ${#DOMESTIC_PATTERNS[@]} -gt 0 ]]; then
            log "" "国内仓规则: ${#DOMESTIC_PATTERNS[@]} 条（${DOMESTIC_REGISTRIES_FILE}）"
        fi
        setup_proxy
        resolve_docker_authfile
        if [[ -z "${HTTP_PROXY:-}${HTTPS_PROXY:-}${ALL_PROXY:-}" ]]; then
            echo "警告: 未检测到代理，访问 Docker Hub / ghcr 等海外源可能超时" >&2
        fi
    elif ! command -v docker >/dev/null 2>&1; then
        echo "错误: local 模式需要 docker" >&2
        exit 1
    else
        load_domestic_registries "$DOMESTIC_REGISTRIES_FILE" || true
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
    # STATS_DIR / RECORD_LOCK 均为临时资源；正常退出、错误退出、Ctrl+C 均清理
    trap 'rm -rf "${STATS_DIR:-}"; rm -f "${RECORD_LOCK:-}"' EXIT INT TERM

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
