FROM model.vnet.com/sjhl/vllm-openai:v0.19.0-cu130



# ASR 音频输入依赖：vllm[audio] 关键依赖是 soundfile
# 预装系统库避免运行时缺失 libsndfile

RUN pip install vllm[audio]==0.19.0
