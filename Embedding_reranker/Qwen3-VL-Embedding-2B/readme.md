# Qwen3-VL-Embedding-2B 接口文档

多模态 Embedding 服务，支持**纯文本、图片、视频及图文/视频混合**输入，输出 L2 归一化向量，可用于检索、聚类、相似度计算。

提供两种推理后端，**接口不完全相同**，请按实际部署选择对应章节：

| 后端 | 配置文件 | 默认端口 | 启动命令 |
|------|----------|----------|----------|
| **vLLM** | `docker-compose.yml` | **8018** | `docker compose up -d` |
| **SGLang** | `docker-compose-sglang.yml` | **6009**（映射至容器 8019） | `docker compose -f docker-compose-sglang.yml up -d` |

> 两版默认共用 GPU 0，**勿同时启动**；A/B 对比时需改 `device_ids` 或分时运行。

## 服务信息

| 项 | vLLM | SGLang |
|---|---|---|
| 模型名 | `Qwen3-VL-Embedding-2B` | 同左 |
| 默认地址 | `http://<host>:8018` | `http://<host>:6009` |
| 镜像 | `vllm-openai:v0.24.0` | `sglang:v0.5.13.post1` |
| 权重路径 | `/media/llm/Qwen/Qwen3-VL-Embedding-2B` | 同左 |
| 上下文长度 | 8192（改 `--max-model-len 32768` 可达 32K） | 8192（改 `--context-length 32768`） |
| 向量维度 | 64 ~ 2048（MRL 截断） | 同左 |
| 单请求限制 | 最多 **2** 张图片、**1** 段视频 | 同左 |

---

## vLLM 与 SGLang 接口差异

| 场景 | vLLM (8018) | SGLang (6009) |
|------|-------------|---------------|
| 纯文本 | `input`: string / string[] | **相同** |
| 多模态 | `messages`（Chat 格式 + `image_url`） | `input`: 结构化对象数组（见下文） |
| `continue_final_message` | 多模态**建议传** | **不支持，勿传** |
| `add_special_tokens` | 多模态**建议传** | **不支持，勿传** |
| Instruction | 写在 `messages` 的 `system` 角色 | 写在 `input` 的 `text` 字段 |
| `POST /pooling` | 支持 | **不支持** |
| 响应格式 | OpenAI Embeddings 兼容 | 同左 |

SGLang 在服务端通过 `--chat-template chat_template.jinja` 自动渲染 prompt（含 `add_generation_prompt`），客户端无需传 vLLM 专有参数。

---

## 端点一览

| 方法 | 路径 | vLLM | SGLang | 说明 |
|------|------|:----:|:------:|------|
| `POST` | `/v1/embeddings` | ✓ | ✓ | 生成 Embedding（主接口） |
| `POST` | `/pooling` | ✓ | — | vLLM 通用 Pooling（`task=embed`） |
| `GET` | `/v1/models` | ✓ | ✓ | 查询已注册模型 |
| `GET` | `/health` | ✓ | ✓ | 健康检查 |

---

## 公共响应格式

两种后端 `/v1/embeddings` 响应结构一致：

```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "index": 0,
      "embedding": [0.0123, -0.0456, "..."]
    }
  ],
  "model": "Qwen3-VL-Embedding-2B",
  "usage": {
    "prompt_tokens": 28,
    "total_tokens": 28
  }
}
```

公共请求参数：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | 是 | 固定为 `Qwen3-VL-Embedding-2B` |
| `encoding_format` | string | 否 | `float`（默认）或 `base64` |
| `dimensions` | integer | 否 | MRL 输出维度，范围 64~2048 |

---

# vLLM 接口（端口 8018）

## 1. 纯文本 Embedding

兼容 OpenAI Embeddings API，使用 `input` 字段。

```http
POST /v1/embeddings
Content-Type: application/json
```

