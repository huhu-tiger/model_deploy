# PaddleOCR-VL-1.6 部署说明

- **模型主页**：[HuggingFace - PaddlePaddle/PaddleOCR-VL](https://huggingface.co/PaddlePaddle/PaddleOCR-VL)
- **官方文档**：[PaddleOCR-VL Usage Tutorial](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html)
- **GPU**：第 7 号卡

本目录提供两种部署方案，按业务需求二选一：

---

## 方案对比

| | 方案一：官方百度（`docker-compose-baidu.yml`） | 方案二：vLLM 直连（`docker-compose.yml`） |
|---|---|---|
| **对外 API** | PaddleX 协议（`POST /layout-parsing`） | OpenAI 兼容（`POST /v1/chat/completions`） |
| **OCR 能力** | 完整 Pipeline：版面分析 + 文字识别 + 后处理 | 仅 VLM 推理，OCR 后处理需自行实现 |
| **容器数** | 2（API 网关 + VLM 推理） | 1 |
| **镜像来源** | 百度 CCR（`ccr-2vdh3abv-pub.cnc.bj.baidubce.com`） | 私有仓库（`model.vnet.com`） |
| **共享内存** | 64GB × 2 | 8GB |
| **宿主机端口** | `30008` | `30007` |
| **适用场景** | 直接对外提供 OCR 服务，开箱即用 | 集成到已有 OpenAI 生态平台 |

---

## 方案一：官方百度两容器（`docker-compose-baidu.yml`）

### 架构

```
外部请求 → paddleocr-vl-api (PaddleX Pipeline :30008)
                ↓ 内部调用
           paddleocr-vlm-server (vLLM 推理，仅内部可见)
```

### 宿主机目录结构

首次启动时，官方镜像会自动下载模型并缓存到以下宿主机目录（后续复用，无需重复下载）：

```
/media/llm/paddleocr/
├── official_models/
│   ├── PaddleOCR-VL-1.6/          VLM 推理模型（paddle 静态图，API 容器用）
│   ├── PP-DocLayoutV3/             版面分析模型
│   ├── PP-LCNet_x1_0_doc_ori/     文档方向分类模型
│   └── UVDoc/                      文档矫正模型
│   └── ...                         VLM server 下载的 HuggingFace 格式模型
└── fonts/                          渲染字体（PingFang 等）
```

两个容器共享 `official_models` 目录，同一模型不会重复下载。

### 启动 / 停止

```bash
cd /media/source/model_deploy/Multimodal/OCR/PaddlePaddle/PaddleOCR-VL-1.6

# 首次：拉取镜像
docker compose -f docker-compose-baidu.yml pull

# 启动（后台运行）
docker compose -f docker-compose-baidu.yml up -d

# 查看日志（VLM server 首次下载模型耗时较长，start_period 为 300s）
docker compose -f docker-compose-baidu.yml logs -f

# 停止
docker compose -f docker-compose-baidu.yml down
```

### 健康检查

```bash
curl -f http://localhost:30008/health
```

### API 调用

主要端点：`POST /layout-parsing`（文档版面解析 + OCR）

```bash
# curl 示例（传图片 URL）
curl -X POST "http://localhost:30008/layout-parsing" \
  -H "Content-Type: application/json" \
  -d '{
    "file": "https://example.com/document.png",
    "fileType": 1
  }'
```

```python
# Python 示例（传 base64）
import base64, requests

with open("document.png", "rb") as f:
    file_b64 = base64.b64encode(f.read()).decode("ascii")

resp = requests.post(
    "http://localhost:30008/layout-parsing",
    json={"file": file_b64, "fileType": 1},
    timeout=3600,
)
print(resp.json())
```

完整接口说明见 [官方文档 Service Deployment](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html)。

---

## 方案二：vLLM 直连（`docker-compose.yml`）

### 架构

```
外部请求 → paddleocr-vl-1.6-vllm-server (vLLM OpenAI API :30007)
```

### 宿主机目录结构

模型从宿主机直接挂载，无需下载：

```
/media/llm/PaddlePaddle/
└── PaddleOCR-VL-1.6/    HuggingFace 格式模型（直接映射进容器）
```

### 启动 / 停止

```bash
cd /media/source/model_deploy/Multimodal/OCR/PaddlePaddle/PaddleOCR-VL-1.6

# 启动
docker compose up -d

# 查看日志
docker compose logs -f

# 停止
docker compose down
```

### 健康检查

```bash
curl -f http://localhost:30007/health
```

### API 调用

兼容 OpenAI Chat Completions 协议，Base URL 为 `http://<服务器IP>:30007/v1`。

支持的任务类型（通过 `text` 字段区分）：

| 任务 | 提示词 |
|------|--------|
| 通用 OCR | `"OCR:"` |
| 表格识别 | `"Table Recognition:"` |
| 公式识别 | `"Formula Recognition:"` |
| 图表识别 | `"Chart Recognition:"` |

```bash
# curl 示例
curl -X POST "http://localhost:30007/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "PaddleOCR-VL-1.6",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}},
        {"type": "text", "text": "OCR:"}
      ]
    }],
    "temperature": 0.0
  }'
```

```python
# Python 示例
from openai import OpenAI

client = OpenAI(api_key="EMPTY", base_url="http://localhost:30007/v1", timeout=3600)

response = client.chat.completions.create(
    model="PaddleOCR-VL-1.6",
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}},
            {"type": "text", "text": "OCR:"},
        ],
    }],
    temperature=0.0,
)
print(response.choices[0].message.content)
```

---

## 注意事项

- vLLM 方案：若出现 `The model PaddleOCR-VL-1.6 does not exist.`，确认 `--served-model-name PaddleOCR-VL-1.6` 参数已生效，并在请求中 `model` 字段填写相同名称。
- 百度方案：VLM server 首次启动会下载模型，`start_period` 设置为 300s，期间 API 容器会等待其健康后再启动。
- 离线环境：百度方案镜像使用 `latest-nvidia-gpu-offline`（含模型），在线环境可改为 `latest-nvidia-gpu`。
