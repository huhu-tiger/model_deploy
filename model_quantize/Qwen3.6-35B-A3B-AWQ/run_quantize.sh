#!/usr/bin/env bash
# ============================================================
#  Qwen3.6-35B-A3B  AWQ-4bit 量化一键运行脚本
#
#  用法:
#    chmod +x run_quantize.sh
#    ./run_quantize.sh [方案] [GPU卡号]
#
#  方案选项:
#    rtn            RTN 无校准数据量化（复现 QuantTrio，推荐首选）
#                   - 无需校准数据集，速度最快（~30分钟）
#                   - 内存低（逐 shard 流式，< 30GB）
#                   - 精度略低于有校准数据方案
#    llmcompressor  llmcompressor W4A16_ASYM（复现 cyankiwi，精度最高）
#                   - 需要校准数据集和 4×A800 显存
#                   - 耗时 2~4 小时
#
#  示例:
#    ./run_quantize.sh                        # 默认 rtn，GPU 2,3,4,5
#    ./run_quantize.sh rtn 2,3,4,5           # RTN，4 卡并行（~8 分钟）
#    ./run_quantize.sh rtn 2                 # RTN，单卡（~30 分钟）
#    ./run_quantize.sh llmcompressor 2,3,4,5 # AWQ + 校准数据
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
METHOD="${1:-rtn}"            # 默认 RTN（无校准数据，低资源）
GPU_IDS="${2:-2,3,4,5}"      # 物理 GPU 编号，逗号分隔

MODEL_PATH="/media/llm/Qwen/Qwen3.6-35B-A3B"
IMAGE="model.vnet.com/sjhl/vllm-openai:v0.23.0"

# 按方案设置默认输出目录后缀
case "${METHOD}" in
    rtn)           OUTPUT_PATH="/media/llm/Qwen/Qwen3.6-35B-A3B-AWQ-4bit-RTN" ;;
    llmcompressor) OUTPUT_PATH="/media/llm/Qwen/Qwen3.6-35B-A3B-AWQ-4bit-LC"  ;;
    *)
        echo "[错误] 未知方案: ${METHOD}，支持: rtn | llmcompressor"
        exit 1
        ;;
esac

GPU_COUNT=$(echo "${GPU_IDS}" | tr ',' '\n' | wc -l)

echo "=========================================================="
echo "  Qwen3.6-35B-A3B  AWQ 量化"
echo "  方案        : ${METHOD}"
echo "  GPU 卡号    : ${GPU_IDS}  (共 ${GPU_COUNT} 张)"
echo "  源模型路径  : ${MODEL_PATH}"
echo "  输出目录    : ${OUTPUT_PATH}"
echo "  Docker 镜像 : ${IMAGE}"
echo "=========================================================="

if [ ! -d "${MODEL_PATH}" ]; then
    echo "[错误] 源模型目录不存在: ${MODEL_PATH}"
    exit 1
fi

mkdir -p "${OUTPUT_PATH}"

# ── 按方案组装命令 ──────────────────────────────────────────────
if [ "${METHOD}" = "rtn" ]; then
    # RTN：无需校准数据，逐 shard 流式处理，单卡/多卡均可
    INSTALL_CMD="pip install safetensors tqdm -i https://pypi.tuna.tsinghua.edu.cn/simple/ -q"
    QUANT_CMD="python3 quantize_rtn.py \
        --model-path ${MODEL_PATH} \
        --output-path ${OUTPUT_PATH} \
        --gpus ${GPU_IDS}"

elif [ "${METHOD}" = "llmcompressor" ]; then
    # llmcompressor：有校准数据，精度更高（参考 cyankiwi 方案）
    INSTALL_CMD="pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/ -q"
    QUANT_CMD="python3 quantize_llmcompressor.py \
        --model-path ${MODEL_PATH} \
        --output-path ${OUTPUT_PATH} \
        --gpus ${GPU_IDS} \
        --calib-dataset HuggingFaceH4/ultrachat_200k \
        --calib-samples 512 \
        --max-seq-length 2048 \
        --scheme W4A16_ASYM"
fi

FULL_CMD="set -e \
    && echo '=== 安装依赖 ===' && ${INSTALL_CMD} \
    && echo '=== 开始量化 [${METHOD}]（GPU: ${GPU_IDS}） ===' \
    && ${QUANT_CMD}"

echo ""
echo "[启动] Docker 容器..."
echo ""

docker run --rm \
    --runtime=nvidia \
    --gpus "device=${GPU_IDS}" \
    --ipc=host \
    --shm-size=64g \
    --ulimit memlock=-1 \
    --ulimit stack=67108864 \
    -e NVIDIA_VISIBLE_DEVICES="${GPU_IDS}" \
    -e HF_HOME="/media/llm/.cache/huggingface" \
    -e HF_ENDPOINT="https://hf-mirror.com" \
    -v /media/llm:/media/llm \
    -v /etc/localtime:/etc/localtime \
    -v "${SCRIPT_DIR}:/workspace/quantize" \
    -w /workspace/quantize \
    "${IMAGE}" \
    bash -c "${FULL_CMD}"

echo ""
echo "=========================================================="
echo "✅ 量化完成！"
echo "   量化模型保存在: ${OUTPUT_PATH}"
echo ""
echo "   ── 质量评测（可选）───────────────────────────────────"
echo "   docker run --rm --runtime=nvidia --gpus \"device=${GPU_IDS}\" \\"
echo "     --ipc=host -v /media/llm:/media/llm \\"
echo "     -v ${SCRIPT_DIR}:/workspace/quantize -w /workspace/quantize \\"
echo "     ${IMAGE} bash -c \\"
echo "     \"pip install datasets -q && python eval_quantized.py \\"
echo "       --quant-path ${OUTPUT_PATH} \\"
echo "       --orig-path  ${MODEL_PATH} \\"
echo "       --gpus ${GPU_IDS} --dataset wikitext,ceval\""
echo ""
echo "   ── 部署（修改路径后执行）─────────────────────────────"
echo "   # 将 OUTPUT_PATH 更新到部署配置后:"
echo "   docker compose -f ../docker-compose-vllm-first.yml up -d"
echo "=========================================================="