```json
{
  "model": "Qwen3-VL-Embedding-2B",
  "input": [
    "Represent the user query for retrieval.",
    "A woman playing with her dog on a beach at sunset."
  ],
  "encoding_format": "float"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `input` | string \| string[] | 是* | 纯文本；与 `messages` 二选一 |
| `messages` | object \| object[] | 是* | 多模态 chat 格式；与 `input` 二选一 |

```bash
curl -s http://127.0.0.1:8018/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "Qwen3-VL-Embedding-2B",
    "input": ["你好，世界", "Hello, world"],
    "encoding_format": "float"
  }'
```

---

## 2. 多模态 Embedding（图片 / 图文）

多模态请求须使用 **`messages`** 字段，并建议带上空的 `assistant` 消息（配合 `continue_final_message=true`）以获得正确向量：

```json
{
  "model": "Qwen3-VL-Embedding-2B",
  "messages": [
    {
      "role": "system",
      "content": [{"type": "text", "text": "Represent the user's input."}]
    },
    {
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "https://example.com/demo.jpeg"}},
        {"type": "text", "text": ""}
      ]
    },
    {
      "role": "assistant",
      "content": [{"type": "text", "text": ""}]
    }
  ],
  "encoding_format": "float",
  "continue_final_message": true,
  "add_special_tokens": true
}
```

Query 侧可在 `system` 消息中指定任务指令（**doc 侧可省略**）：

```json
{
  "model": "Qwen3-VL-Embedding-2B",
  "messages": [
    {
      "role": "system",
      "content": [{"type": "text", "text": "Retrieve images or text relevant to the user's query."}]
    },
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "A woman playing with her dog on a beach at sunset."}
      ]
    }
  ],
  "encoding_format": "float"
}
```

### 图片 URL 格式（vLLM）

| 类型 | 示例 |
|------|------|
| HTTP/HTTPS | `"url": "https://example.com/image.jpg"` |
| Base64 | `"url": "data:image/jpeg;base64,/9j/4AAQ..."` |
| 本地文件 | 服务端可访问时使用 `"url": "file:///media/llm/..."` |

### curl 示例（vLLM 图文）

```bash
curl -s http://127.0.0.1:8018/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d @- <<'EOF'
{
  "model": "Qwen3-VL-Embedding-2B",
  "messages": [
    {
      "role": "system",
      "content": [{"type": "text", "text": "Represent the user's input."}]
    },
    {
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen-VL/assets/demo.jpeg"}},
        {"type": "text", "text": ""}
      ]
    },
    {
      "role": "assistant",
      "content": [{"type": "text", "text": ""}]
    }
  ],
  "encoding_format": "float",
  "continue_final_message": true,
  "add_special_tokens": true
}
EOF
```

> 若用 Postman / Apifox 等工具，直接复制 `{}` 内 JSON 即可，**不要**带 bash 的 `'\''` 转义。

---

## 3. 视频 Embedding（vLLM）

单请求最多 **1** 段视频，通过 `messages` + `video_url` 传入：

```json
{
  "model": "Qwen3-VL-Embedding-2B",
  "messages": {
    "role": "user",
    "content": [
      {"type": "text", "text": "Describe the video content."},
      {"type": "video_url", "video_url": {"url": "https://example.com/demo.mp4"}}
    ]
  },
  "encoding_format": "float"
}
```

> 视频/图片拉取超时由环境变量 `VLLM_VIDEO_FETCH_TIMEOUT`（默认 120s）、`VLLM_IMAGE_FETCH_TIMEOUT`（默认 60s）控制。

---

## 4. MRL 自定义维度（vLLM）

```json
{
  "model": "Qwen3-VL-Embedding-2B",
  "input": "Short text for embedding.",
  "dimensions": 512,
  "encoding_format": "float"
}
```

---

## 5. Pooling API（vLLM 备选）

```bash
curl -s http://127.0.0.1:8018/pooling \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "Qwen3-VL-Embedding-2B",
    "input": ["Hello", "World"],
    "task": "embed"
  }'
