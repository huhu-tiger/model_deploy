# PP-OCRv6 通用 OCR 服务化（PaddleX basic serving）
# 基础镜像使用 paddleocr-vl（CCR 无 paddlepaddle/paddleocr 仓库）
ARG PADDLEOCR_IMAGE_TAG=latest-nvidia-gpu-offline
FROM ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:${PADDLEOCR_IMAGE_TAG}

USER root

ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

RUN python -m pip install --no-cache-dir -U \
        "paddleocr>=3.7.0" \
        "paddlex>=3.7.0" && \
    paddlex --install serving

WORKDIR /deploy
