#!/usr/bin/env bash
# ============================================================
#  Qwen3.6-35B-A3B  AWQ-4bit 量化一键运行脚本
#  方案: llmcompressor W4A16_ASYM AWQ + 多卡并行 (device_map='auto')
#
#  用法:
#    chmod +x run_quantize.sh
#    ./run_quantize.sh [GPU卡号] [校准集] [样本数]
#
#  参数（位置参数,均可省略走默认值）:
#    GPU卡号   宿主机物理 GPU 编号,逗号分隔（默认: 2,3,4,5）
#              脚本会自动转换为容器内逻辑编号 0,1,..,N-1 传给 python
#    校准集    --calib-dataset 取值,支持别名或逗号分隔多集
#              默认: cyankiwi/calibration,HuggingFaceH4/ultrachat_200k
#              （中英双语 + 英文对话混合,GLM-5.2 同款推荐配方）
#    样本数    --calib-samples,支持总数或逐集指定
#              默认: 256,256（每集 256 条,合计 512 条）
#
#  完整别名/选型见 ../docs/dataset.md 或 llmcompressor_common.DATASET_ALIASES
#
#  示例:
#    ./run_quantize.sh                                   # 全部默认
#    ./run_quantize.sh 2,3,4,5                          # 仅指定 GPU
#    ./run_quantize.sh 2,3,4,5 cyankiwi 384             # 切回单集 384 条
#    ./run_quantize.sh 2,3,4,5 ultrachat 512            # 单集 ultrachat
#    ./run_quantize.sh 2,3,4,5 cyankiwi,swebench 256,256 # 自定义混合
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_QUANTIZE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"   # llmcompressor_common 公共库在父目录
GPU_IDS="${1:-2,3,4,5}"                                            # 物理 GPU 编号
CALIB_DATASET="${2:-cyankiwi/calibration,HuggingFaceH4/ultrachat_200k}"  # 校准数据集（默认混合）
CALIB_SAMPLES="${3:-256,256}"                                      # 校准样本数（默认逐集 256）

MODEL_PATH="/media/llm/Qwen/Qwen3.6-35B-A3B"
OUTPUT_PATH="/media/llm/Qwen/Qwen3.6-35B-A3B-AWQ-4bit"
# HuggingFace 访问 token（环境变量已设置则沿用,否则用默认）
HF_TOKEN="${HF_TOKEN:-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}"
# 下载 HF 资源默认走内网代理（环境变量已设置则沿用,无代理可传空串）
HTTP_PROXY="${HTTP_PROXY:-http://172.31.0.55:20171}"
HTTPS_PROXY="${HTTPS_PROXY:-http://172.31.0.55:20171}"
NO_PROXY="${NO_PROXY:-localhost,127.0.0.1,172.31.0.0/16,model.vnet.com}"
# 预装 llmcompressor 0.12.0 + datasets 5.0.0 + accelerate 1.13.0 的镜像
# 构建脚本: /media/source/model_deploy/model_quantize/llmcompressor-docker/build.sh
IMAGE="model.vnet.com/sjhl/vllm-openai:v0.23.0-llmcompressor"

GPU_COUNT=$(echo "${GPU_IDS}" | tr ',' '\n' | wc -l)
# nvidia container runtime 已将物理 GPU ${GPU_IDS} 重映射为容器内 0,1,...,N-1。
# 容器内 Python 必须使用容器内的逻辑编号,而不是宿主机的物理编号。
CONTAINER_GPU_IDS=$(seq -s, 0 $((GPU_COUNT - 1)))

# ⚠️ Qwen3.6-35B-A3B 是 256 expert MoE,llmcompressor 0.12.0 在 multi-gpu device_map 模式下,
# AWQ 的 cache_parent_kwargs_hook 在 256 个 expert × 40 层 × 512 samples 累积 OOM。
# 默认走单卡 sequential offload(llmcompressor 官方推荐的 MoE 量化路径):
#   - 模型常驻 CPU RAM,逐层 → cuda:0 处理 → 释放
#   - 速度慢但稳定,GLM-5.2 / DeepSeek-R1 等大 MoE 都用这个
#   - 预计 4-8 小时(vs 多卡 1-2 小时,但多卡当前会 OOM)
# 实验性多卡模式: USE_MULTI_GPU=1 ./run_quantize.sh ...（需要先缩小 calib_samples 避免 OOM）
USE_MULTI_GPU="${USE_MULTI_GPU:-0}"
if [ "${USE_MULTI_GPU}" = "1" ]; then
    MULTI_GPU_FLAG="--multi-gpu"
    MULTI_GPU_NOTE="多卡 device_map（实验性,大 MoE 可能 OOM）"
