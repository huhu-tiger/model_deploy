#!/bin/bash

# ============================================================================
# EvalScope 压测命令 - 使用 OpenQA 数据集
# ============================================================================
# 目标: 自动寻找满足 P99 首字延迟 (TTFT) <= 2秒 的最大并发数
# 数据集: OpenQA (真实问答数据，自动从 ModelScope 下载)
# 优点: 不需要 tokenizer，测试真实场景
# ============================================================================

# 激活 conda 环境
source $(conda info --base)/etc/profile.d/conda.sh
conda activate model_test

# 设置使用 ModelScope（而不是 HuggingFace）
export USE_MODELSCOPE_HUB=1
export MODELSCOPE_CACHE=/root/.cache/modelscope

echo "=========================================="
echo "压测配置: OpenQA 数据集"
echo "=========================================="
echo "数据集: OpenQA (真实问答)"
echo "并发范围: 2 - 128"
echo "每级请求数: 50"
echo "SLA 目标: P99 TTFT <= 2秒"
echo "=========================================="
echo ""

# 执行压测
evalscope perf \
  --model YuFeng-XGuard-Reason-0.6B \
  --url http://39.155.179.5:30001/v1/chat/completions \
  --api openai \
  --dataset openqa \
  --max-tokens 200 \
  --temperature 0.1 \
  --top-p 1.0 \
  --sla-auto-tune \
  --sla-variable parallel \
  --sla-params '[{"p99_ttft": "<=2"}]' \
  --parallel 16 \
  --sla-upper-bound 50 \
  --stream 

