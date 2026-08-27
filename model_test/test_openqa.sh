#!/bin/bash

# ============================================================================
# EvalScope 压测命令 - 使用 OpenQA 数据集（基础压测）
# ============================================================================
# 目标: 测试多个并发级别的性能表现
# 数据集: OpenQA (真实问答数据，自动从 ModelScope 下载)
# 优点: 不需要 tokenizer，测试真实场景
# 模式: 基础压测（非 SLA 自动调优）
# ============================================================================

# 激活 conda 环境
source $(conda info --base)/etc/profile.d/conda.sh
conda activate model_test

# 设置使用 ModelScope（而不是 HuggingFace）
export USE_MODELSCOPE_HUB=1
export MODELSCOPE_CACHE=/root/.cache/modelscope

echo "=========================================="
echo "压测配置: OpenQA 数据集 - 基础压测"
echo "=========================================="
echo "数据集: OpenQA (真实问答)"
echo "目标: http://172.31.0.32:30001  Ornith-1.0-35B"
echo "并发级别: 32, 48, 64"
echo "每级请求数: 64, 96, 128"
echo "模式: 基础性能测试"
echo "=========================================="
echo ""

# 执行压测 - 测试多个并发级别
evalscope perf \
  --model /media/llm/deepreinforce-ai/Ornith-1.0-35B \
  --url http://172.31.0.32:30001/v1/chat/completions \
  --extra-args '{"chat_template_kwargs": {"enable_thinking": false}}' \
  --api openai \
  --dataset openqa \
  --parallel  32 48 64\
  --number 64 96 128\
  --min-prompt-length 10 \
  --max-prompt-length 8000 \
  --max-tokens 2048 \
  --temperature 0.1 \
  --top-p 1.0 \
  --stream \
  --visualizer swanlab \
  --swanlab-api-key local \
  --name 'Ornith-1.0-35B_openqa'

