#!/bin/bash
# 兼容旧路径：转发到 context_bench/
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/context_bench/test_context_sweep.sh" "$@"
