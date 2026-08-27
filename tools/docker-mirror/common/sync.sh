#!/usr/bin/env bash
# direct / local 单镜像同步
# （由 pull_and_push.sh source，勿直接执行）

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
    local dest pull_src
    local start_ts elapsed

    dest="$(to_local_image "$src")" || return 1
    pull_src="$(resolve_src_ref "$src")"
    start_ts=$(date +%s)

    log "$src" "========================================"
    log "$src" "模式:     local (docker pull/tag/push)"
    log "$src" "源镜像:   $pull_src"
    log "$src" "目标镜像: $dest"
    [[ -n "$PLATFORM" ]] && log "$src" "平台:     $PLATFORM"
    [[ -n "$SRC_PREFIX" && "$pull_src" != "$src" ]] && log "$src" "原始源:   $src"
    log "$src" "========================================"

    log "$src" "[1/4] docker pull $pull_src"
    if ! docker_pull "$pull_src"; then
        log "$src" "错误: pull 失败: $pull_src" >&2
        return 1
    fi

    log "$src" "[2/4] docker tag $pull_src $dest"
    if ! docker tag "$pull_src" "$dest"; then
        log "$src" "错误: tag 失败: $pull_src -> $dest" >&2
        return 1
    fi

    log "$src" "[3/4] docker push $dest"
    if ! docker push "$dest"; then
        log "$src" "错误: push 失败: $dest" >&2
        return 1
    fi

    record_image "$dest"
    log "$src" "已记录: $dest -> $RECORD_FILE"

    log "$src" "[4/4] docker rmi -f $dest $pull_src"
    if ! docker rmi -f "$dest" "$pull_src"; then
        log "$src" "警告: 删除本地镜像失败（推送已成功）: $dest, $pull_src" >&2
    else
        log "$src" "已删除本地镜像: $dest, $pull_src"
    fi

    elapsed=$(( $(date +%s) - start_ts ))
    log "$src" "完成，耗时 ${elapsed}s"
}

process_image_direct() {
    local src="$1"
    local dest
    local skopeo_src src_host
    local start_ts elapsed
    local -a copy_args=(copy --retry-times 3)

    dest="$(to_local_image "$src")" || return 1
    skopeo_src="$(resolve_src_ref "$src")"
    src_host="$(registry_host_from_ref "$skopeo_src")"
    append_skopeo_platform_args copy_args "$PLATFORM" || return 1
    append_skopeo_auth_args copy_args
    append_skopeo_dest_args copy_args
    start_ts=$(date +%s)

    log "$src" "========================================"
    log "$src" "模式:     direct (skopeo copy，不落盘)"
    log "$src" "源镜像:   docker://${skopeo_src}"
    log "$src" "目标镜像: docker://${dest}"
    [[ -n "$PLATFORM" ]] && log "$src" "平台:     $PLATFORM"
    if is_domestic_registry "$src_host"; then
        log "$src" "代理:     直连（国内仓库 ${src_host}）"
    elif [[ -n "${HTTP_PROXY:-}" ]]; then
        log "$src" "代理:     ${HTTP_PROXY}"
    fi
    [[ -n "$SRC_PREFIX" && "$skopeo_src" != "$src" ]] && log "$src" "原始源:   $src"
    log "$src" "========================================"

    log "$src" "[1/1] skopeo copy docker://${skopeo_src} docker://${dest}"
    if ! run_skopeo "$skopeo_src" "${copy_args[@]}" "docker://${skopeo_src}" "docker://${dest}"; then
        log "$src" "错误: skopeo copy 失败: $src -> $dest" >&2
        if is_domestic_registry "$src_host"; then
            log "$src" "提示: 国内仓库直连失败，请检查网络或镜像地址" >&2
        else
            log "$src" "提示: 若 TLS 超时，请先 setproxy 或使用 --src-prefix 指定镜像站" >&2
        fi
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
