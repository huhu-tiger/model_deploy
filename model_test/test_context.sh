#!/bin/bash

# ============================================================================
# EvalScope 压测 - Random 数据集（长上下文）
# ============================================================================
# 须与当前推理服务一致：model 名、URL、tokenizer 路径
# 查看已注册模型: curl -s http://127.0.0.1:${API_PORT}/v1/models | jq .
# ============================================================================

# 激活 conda 环境
source $(conda info --base)/etc/profile.d/conda.sh
conda activate model_test

export USE_MODELSCOPE_HUB=1
export MODELSCOPE_CACHE=/root/.cache/modelscope

# --- 与 docker-compose 对齐（当前 30001 = vLLM Qwen3.6-27B + DFlash）---
API_PORT="${API_PORT:-30001}"
MODEL_NAME="${MODEL_NAME:-Qwen3.6-35B-A3B}"
TOKENIZER_PATH="${TOKENIZER_PATH:-/media/llm/palmfuture/Qwen3.6-35B-A3B-GPTQ-Int4}"
BENCH_NAME="${BENCH_NAME:-Qwen3.6-35B-A3B_context_4k-6.5k_swanlab}"

# 若压测 35B GPTQ-Int4（SGLang 30001）可改为：
# MODEL_NAME=Qwen3.6-35B-A3B
# TOKENIZER_PATH=/media/llm/palmfuture/Qwen3.6-35B-A3B-GPTQ-Int4
# BENCH_NAME=Qwen3.6-35B-A3B_context_4k-6.5k_swanlab

API_URL="http://127.0.0.1:${API_PORT}/v1/chat/completions"

echo "=========================================="
echo "压测配置: Random 数据集 - 长上下文"
echo "=========================================="
echo "API:        ${API_URL}"
echo "Model:      ${MODEL_NAME}"
echo "Tokenizer:  ${TOKENIZER_PATH}"
echo "Prompt:     4000-6500 tokens (apply_chat_template 后)"
echo "Parallel:   8, 16  |  Number: 16, 32"
echo "=========================================="
echo ""

evalscope perf \
  --model "${MODEL_NAME}" \
  --url "${API_URL}" \
  --extra-args '{"chat_template_kwargs": {"enable_thinking": false}}' \
  --api openai \
  --dataset random \
  --tokenizer-path "${TOKENIZER_PATH}" \
  --parallel 8 16 \
  --number 16 32 \
  --min-prompt-length 4000 \
  --max-prompt-length 6500 \
  --prefix-length 0 \
  --max-tokens 2048 \
  --temperature 0.7 \
  --top-p 1.0 \
  --stream \
  --visualizer swanlab \
  --swanlab-api-key local \
  --name "${BENCH_NAME}"
