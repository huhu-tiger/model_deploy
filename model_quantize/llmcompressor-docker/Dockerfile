FROM model.vnet.com/sjhl/vllm-openai:v0.23.0

# ── 镜像信息 ──────────────────────────────────────────────────────
LABEL maintainer="sjhl" \
      description="vLLM v0.23.0 + llmcompressor AWQ 量化环境" \
      base="model.vnet.com/sjhl/vllm-openai:v0.23.0"

# ── 基础镜像已预装（不重复安装）────────────────────────────────────
#   torch         2.11.0+cu130
#   transformers  5.10.2
#   safetensors   0.7.0
#   compressed-tensors 0.17.0  (vllm 依赖)
#
# ── 新增依赖 ───────────────────────────────────────────────────────
#   llmcompressor 0.12.0   AWQ/GPTQ 量化框架
#     └─ compressed-tensors 0.17.1（会覆盖 0.17.0，patch 级别差异，
#                                   量化阶段不调用 vllm 推理，无影响）
#   datasets      5.0.0    校准数据集加载
#   accelerate    1.13.0   CPU offload / 多卡支持（sequential_offload_device）

COPY requirements.txt /tmp/requirements.txt

RUN pip install -r /tmp/requirements.txt \
    -i https://pypi.mirrors.ustc.edu.cn/simple/ \
    --timeout 120 \
    --retries 5 \
    && pip cache purge

# ── 验证核心 API 可用 ──────────────────────────────────────────────
RUN python3 -c "\
import llmcompressor; print('llmcompressor :', llmcompressor.__version__); \
from llmcompressor.modifiers.transform.awq import AWQModifier; print('AWQModifier          : OK'); \
from llmcompressor.modifiers.quantization import QuantizationModifier; print('QuantizationModifier : OK'); \
from llmcompressor import oneshot; print('oneshot              : OK'); \
import datasets; print('datasets      :', datasets.__version__); \
import accelerate; print('accelerate    :', accelerate.__version__); \
"

WORKDIR /workspace
