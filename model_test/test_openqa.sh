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
echo "并发级别: 1, 2, 4, 8, 16, 32"
echo "每级请求数: 100"
echo "模式: 基础性能测试"
echo "=========================================="
echo ""

# 执行压测 - 测试多个并发级别
evalscope perf \
  --model deepseek-v3.2 \
  --url http://61.49.53.5:30002/v1/chat/completions \
  --api openai \
  --dataset openqa \
  --parallel 1 2 4 8 16 32 \
  --number 2 4 8 16 32 64 \
  --min-prompt-length 10 \
  --max-prompt-length 2000 \
  --max-tokens 2048 \
  --temperature 0.1 \
  --top-p 1.0 \
  --stream \
  --visualizer swanlab \
  --swanlab-api-key local \
  --name 'deepseek-v3.2_of_swanlab_log'



echo ""
echo "=========================================="
echo "压测完成！"
echo "=========================================="
echo "查看结果:"
echo "  - 文本报告: outputs/*/deepseek-v3.2/performance_summary.txt"
echo "  - 可视化图表: outputs/charts/performance_metrics.png"
echo "=========================================="
