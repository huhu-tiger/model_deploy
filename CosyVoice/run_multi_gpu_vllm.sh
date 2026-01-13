#!/bin/bash

# 激活虚拟环境
source .venv_vllm/bin/activate

# 设置GPU数量，默认为2
TENSOR_PARALLEL_SIZE=${1:-2}
GPU_MEMORY_UTILIZATION=${2:-0.7}

echo "启动多GPU推理，使用 $TENSOR_PARALLEL_SIZE 个GPU，内存利用率为 $GPU_MEMORY_UTILIZATION"

# 运行多GPU推理脚本
python multi_gpu_vllm_example.py --tensor_parallel_size $TENSOR_PARALLEL_SIZE --gpu_memory_utilization $GPU_MEMORY_UTILIZATION

echo "多GPU推理完成" 