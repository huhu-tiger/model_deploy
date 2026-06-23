#!/bin/bash

# ============================================================================
# EvalScope 能力评测 - 深度推理（hard）
# ============================================================================
# 业内推理评测"铁三角"，对标 DeepSeek-R1 / QwQ / Qwen3-Thinking 那一档：
#   gpqa_diamond      研究生级 物理/化学/生物，多选题，重深度推理
#   aime25            2025 AIME 竞赛数学，30 题
#   live_code_bench   LeetCode 风格代码推理（默认 release_latest 子集 ~2.4GB）
#   humaneval         轻量替代（164 题，~几 MB）：CODE_BENCH=humaneval
#
# 这些任务都需要长思考链路：默认开 enable_thinking，max_tokens 给足 32K
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
EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-8}"
ENABLE_THINKING="${ENABLE_THINKING:-true}"
MAX_TOKENS="${MAX_TOKENS:-32000}"

# LiveCodeBench 时间窗（防止训练集泄漏，建议取模型 cutoff 之后的题目）
LCB_START="${LCB_START:-2024-08-01}"
LCB_END="${LCB_END:-2026-07-01}"
LCB_SUBSET="${LCB_SUBSET:-release_latest}"
# 代码评测：live_code_bench（竞赛题）| humaneval（轻量经典题，~几 MB）
CODE_BENCH="${CODE_BENCH:-live_code_bench}"
if [ "${CODE_BENCH}" != "live_code_bench" ] && [ "${CODE_BENCH}" != "humaneval" ]; then
    echo "[ERROR] CODE_BENCH='${CODE_BENCH}' 无效，只接受 live_code_bench 或 humaneval" >&2
    exit 1
fi

API_URL="${API_URL:-http://${API_HOST}:${API_PORT}/v1}"

# 规范化为 JSON boolean
if [ "${ENABLE_THINKING}" = "true" ] || [ "${ENABLE_THINKING}" = "1" ] || [ "${ENABLE_THINKING}" = "yes" ]; then
    ENABLE_THINKING_JSON=true
else
    ENABLE_THINKING_JSON=false
fi
WORK_DIR="outputs/$(date +%Y%m%d_%H%M%S)_hard"

echo "=========================================="
echo "能力评测：深度推理（hard）"
echo "=========================================="
echo "API:        ${API_URL}"
echo "Model:      ${MODEL_NAME}"
echo "Datasets:   gpqa_diamond / aime25 / ${CODE_BENCH}"
if [ "${CODE_BENCH}" = "live_code_bench" ]; then
  echo "LCB subset: ${LCB_SUBSET}"
  echo "LCB date:   ${LCB_START} ~ ${LCB_END}"
fi
echo "Concurrent: ${EVAL_BATCH_SIZE}"
echo "Thinking:   ${ENABLE_THINKING}  (max_tokens=${MAX_TOKENS})"
echo "Work dir:   ${WORK_DIR}"
echo "=========================================="

if [ "${CODE_BENCH}" = "humaneval" ]; then
  DATASET_ARGS="{
    \"gpqa_diamond\": {\"few_shot_num\": 0},
    \"aime25\": {\"few_shot_num\": 0},
    \"humaneval\": {}
  }"
else
  DATASET_ARGS="{
    \"gpqa_diamond\": {\"few_shot_num\": 0},
    \"aime25\": {\"few_shot_num\": 0},
    \"live_code_bench\": {
      \"subset_list\": [\"${LCB_SUBSET}\"],
      \"extra_params\": {\"start_date\": \"${LCB_START}\", \"end_date\": \"${LCB_END}\"},
      \"filters\": {\"remove_until\": \"</think>\"}
    }
  }"
fi

evalscope eval \
  --model "${MODEL_NAME}" \
  --api-url "${API_URL}" \
  --api-key "${API_KEY}" \
  --eval-type openai_api \
  --datasets gpqa_diamond aime25 "${CODE_BENCH}" \
  --dataset-args "${DATASET_ARGS}" \
  --limit "${LIMIT}" \
  --eval-batch-size "${EVAL_BATCH_SIZE}" \
  --work-dir "${WORK_DIR}" \
  --ignore-errors \
  --generation-config "{
    \"temperature\": 0.6,
    \"top_p\": 0.95,
    \"max_tokens\": ${MAX_TOKENS},
    \"n\": 1,
    \"extra_body\": {\"chat_template_kwargs\": {\"enable_thinking\": ${ENABLE_THINKING_JSON}}}
  }"

write_eval_summary "${WORK_DIR}"

echo ""
echo "评测完成，结果目录：${WORK_DIR}"
