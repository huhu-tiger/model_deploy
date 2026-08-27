# shellcheck shell=bash
# 进程硬超时包装。其它脚本: source .../common/timeout.sh && run_with_timeout 600 cmd...

run_with_timeout() {
  local hard_to="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout --signal=TERM --kill-after=30 "${hard_to}" "$@"
  else
    "$@"
  fi
}
