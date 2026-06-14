#!/bin/bash
# ============================================================================
# 按字数阶梯探测最大输入/输出（16K→32K→64K→…→512K，报错即停，不用 tokenizer）
# ============================================================================
# 用法:
#   ./run.sh
#   API_URL=http://127.0.0.1:30003/v1/chat/completions MODEL_NAME=minimax-m2.7 ./run.sh
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v conda >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  source "$(conda info --base)/etc/profile.d/conda.sh"
  conda activate model_test 2>/dev/null || true
fi

API_URL="${API_URL:-http://127.0.0.1:30003/v1/chat/completions}"
MODEL_NAME="${MODEL_NAME:-Qwen3.6-35B-A3B}"
API_KEY="${API_KEY:-}"
START_K="${START_K:-16}"
MAX_K="${MAX_K:-512}"
STEP_K="${STEP_K:-0}"
OUTPUT_START_K="${OUTPUT_START_K:-1}"
OUTPUT_MAX_K="${OUTPUT_MAX_K:-64}"
K_UNIT="${K_UNIT:-1024}"
TIMEOUT="${TIMEOUT:-600}"
JOINT_INPUT_K="${JOINT_INPUT_K:-0}"
if [[ -z "${EXTRA_BODY:-}" ]]; then
  EXTRA_BODY='{"chat_template_kwargs":{"enable_thinking":false}}'
fi

echo "=========================================="
echo "最大输入/输出长度探测（字数阶梯）"
echo "=========================================="
echo "API:     ${API_URL}"
echo "Model:   ${MODEL_NAME}"
if [[ "${STEP_K}" == "0" ]]; then
  echo "阶梯:    ${START_K}K → ${MAX_K}K，步进=翻倍 (×${K_UNIT} 字/K)"
else
  echo "阶梯:    ${START_K}K → ${MAX_K}K，步进=+${STEP_K}K (×${K_UNIT} 字/K)"
fi
echo "=========================================="
echo ""

ARGS=(
  --url "${API_URL}"
  --model "${MODEL_NAME}"
  --start-k "${START_K}"
  --max-k "${MAX_K}"
  --step-k "${STEP_K}"
  --output-start-k "${OUTPUT_START_K}"
  --output-max-k "${OUTPUT_MAX_K}"
  --k-unit "${K_UNIT}"
  --extra-body "${EXTRA_BODY}"
  --timeout "${TIMEOUT}"
)

if [[ -n "${API_KEY}" ]]; then
  ARGS+=(--api-key "${API_KEY}")
fi
if [[ "${SKIP_INPUT:-0}" == "1" ]]; then
  ARGS+=(--skip-input)
fi
if [[ "${SKIP_OUTPUT:-0}" == "1" ]]; then
  ARGS+=(--skip-output)
fi
if [[ "${JOINT_INPUT_K:-0}" != "0" ]]; then
  ARGS+=(--joint-input-k "${JOINT_INPUT_K}")
fi

python3 "${SCRIPT_DIR}/test_max_length.py" "${ARGS[@]}" "$@"
