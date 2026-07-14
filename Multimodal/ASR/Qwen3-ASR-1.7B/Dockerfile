FROM vllm/vllm-openai:v0.25.1

# ASR 音频输入依赖：官方 openai 镜像不含 optional audio（soundfile 等）
# NOTE: vLLM 版本须与基础镜像一致
RUN uv pip install --system \
    --index-url https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    vllm[audio]==0.25.1