```

---

# SGLang 接口（端口 6009）

SGLang 统一使用 **`input`** 字段。纯文本与 vLLM 相同；多模态使用**结构化对象数组**，**不要**传 `messages`、`continue_final_message`、`add_special_tokens`。

## 1. 纯文本 Embedding

与 vLLM 完全相同，仅改端口：

```bash
curl -s http://127.0.0.1:6009/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "Qwen3-VL-Embedding-2B",
    "input": ["你好，世界", "Hello, world"],
    "encoding_format": "float"
  }'
```

---

## 2. 多模态 Embedding（图片 / 图文）

`input` 为对象数组，每个对象可含 `text`、`image`、`video` 字段（至少一个）：

```json
{
  "model": "Qwen3-VL-Embedding-2B",
  "input": [
    {"text": "Represent the user's input."},
    {"image": "https://example.com/demo.jpeg"}
  ],
  "encoding_format": "float"
}
```

图文合并为单个对象：

```json
{
  "model": "Qwen3-VL-Embedding-2B",
  "input": [
    {
      "text": "A woman playing with her dog on a beach at sunset.",
      "image": "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen-VL/assets/demo.jpeg"
    }
  ],
  "encoding_format": "float"
}
```

带检索 instruction 的 query 示例（instruction 写在 `text` 中）：

```json
{
  "model": "Qwen3-VL-Embedding-2B",
  "input": [
    {
      "text": "Retrieve images or text relevant to the user's query.\nA woman playing with her dog on a beach at sunset."
    }
  ],
  "encoding_format": "float"
}
```

批量 embedding（多条 input，每条可独立含 text/image）：

```json
{
  "model": "Qwen3-VL-Embedding-2B",
  "input": [
    {"text": "A woman playing with her dog on a beach at sunset."},
    {"text": "Pet owner training dog outdoors near water."},
    {"image": "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen-VL/assets/demo.jpeg"},
    {
      "text": "A woman shares a joyful moment with her golden retriever.",
      "image": "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen-VL/assets/demo.jpeg"
    }
  ],
  "encoding_format": "float"
}
```

### 媒体 URL 格式（SGLang）

| 类型 | 字段 | 示例 |
|------|------|------|
| HTTP/HTTPS 图片 | `image` | `"https://example.com/image.jpg"` |
| Base64 图片 | `image` | `"data:image/jpeg;base64,/9j/4AAQ..."` |
| 本地文件 | `image` | `"/media/llm/path/to/image.jpg"` 或 `"file:///media/llm/..."` |
| HTTP/HTTPS 视频 | `video` | `"https://example.com/demo.mp4"` |

### curl 示例（SGLang 图文）

```bash
curl -s http://127.0.0.1:6009/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d @- <<'EOF'
{
  "model": "Qwen3-VL-Embedding-2B",
  "input": [
    {"text": "Represent the user's input."},
    {"image": "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen-VL/assets/demo.jpeg"}
  ],
  "encoding_format": "float"
}
EOF
```

---

## 3. 视频 Embedding（SGLang）

单请求最多 **1** 段视频，使用 `video` 字段：

```json
{
  "model": "Qwen3-VL-Embedding-2B",
  "input": [
    {
      "text": "Describe the video content.",
      "video": "https://example.com/demo.mp4"
    }
  ],
  "encoding_format": "float"
}
```

---

## 4. MRL 自定义维度（SGLang）

```json
{
  "model": "Qwen3-VL-Embedding-2B",
  "input": [{"text": "Short text for embedding."}],
  "dimensions": 512,
  "encoding_format": "float"
}
```

---

# 通用说明

## 相似度计算

向量已 L2 归一化时，**余弦相似度 = 向量点积**：

```python
import numpy as np

score = np.dot(query_emb, doc_emb)
```

检索典型流程：

1. **Query**（文本/图片/混合）加 task-specific instruction
2. **Document** 一般不加 instruction，或仅用默认 `"Represent the user's input."`
3. 对 query 向量与 doc 向量做点积排序

## 查询模型信息

```bash
# vLLM
curl -s http://127.0.0.1:8018/v1/models | python3 -m json.tool

# SGLang
curl -s http://127.0.0.1:6009/v1/models | python3 -m json.tool
```

## Python 调用示例

### vLLM

```python
import requests
import numpy as np

