
# docker build
```
docker build \
  -f Multimodal/ASR/Qwen3-ASR-1.7B/Dockerfile \
  -t local/vllm-openai-audio:v0.19.0-cu130 \
  --build-arg http_proxy=http://192.168.0.2:20171 \
  --build-arg https_proxy=http://192.168.0.2:20171 \
  --build-arg no_proxy=localhost,127.0.0.1,192.168.0.0/16 \
  Multimodal/ASR/Qwen3-ASR-1.7B
```