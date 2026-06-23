#!/bin/bash

# ============================================================================
# EvalScope 能力评测 - 快速冒烟（小样本）
# ============================================================================
# 适用：模型上线前快速验证能力是否正常（每个数据集只跑 LIMIT 条）
# 评测维度：
#   gsm8k          基础数学推理
#   ifeval         指令遵循
#   gpqa_diamond   研究生级科学推理（硬推理）
#   bfcl_v3        工具调用 / Function Calling（覆盖全部 4 类）：
#     AST_NON_LIVE  simple / multiple / parallel / irrelevance
#                   — 函数调用格式校验（静态 AST 匹配）
#     AST_LIVE      live_simple / live_multiple / live_parallel
#                   — 函数调用真实执行，测参数是否能跑通
#     MULTI_TURN    multi_turn_base / multi_turn_miss_func /
#                   multi_turn_miss_param / multi_turn_long_context
#                   — 多轮对话工具调用，测上下文追踪与连续调用
# 区别于 test_*.sh：那些是吞吐/延迟压测，本脚本评测的是回答质量/准确率
# ============================================================================
# 前置：工具调用部分需要 bfcl-eval 包
#   pip install bfcl-eval==2025.10.27.1
# BFCL 默认走 prompt 模式（兼容所有 OpenAI 接口）；如模型支持原生 function call，
# 设 BFCL_FC_MODE=true，并确保推理服务端开启了 tool parser：
#   vLLM:   --enable-auto-tool-choice --tool-call-parser hermes
#   SGLang: --tool-call-parser qwen3
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"
source "${SCRIPT_DIR}/eval_common.sh"

source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV:-model_test}"

export USE_MODELSCOPE_HUB=1
export MODELSCOPE_CACHE="${MODELSCOPE_CACHE:-${SCRIPT_DIR}/datasets}"

# --- 与推理服务对齐 ---
API_HOST="${API_HOST:-61.49.53.41}"
API_PORT="${API_PORT:-30001}"
MODEL_NAME="${MODEL_NAME:-/media/llm/Qwen/Qwen3.6-35B-A3B}"
API_KEY="${API_KEY:-EMPTY}"
LIMIT="${LIMIT:-50}"
EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-8}"

# 思考模式（推理类需要开；ifeval 影响小，统一开以兼顾 gpqa/gsm8k）
ENABLE_THINKING="${ENABLE_THINKING:-true}"
MAX_TOKENS="${MAX_TOKENS:-8192}"

# BFCL：默认 prompt 模式（最稳），需要时切原生 fc
BFCL_FC_MODE="${BFCL_FC_MODE:-false}"

API_URL="${API_URL:-http://${API_HOST}:${API_PORT}/v1}"

# 规范化为 JSON boolean（防止 1/yes/True 等导致 JSON 非法）
if [ "${ENABLE_THINKING}" = "true" ] || [ "${ENABLE_THINKING}" = "1" ] || [ "${ENABLE_THINKING}" = "yes" ]; then
    ENABLE_THINKING_JSON=true
else
    ENABLE_THINKING_JSON=false
fi

# 规范化 BFCL_FC_MODE 为 JSON boolean
if [ "${BFCL_FC_MODE}" = "true" ] || [ "${BFCL_FC_MODE}" = "1" ] || [ "${BFCL_FC_MODE}" = "yes" ]; then
    BFCL_FC_MODE_JSON=true
else
    BFCL_FC_MODE_JSON=false
fi
WORK_DIR="outputs/$(date +%Y%m%d_%H%M%S)_quick"

echo "=========================================="
echo "能力评测：快速冒烟（每数据集 ${LIMIT} 条）"
echo "=========================================="
echo "API:        ${API_URL}"
echo "Model:      ${MODEL_NAME}"
echo "Datasets:   gsm8k / ifeval / gpqa_diamond / bfcl_v3 (AST_NON_LIVE + AST_LIVE + MULTI_TURN)"
echo "Concurrent: ${EVAL_BATCH_SIZE}"
echo "Thinking:   ${ENABLE_THINKING}  (max_tokens=${MAX_TOKENS})"
echo "BFCL fc:    ${BFCL_FC_MODE}"
echo "Work dir:   ${WORK_DIR}"
echo "=========================================="

evalscope eval \
  --model "${MODEL_NAME}" \
  --api-url "${API_URL}" \
  --api-key "${API_KEY}" \
  --eval-type openai_api \
  --datasets gsm8k ifeval gpqa_diamond bfcl_v3 \
  --dataset-args "{
    \"gsm8k\": {\"few_shot_num\": 0},
    \"gpqa_diamond\": {\"few_shot_num\": 0},
    \"bfcl_v3\": {
      \"subset_list\": [
        \"simple\", \"multiple\", \"parallel\", \"irrelevance\",
        \"live_simple\", \"live_multiple\", \"live_parallel\", \"live_irrelevance\",
        \"multi_turn_base\", \"multi_turn_miss_func\", \"multi_turn_miss_param\", \"multi_turn_long_context\"
      ],
      \"extra_params\": {
        \"underscore_to_dot\": true,
        \"is_fc_model\": ${BFCL_FC_MODE_JSON}
      }
    }
  }" \
  --limit "${LIMIT}" \
  --eval-batch-size "${EVAL_BATCH_SIZE}" \
  --work-dir "${WORK_DIR}" \
  --ignore-errors \
  --generation-config "{
    \"temperature\": 0.6,
    \"top_p\": 0.95,
    \"max_tokens\": ${MAX_TOKENS},
    \"extra_body\": {\"chat_template_kwargs\": {\"enable_thinking\": ${ENABLE_THINKING_JSON}}}
  }"

write_eval_summary "${WORK_DIR}"

echo ""
echo "评测完成，结果目录：${WORK_DIR}"