BASE = "http://127.0.0.1:8018"
MODEL = "Qwen3-VL-Embedding-2B"

def embed_text(texts: list[str]) -> list[list[float]]:
    r = requests.post(
        f"{BASE}/v1/embeddings",
        json={"model": MODEL, "input": texts, "encoding_format": "float"},
        timeout=120,
    )
    r.raise_for_status()
    data = sorted(r.json()["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in data]

def embed_multimodal(messages) -> list[float]:
    r = requests.post(
        f"{BASE}/v1/embeddings",
        json={
            "model": MODEL,
            "messages": messages,
            "encoding_format": "float",
            "continue_final_message": True,
            "add_special_tokens": True,
        },
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]

vecs = embed_text(["Retrieve relevant passages.", "The capital of China is Beijing."])

img_vec = embed_multimodal([
    {"role": "system", "content": [{"type": "text", "text": "Represent the user's input."}]},
    {"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "https://example.com/cat.jpg"}},
        {"type": "text", "text": "A cat sitting on a windowsill."},
    ]},
    {"role": "assistant", "content": [{"type": "text", "text": ""}]},
])

print("text similarity:", np.dot(vecs[0], vecs[1]))
```

### SGLang

```python
import requests
import numpy as np

BASE = "http://127.0.0.1:6009"
MODEL = "Qwen3-VL-Embedding-2B"

def embed_text(texts: list[str]) -> list[list[float]]:
    r = requests.post(
        f"{BASE}/v1/embeddings",
        json={"model": MODEL, "input": texts, "encoding_format": "float"},
        timeout=120,
    )
    r.raise_for_status()
    data = sorted(r.json()["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in data]

def embed_multimodal(text: str, image: str | None = None) -> list[float]:
    item: dict = {"text": text}
    if image:
        item["image"] = image
    r = requests.post(
        f"{BASE}/v1/embeddings",
        json={"model": MODEL, "input": [item], "encoding_format": "float"},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]

vecs = embed_text(["Retrieve relevant passages.", "The capital of China is Beijing."])

img_vec = embed_multimodal(
    "Represent the user's input.",
    "https://example.com/cat.jpg",
)

print("text similarity:", np.dot(vecs[0], vecs[1]))
```

---

## 错误码

| HTTP 状态 | 常见原因 |
|-----------|----------|
| `400` | JSON 格式错误、缺少 `model`/`input`（或 vLLM 多模态缺少 `messages`） |
| `404` | `model` 名称与服务端 `--served-model-name` 不一致 |
| `413` / context 相关 | 输入超长，超过 context 上限 |
| `422` | 多模态格式不合法（如图片 URL 无法拉取） |
| `500` | 服务内部错误（OOM、模型加载失败等） |

---

## 注意事项

1. **`model` 名称**须与 compose 中 `--served-model-name` 完全一致：`Qwen3-VL-Embedding-2B`。
2. **vLLM**：纯文本用 `input`；多模态用 `messages`。**SGLang**：纯文本和多模态均用 `input`（多模态为对象数组）。
3. **Instruction**：检索类 query 建议写英文任务描述，可提升 1%~5% 效果；document 侧通常用默认 `"Represent the user's input."` 即可。
4. **并发**：2B 模型单卡即可；高并发时注意 GPU 显存与 batch 配置。
5. **vLLM 版本**：需 >= 0.14（当前镜像 `v0.24.0`）。
6. **SGLang 版本**：当前镜像 `v0.5.13.post1`；启动须带 `--is-embedding` 与 `--chat-template .../chat_template.jinja`。

---

## 参考

- 模型 README：`/media/llm/Qwen/Qwen3-VL-Embedding-2B/README.md`
- vLLM Pooling 文档：https://docs.vllm.ai/en/stable/models/pooling_models.html
- SGLang Embedding 文档：https://docs.sglang.io/basic_usage/openai_api_embeddings.html
- 官方示例：https://github.com/QwenLM/Qwen3-VL-Embedding/tree/main/examples
