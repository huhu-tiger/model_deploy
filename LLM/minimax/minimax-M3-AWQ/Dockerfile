# MiniMax-M3-AWQ-INT4 — 方案 B（源码编译）
# ModelScope: https://modelscope.cn/models/cyankiwi/MiniMax-M3-AWQ-INT4
#
# 与方案 A 区别:
#   A = vllm/vllm-openai:minimax-m3 底座 + 仅覆盖 compressed-tensors 补丁（快）
#   B = 基于 a7fdfeef 补丁分支全量编译 CUDA，Python/C++ 严格同源（慢，约 1～3h）
#
# 构建:
#   make build
# 内网基础镜像:
#   make build BASE_IMAGE_B=model.vnet.com/sjhl/vllm-openai:v0.23.0

ARG BASE_IMAGE=model.vnet.com/sjhl/vllm-openai:v0.23.0
FROM ${BASE_IMAGE}

ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_TRUSTED_HOST=mirrors.aliyun.com
ARG UPSTREAM_COMMIT=a7fdfeef72323eb3db6f0620e4ea200290d0ca5a
ARG PATCH_COMMIT=8f1350ebf25f188a77022c70b575731f0df6a61a
# H100 Hopper (compute capability 9.0)
ARG TORCH_CUDA_ARCH_LIST=9.0
ARG MAX_JOBS=64
ARG NVCC_THREADS=4

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    TORCH_CUDA_ARCH_LIST=${TORCH_CUDA_ARCH_LIST} \
    MAX_JOBS=${MAX_JOBS} \
    NVCC_THREADS=${NVCC_THREADS} \
    CMAKE_BUILD_TYPE=RelWithDebInfo

# 显式禁用预编译，避免继承基础镜像或环境中的 wheel 覆盖
ENV VLLM_USE_PRECOMPILED=0

RUN env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
      apt-get update \
    && env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
      apt-get install -y --no-install-recommends \
        git \
        pkg-config \
        rustc \
        cargo \
        cuda-nvrtc-dev-13-0 \
      && rm -rf /var/lib/apt/lists/*

# 卸载基础镜像自带 vllm，防止旧 _C.abi3.so 残留
RUN python3 -m pip uninstall -y vllm 2>/dev/null || true \
    && rm -rf /usr/local/lib/python3.12/dist-packages/vllm \
              /usr/local/lib/python3.12/dist-packages/vllm-*.dist-info \
              /opt/vllm-minimax-m3-awq

WORKDIR /opt/vllm-minimax-m3-awq

ARG HTTP_PROXY=
ARG HTTPS_PROXY=
RUN if [ -n "${HTTP_PROXY}" ]; then \
      export HTTP_PROXY="${HTTP_PROXY}" HTTPS_PROXY="${HTTPS_PROXY}" \
             http_proxy="${HTTP_PROXY}" https_proxy="${HTTPS_PROXY}"; \
    fi \
    && git clone https://github.com/toncao/vllm.git . \
    && git remote add upstream https://github.com/vllm-project/vllm.git \
    && git fetch upstream "${UPSTREAM_COMMIT}" \
    && git checkout minimax-m3-compressed-tensors \
    && git checkout "${PATCH_COMMIT}"

RUN mkdir -p /root/.pip \
    && printf '[global]\nindex-url = %s\ntrusted-host = %s\n' \
         "${PIP_INDEX_URL}" "${PIP_TRUSTED_HOST}" > /root/.pip/pip.conf

# build 依赖（对齐 requirements/build/cuda.txt；torch 已由基础镜像提供）
RUN env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
      NO_PROXY= no_proxy= \
    python3 -m pip install --proxy="" \
      "cmake>=3.26.1" \
      ninja \
      packaging \
      "setuptools>=77.0.3,<81.0.0" \
      "setuptools-scm>=8" \
      "setuptools-rust>=1.9.0" \
      wheel \
      jinja2 \
      regex \
      build

# 源码编译安装（pip 不走代理；cmake FetchContent 拉 GitHub 子模块需保留 HTTP_PROXY）
ARG HTTP_PROXY=
ARG HTTPS_PROXY=
RUN if [ -n "${HTTP_PROXY}" ]; then \
      export HTTP_PROXY="${HTTP_PROXY}" HTTPS_PROXY="${HTTPS_PROXY}" \
             http_proxy="${HTTP_PROXY}" https_proxy="${HTTPS_PROXY}"; \
    fi \
    && VLLM_USE_PRECOMPILED=0 \
    python3 -m pip install -e . --no-build-isolation --proxy=""

RUN python3 - <<'PY'
import os
import vllm
import torch

print("vllm:", vllm.__version__)
print("vllm path:", os.path.dirname(vllm.__file__))
print("VLLM_USE_PRECOMPILED:", os.environ.get("VLLM_USE_PRECOMPILED"))

op = getattr(torch.ops._C, "fused_minimax_m3_qknorm_rope_kv_insert", None)
if op is None:
    raise SystemExit("ERROR: fused_minimax_m3_qknorm_rope_kv_insert missing after source build")
print("M3 op schema:", op.schema)

import importlib
importlib.import_module(
    "vllm.model_executor.layers.quantization.compressed_tensors.compressed_tensors_moe"
)
print("compressed-tensors: OK")
print("scheme B source build: OK")
PY
