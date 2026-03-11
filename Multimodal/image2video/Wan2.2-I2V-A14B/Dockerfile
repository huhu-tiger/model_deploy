#  docker build -t model.vnet.com/sjhl/vllm-omni:v0.16.0-flashattn   --build-arg HTTP_PROXY=http://192.168.0.2:20171   --build-arg HTTPS_PROXY=http://192.168.0.2:20171   --build-arg NO_PROXY=localhost,127.0.0.1   -f Dockerfile .
FROM model.vnet.com/sjhl/vllm-omni:v0.16.0

# Proxy (for apt/pip/git during build)
# You can override at build time:
#   docker build --build-arg HTTP_PROXY=http://192.168.0.2:20171 ...
ARG HTTP_PROXY=http://192.168.0.2:20171
ARG HTTPS_PROXY=http://192.168.0.2:20171
ARG NO_PROXY=localhost,127.0.0.1
ENV http_proxy=${HTTP_PROXY} \
    https_proxy=${HTTPS_PROXY} \
    HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    no_proxy=${NO_PROXY} \
    NO_PROXY=${NO_PROXY}

# Build deps for flash-attn (compiled extension)
# Notes:
# - torch in this image is 2.9.1+cu129 (Py3.12), so we compile flash-attn from source.
# - This requires network access during build to fetch python wheels/sdist.
RUN env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
      apt-get update \
    && env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
      apt-get install -y --no-install-recommends \
      build-essential \
      git \
      ninja-build \
      python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Speed / reliability knobs for pip builds
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    MAX_JOBS=8 \
    # A800 is SM80; keep it minimal to speed compilation.
    TORCH_CUDA_ARCH_LIST="8.0"

RUN python3 -m pip install --upgrade pip setuptools wheel \
    && python3 -m pip install --no-build-isolation flash-attn \
    && python3 - <<'PY'
import torch
print("torch:", torch.__version__, "| cuda:", torch.version.cuda)
import flash_attn
print("flash_attn:", flash_attn.__version__)
PY

