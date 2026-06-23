#!/bin/bash

# ============================================================================
# EvalScope 能力评测 - 中文综合能力
# ============================================================================
# 评测维度：
#   ceval    中文综合学科（52 科目，知识 + 推理）
#   cmmlu    中文多任务语言理解（67 学科，偏中国本土）
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
LIMIT="${LIMIT:-100}"
EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-16}"

API_URL="${API_URL:-http://${API_HOST}:${API_PORT}/v1}"
WORK_DIR="outputs/$(date +%Y%m%d_%H%M%S)_chinese"

echo "=========================================="
echo "能力评测：中文综合（每数据集 ${LIMIT} 条）"
echo "=========================================="
echo "API:        ${API_URL}"
echo "Model:      ${MODEL_NAME}"
echo "Datasets:   ceval / cmmlu"
echo "Concurrent: ${EVAL_BATCH_SIZE}"
echo "Work dir:   ${WORK_DIR}"
echo "=========================================="

evalscope eval \
  --model "${MODEL_NAME}" \
  --api-url "${API_URL}" \
  --api-key "${API_KEY}" \
  --eval-type openai_api \
  --datasets ceval cmmlu \
  --limit "${LIMIT}" \
  --eval-batch-size "${EVAL_BATCH_SIZE}" \
  --work-dir "${WORK_DIR}" \
  --ignore-errors \
  --generation-config '{"temperature": 0.0, "max_tokens": 2048, "extra_body": {"chat_template_kwargs": {"enable_thinking": false}}}'

write_eval_summary "${WORK_DIR}"

echo ""
echo "评测完成，结果目录：${WORK_DIR}"
