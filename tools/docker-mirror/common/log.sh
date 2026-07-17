#!/usr/bin/env bash
# 日志输出（由 pull_and_push.sh source，勿直接执行）

log() {
    local src="${1:-}"
    shift || true
    if [[ -n "$src" ]]; then
        echo "[${src}] $*"
    else
        echo "$*"
    fi
}
