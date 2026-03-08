#!/bin/bash

# Qwen Image Edit API 启动脚本

echo "🚀 启动 Qwen Image Edit API 服务..."

# 检查Python环境
if ! command -v python &> /dev/null; then
    echo "❌ 错误: 未找到Python环境"
    exit 1
fi

# 检查依赖
echo "📦 检查依赖..."
if ! python -c "import fastapi, uvicorn, torch, diffusers" &> /dev/null; then
    echo "⚠️  警告: 缺少某些依赖，正在安装..."
    pip install -r requirements.txt
fi

# 检查模型路径
MODEL_PATH="/media/llm/Qwen-Image-Edit"
if [ ! -d "$MODEL_PATH" ]; then
    echo "⚠️  警告: 模型路径不存在: $MODEL_PATH"
    echo "请确保Qwen-Image-Edit模型已正确下载到指定路径"
fi

# 设置环境变量
export CUDA_VISIBLE_DEVICES=4
export vl_base_url="http://192.168.0.2:9116/v1"
export vl_model="Qwen2.5-VL-7B-Instruct"

# 创建输出目录
mkdir -p output_images

# 启动服务
echo "🌐 启动API服务在 http://localhost:8000"
echo "📚 API文档地址: http://localhost:8000/docs"
echo "🔍 健康检查: http://localhost:8000/health"
echo "📁 图片目录: output_images/"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

python api.py 