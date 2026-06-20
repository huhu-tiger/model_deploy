#!/bin/bash
# 构建 llmcompressor 量化镜像
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="model.vnet.com/sjhl/vllm-openai:v0.23.0-llmcompressor"

echo "=== 构建镜像: $IMAGE ==="
docker build \
    --network host \
    -t "$IMAGE" \
    "$SCRIPT_DIR"

echo ""
echo "=== 构建完成 ==="
echo "镜像: $IMAGE"
echo ""
echo "验证："
echo "  docker run --rm $IMAGE python3 -c \"import llmcompressor; print(llmcompressor.__version__)\""