else
    MULTI_GPU_FLAG=""
    MULTI_GPU_NOTE="单卡 sequential offload（稳定,推荐用于 256 expert MoE）"
fi

echo "=========================================================="
echo "  Qwen3.6-35B-A3B  llmcompressor AWQ W4A16_ASYM 量化"
echo "  GPU 卡号    : ${GPU_IDS}  (共 ${GPU_COUNT} 张)"
echo "  执行模式    : ${MULTI_GPU_NOTE}"
echo "  源模型路径  : ${MODEL_PATH}"
echo "  输出目录    : ${OUTPUT_PATH}"
echo "  校准数据集  : ${CALIB_DATASET}"
echo "  校准样本数  : ${CALIB_SAMPLES}"
echo "  Docker 镜像 : ${IMAGE}"
echo "=========================================================="

if [ ! -d "${MODEL_PATH}" ]; then
    echo "[错误] 源模型目录不存在: ${MODEL_PATH}"
    exit 1
fi

mkdir -p "${OUTPUT_PATH}"

# 镜像已预装 llmcompressor/datasets/accelerate，跳过 pip 安装
# --gpus 传容器内逻辑编号(0,1,..N-1),不是宿主机物理编号
# --multi-gpu 多卡并行(USE_MULTI_GPU=1 启用),否则单卡 sequential offload
QUANT_CMD="python3 quantize_llmcompressor.py \
    --model-path ${MODEL_PATH} \
    --output-path ${OUTPUT_PATH} \
    --gpus ${CONTAINER_GPU_IDS} \
    ${MULTI_GPU_FLAG} \
    --calib-dataset ${CALIB_DATASET} \
    --calib-samples ${CALIB_SAMPLES} \
    --max-seq-length 2048 \
    --scheme W4A16_ASYM"

FULL_CMD="set -e \
    && echo '=== 镜像已预装 llmcompressor/datasets/accelerate，跳过 pip 安装 ===' \
    && echo '=== 开始量化（GPU: ${GPU_IDS}，校准集: ${CALIB_DATASET}） ===' \
    && ${QUANT_CMD}"

echo ""
echo "[启动] Docker 容器..."
echo ""

docker run --rm \
    --runtime=nvidia \
    --entrypoint bash \
    --ipc=host \
    --shm-size=64g \
    --ulimit memlock=-1 \
    --ulimit stack=67108864 \
    -e NVIDIA_VISIBLE_DEVICES="${GPU_IDS}" \
    -e HF_HOME="/media/llm/.cache/huggingface" \
    -e HF_DATASETS_CACHE="/media/quantize/datasets" \
    -e HF_ENDPOINT="https://huggingface.co" \
    -e HF_TOKEN="${HF_TOKEN}" \
    -e HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}" \
    -e HTTP_PROXY="${HTTP_PROXY}" \
    -e HTTPS_PROXY="${HTTPS_PROXY}" \
    -e http_proxy="${HTTP_PROXY}" \
    -e https_proxy="${HTTPS_PROXY}" \
    -e NO_PROXY="${NO_PROXY}" \
    -e no_proxy="${NO_PROXY}" \
    -v /media/llm:/media/llm \
    -v /media/quantize/datasets:/media/quantize/datasets \
    -v /etc/localtime:/etc/localtime \
    -v "${MODEL_QUANTIZE_DIR}:/workspace/model_quantize" \
    -w /workspace/model_quantize/Qwen3.6-35B-A3B-AWQ \
    "${IMAGE}" \
    -c "${FULL_CMD}"

echo ""
echo "=========================================================="
echo "✅ 量化完成！"
echo "   量化模型保存在: ${OUTPUT_PATH}"
echo ""
echo "   ── 质量评测（可选）───────────────────────────────────"
echo "   docker run --rm --runtime=nvidia --entrypoint bash -e NVIDIA_VISIBLE_DEVICES=${GPU_IDS} \\"
echo "     --ipc=host -v /media/llm:/media/llm \\"
echo "     -v ${MODEL_QUANTIZE_DIR}:/workspace/model_quantize -w /workspace/model_quantize/Qwen3.6-35B-A3B-AWQ \\"
echo "     ${IMAGE} \\"
echo "     -c \\"
echo "     \"python eval_quantized.py \\"
echo "       --quant-path ${OUTPUT_PATH} \\"
echo "       --orig-path  ${MODEL_PATH} \\"
echo "       --gpus ${GPU_IDS} --dataset wikitext,ceval\""
echo ""
echo "   ── 部署（修改路径后执行）─────────────────────────────"
echo "   # 将 OUTPUT_PATH 更新到部署配置后:"
echo "   docker compose -f ../docker-compose-vllm-first.yml up -d"
echo "=========================================================="
