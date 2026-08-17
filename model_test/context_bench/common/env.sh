# shellcheck shell=bash
# 公共环境：conda 激活、日志、路径。其它脚本: source "$(dirname "$0")/common/env.sh"

_COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTEXT_BENCH_DIR="$(cd "${_COMMON_DIR}/.." && pwd)"
COMMON_PY="${_COMMON_DIR}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }
die() { echo "[ERROR] $*" >&2; exit 1; }

activate_model_test_env() {
  local env_name="${CONDA_ENV:-model_test}"
  if ! command -v conda >/dev/null 2>&1; then
    die "未找到 conda"
  fi
  # shellcheck disable=SC1091
  source "$(conda info --base)/etc/profile.d/conda.sh"
  conda activate "${env_name}" || die "conda activate ${env_name} 失败"
  export USE_MODELSCOPE_HUB="${USE_MODELSCOPE_HUB:-1}"
  export MODELSCOPE_CACHE="${MODELSCOPE_CACHE:-/root/.cache/modelscope}"
}

# evalscope 与图表都在 conda 环境 model_test 里
ensure_evalscope() {
  if command -v conda >/dev/null 2>&1; then
    activate_model_test_env
  fi
  if ! command -v evalscope >/dev/null 2>&1; then
    die "未找到 evalscope。请安装到 conda 环境 ${CONDA_ENV:-model_test}，或先 conda activate 后再跑压测。"
  fi
}

# 从 timeouts JSON 读取整数，避免 eval
read_timeout_json() {
  local json="$1"
  local line
  line="$(python3 -c '
import json, sys
d = json.loads(sys.argv[1])
print(d["read_timeout"], d["total_timeout"], d["duration"], d["hard_timeout"])
' "${json}")" || return 1
  # shellcheck disable=SC2034
  read -r READ_TO TOTAL_TO RUN_DURATION HARD_TO <<< "${line}"
}
