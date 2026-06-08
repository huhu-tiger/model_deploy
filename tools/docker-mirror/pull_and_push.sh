#!/usr/bin/env bash
# 从远程仓库拉取 Docker 镜像，打标签后推送到内网仓库 model.vnet.com/sjhl，推送成功后删除本地镜像
#
# 用法:
#   ./pull_and_push.sh <镜像> [<镜像> ...]
#
# 示例:
#   ./pull_and_push.sh vllm/vllm-openai:v0.22.1
#   ./pull_and_push.sh vllm/vllm-omni:v0.22.0,vllm/vllm-openai:v0.22.1
#
# 输入 vllm/vllm-openai:v0.22.1 将自动推送至 model.vnet.com/sjhl/vllm-openai:v0.22.1

set -euo pipefail

REGISTRY="model.vnet.com/sjhl"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECORD_FILE="${SCRIPT_DIR}/pushed_images.txt"

usage() {
    cat <<EOF
用法: $(basename "$0") <镜像> [<镜像> ...]

从远程拉取镜像，打标签后推送到 ${REGISTRY}，成功后记录并删除本地镜像。
支持空格或逗号分隔多个镜像。

示例:
  $(basename "$0") vllm/vllm-openai:v0.22.1
  $(basename "$0") vllm/vllm-omni:v0.22.0,vllm/vllm-openai:v0.22.1
  $(basename "$0") vllm/vllm-openai:v0.22.1 nvidia/cuda:12.0.0-base
EOF
    exit 1
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

is_recorded() {
    local dest="$1"
    [[ -f "$RECORD_FILE" ]] && grep -qxF "$dest" "$RECORD_FILE"
}

process_image() {
    local src="$1"
    local dest

    dest="$(to_local_image "$src")" || return 1

    echo "========================================"
    echo "源镜像:   $src"
    echo "目标镜像: $dest"
    echo "========================================"

    echo "[1/4] docker pull $src"
    if ! docker pull "$src"; then
        echo "错误: pull 失败: $src" >&2
        return 1
    fi

    echo "[2/4] docker tag $src $dest"
    if ! docker tag "$src" "$dest"; then
        echo "错误: tag 失败: $src -> $dest" >&2
        return 1
    fi

    echo "[3/4] docker push $dest"
    if ! docker push "$dest"; then
        echo "错误: push 失败: $dest" >&2
        return 1
    fi

    echo "$dest" >> "$RECORD_FILE"
    echo "已记录: $dest -> $RECORD_FILE"

    echo "[4/4] docker rmi -f $dest $src"
    if ! docker rmi -f "$dest" "$src"; then
        echo "警告: 删除本地镜像失败（推送已成功）: $dest, $src" >&2
    else
        echo "已删除本地镜像: $dest, $src"
    fi
}

main() {
    if [[ $# -lt 1 ]]; then
        usage
    fi

    local images=()
    collect_images images "$@"

    if [[ ${#images[@]} -eq 0 ]]; then
        usage
    fi

    touch "$RECORD_FILE"

    local failed=0
    local skipped=0
    local processed=0
    local image
    local dest

    for image in "${images[@]}"; do
        dest="$(to_local_image "$image")" || { failed=1; continue; }
        if is_recorded "$dest"; then
            echo "跳过: $dest 已在推送记录中 ($RECORD_FILE)"
            skipped=$((skipped + 1))
            continue
        fi
        if process_image "$image"; then
            processed=$((processed + 1))
        else
            echo "失败: $image" >&2
            failed=1
        fi
    done

    if [[ $failed -ne 0 ]]; then
        echo "部分镜像处理失败（已处理: ${processed}, 已跳过: ${skipped}）" >&2
        exit 1
    fi

    if [[ $processed -eq 0 && $skipped -gt 0 ]]; then
        echo "全部镜像均已推送过，无需重复处理（已跳过: ${skipped}）"
    elif [[ $skipped -gt 0 ]]; then
        echo "全部镜像处理完成（已处理: ${processed}, 已跳过: ${skipped}）"
    else
        echo "全部镜像处理完成"
    fi
}

main "$@"
