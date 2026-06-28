# PaddleOCR-VL-1.6 部署说明

- **模型主页**：[HuggingFace - PaddlePaddle/PaddleOCR-VL](https://huggingface.co/PaddlePaddle/PaddleOCR-VL)
- **官方文档**：[PaddleOCR-VL Usage Tutorial](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html)
- **接口文档**：[api.md](./api.md)

---

## 方案对比

| | 方案一：官方百度（`docker-compose-baidu.yml`） | 方案二：vLLM 直连（`docker-compose.yml`） |
|---|---|---|
| **容器数** | 2（API 网关 + VLM 推理） | 1 |
| **对外端口** | `30008`（PaddleX Pipeline）<br>`30009`（OpenAI 兼容，VLM 直连） | `30007`（OpenAI 兼容） |
| **GPU** | 第 3 号卡（两容器共用） | 第 7 号卡 |
| **OCR 能力** | 完整 Pipeline：版面分析 + 文字识别 + 结构化输出 | 仅 VLM 推理，需自行后处理 |
| **PDF 支持** | ✅ 原生支持 | ❌ 需先转为图片 |
| **镜像来源** | 百度 CCR（`ccr-2vdh3abv-pub.cnc.bj.baidubce.com`） | 私有仓库（`model.vnet.com`） |
| **适用场景** | 完整文档解析、开箱即用 | 集成到已有 OpenAI 生态 |

---

## 方案一：官方百度（`docker-compose-baidu.yml`）

### 架构

```
外部请求
  ├─→ paddleocr-vl-api         :30008  PaddleX Pipeline（版面 + OCR + 后处理）
  │         ↓ 内部调用
  └─→ paddleocr-vlm-server     :30009  vLLM OpenAI API（可直接外部调用）
```

两个容器均使用 **GPU 3**。VLM server 同时对外暴露 OpenAI 兼容接口（30009），
与方案二底层实现完全相同（`vllm.entrypoints.openai.api_server`）。

### 宿主机目录结构

```
PaddleOCR-VL-1.6/                        ← 当前目录
├── official_models/                      ← paddle 静态图模型缓存（.gitignore 已排除）
│   ├── PP-DocLayoutV3/                   ← 直接挂载自 /media/llm/PaddlePaddle/PP-DocLayoutV3
│   ├── PP-LCNet_x1_0_doc_ori/            ← 首次启动时自动下载
│   └── UVDoc/                            ← 首次启动时自动下载
└── fonts/                                ← 渲染字体（首次启动时自动下载，.gitignore 已排除）
```

VLM 推理模型（HuggingFace 格式）直接挂载自 `/media/llm/PaddlePaddle/PaddleOCR-VL-1.6`，无需下载。

### 启动 / 停止

```bash
cd /media/source/model_deploy/Multimodal/OCR/PaddlePaddle/PaddleOCR-VL-1.6

# 首次：拉取镜像
docker compose -f docker-compose-baidu.yml pull

# 启动（后台运行）
docker compose -f docker-compose-baidu.yml up -d

# 查看日志
docker compose -f docker-compose-baidu.yml logs -f

# 停止
docker compose -f docker-compose-baidu.yml down
```

启动耗时参考：
- `paddleocr-vlm-server`：约 1 分钟（加载本地模型）
- `paddleocr-vl-api`：约 2.5 分钟（加载版面/OCR 静态图模型）

### 健康检查

```bash
curl http://localhost:30008/health   # PaddleX Pipeline
curl http://localhost:30009/health   # vLLM OpenAI API
```

### API 调用

完整接口说明见 [api.md](./api.md)。

**方式一：PaddleX Pipeline（图片 / PDF → 结构化 JSON）**

```bash
# 图片 URL
curl -X POST "http://localhost:30008/layout-parsing" \
  -H "Content-Type: application/json" \
  -d '{"file": "https://example.com/doc.png", "fileType": 1}'

# 本地 PDF（Base64）
PDF_B64=$(base64 -w 0 /path/to/doc.pdf)   # Linux；macOS 用 base64 -i
curl -X POST "http://localhost:30008/layout-parsing" \
  -H "Content-Type: application/json" \
  -d "{\"file\": \"${PDF_B64}\", \"fileType\": 0}"
```

**方式二：OpenAI 接口直连 VLM（图片 → 文本）**

```bash
curl -X POST "http://localhost:30009/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "PaddleOCR-VL-1.6-0.9B",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}},
        {"type": "text", "text": "OCR:"}
      ]
    }],
    "temperature": 0.0,
    "max_tokens": 2048
  }'
```

---

## 方案二：vLLM 直连（`docker-compose.yml`）

### 架构

```
外部请求 → paddleocr-vl-1.6-vllm-server  :30007  vLLM OpenAI API
```

使用 **GPU 7**，模型从 `/media/llm/PaddlePaddle/PaddleOCR-VL-1.6` 直接挂载。

### 启动 / 停止

```bash
cd /media/source/model_deploy/Multimodal/OCR/PaddlePaddle/PaddleOCR-VL-1.6

docker compose up -d
docker compose logs -f
docker compose down
```

### 健康检查 & 模型列表

```bash
curl http://localhost:30007/health
curl http://localhost:30007/v1/models
```

### API 调用

```bash
curl -X POST "http://localhost:30007/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "PaddleOCR-VL-1.6-0.9B",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}},
        {"type": "text", "text": "OCR:"}
      ]
    }],
    "temperature": 0.0,
    "max_tokens": 2048
  }'
```

```python
from openai import OpenAI

client = OpenAI(api_key="EMPTY", base_url="http://localhost:30007/v1", timeout=120)

resp = client.chat.completions.create(
    model="PaddleOCR-VL-1.6-0.9B",
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}},
            {"type": "text", "text": "OCR:"},
        ],
    }],
    temperature=0.0,
    max_tokens=2048,
)
print(resp.choices[0].message.content)
```

任务提示词：`"OCR:"` / `"Table Recognition:"` / `"Formula Recognition:"` / `"Chart Recognition:"`

---

## 注意事项

- **PP-DocLayoutV3**：已从 `/media/llm/PaddlePaddle/PP-DocLayoutV3` 直接挂载，无需下载。其他版面模型（`PP-LCNet_x1_0_doc_ori`、`UVDoc`）首次触发时自动下载到 `./official_models/` 并持久化。
- **离线镜像**：方案一使用 `latest-nvidia-gpu-offline`（含内置组件），在线环境可改为 `latest-nvidia-gpu`。
- **模型名称**：调用 OpenAI 接口时 `model` 字段固定填 `"PaddleOCR-VL-1.6-0.9B"`（与 `/v1/models` 返回的 `id` 一致）。
