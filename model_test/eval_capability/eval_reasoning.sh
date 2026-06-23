#!/bin/bash

# ============================================================================
# EvalScope 能力评测 - 推理 / 数学 / 代码
# ============================================================================
# 评测维度：
#   gsm8k        小学数学应用题
#   math_500     高难度数学（MATH 子集，按难度 Level 1-5）
#   humaneval    代码生成（pass@1）
# 注：推理类任务建议保留 enable_thinking=true（如果模型支持）
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"
source "${SCRIPT_DIR}/eval_common.sh"

source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV:-model_test}"

export USE_MODELSCOPE_HUB=1
export MODELSCOPE_CACHE="${MODELSCOPE_CACHE:-${SCRIPT_DIR}/datasets}"

API_HOST="${API_HOST:-61.49.53.41}"
API_PORT="${API_PORT:-30001}"
MODEL_NAME="${MODEL_NAME:-/media/llm/Qwen/Qwen3.6-35B-A3B}"
API_KEY="${API_KEY:-EMPTY}"
LIMIT="${LIMIT:-50}"
EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-16}"
ENABLE_THINKING="${ENABLE_THINKING:-true}"
MAX_TOKENS="${MAX_TOKENS:-16384}"

API_URL="${API_URL:-http://${API_HOST}:${API_PORT}/v1}"

# 规范化为 JSON boolean
if [ "${ENABLE_THINKING}" = "true" ] || [ "${ENABLE_THINKING}" = "1" ] || [ "${ENABLE_THINKING}" = "yes" ]; then
    ENABLE_THINKING_JSON=true
else
    ENABLE_THINKING_JSON=false
fi
WORK_DIR="outputs/$(date +%Y%m%d_%H%M%S)_reasoning"

echo "=========================================="
echo "能力评测：推理 / 数学 / 代码"
echo "=========================================="
echo "API:        ${API_URL}"
echo "Model:      ${MODEL_NAME}"
echo "Datasets:   gsm8k / math_500 / humaneval"
echo "Concurrent: ${EVAL_BATCH_SIZE}"
echo "Thinking:   ${ENABLE_THINKING}"
echo "Work dir:   ${WORK_DIR}"
echo "=========================================="

# 推理任务输出更长，max_tokens 调大
evalscope eval \
  --model "${MODEL_NAME}" \
  --api-url "${API_URL}" \
  --api-key "${API_KEY}" \
  --eval-type openai_api \
  --datasets gsm8k math_500 humaneval \
  --dataset-args '{"math_500": {"few_shot_num": 0, "subset_list": ["Level 1", "Level 2", "Level 3", "Level 4", "Level 5"]}}' \
  --limit "${LIMIT}" \
  --eval-batch-size "${EVAL_BATCH_SIZE}" \
  --work-dir "${WORK_DIR}" \
  --ignore-errors \
  --generation-config "{\"temperature\": 0.6, \"top_p\": 0.95, \"max_tokens\": ${MAX_TOKENS}, \"extra_body\": {\"chat_template_kwargs\": {\"enable_thinking\": ${ENABLE_THINKING_JSON}}}}"

write_eval_summary "${WORK_DIR}"

echo ""
echo "评测完成，结果目录：${WORK_DIR}"
