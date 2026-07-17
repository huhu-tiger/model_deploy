#!/usr/bin/env bash
# 推送记录与跳过判断
# （由 pull_and_push.sh source，勿直接执行；依赖 proxy.sh 的 run_skopeo）

skopeo_inspect_dest() {
    local dest="$1"
    local -a args=(inspect)

    if [[ "${DEST_TLS_VERIFY}" != "true" ]]; then
        args+=(--tls-verify=false)
    fi

    # 目标仓为内网，走 run_skopeo 直连逻辑
    run_skopeo "$dest" "${args[@]}" "docker://${dest}"
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
