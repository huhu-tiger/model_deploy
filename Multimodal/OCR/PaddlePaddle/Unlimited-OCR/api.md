# Unlimited-OCR 接口文档

## 服务概览

| 项目 | 说明 |
|------|------|
| 协议 | OpenAI 兼容（vLLM） |
| 默认地址 | `http://<host>:30010` |
| 容器内端口 | `8081` |
| 模型名 | `Unlimited-OCR`（`--served-model-name`） |
| 镜像 | `vllm/vllm-openai:unlimited-ocr` |
| 模型路径 | `/media/llm/PaddlePaddle/Unlimited-OCR` |
| GPU | 第 4 号卡 |
| 官方 Recipe | [baidu/Unlimited-OCR](https://recipes.vllm.ai/baidu/Unlimited-OCR) |
| 模型主页 | [ModelScope](https://modelscope.cn/models/PaddlePaddle/Unlimited-OCR) / [Hugging Face](https://huggingface.co/baidu/Unlimited-OCR) |

### 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `GET` | `/v1/models` | 模型列表 |
| `POST` | `/v1/chat/completions` | 文档 OCR / 多页解析（主接口） |

> 本服务为 **vLLM OpenAI 兼容接口**，请求体为 JSON。图片通过 `image_url`（URL 或 Base64 data URL）传入；**不原生支持 PDF**，需先转成图片再调用。

---

## 必读约束

调用失败或返回空内容，多半是下面几条未满足：

| 规则 | 说明 |
|------|------|
| Prompt 以空格开头 | 模型无 chat template，文本须以字面空格开头，如 `" document parsing."` |
| `content` 必须含 `text` | **不能只传 `image_url`**；须同时带 Prompt 文本 |
| `skip_special_tokens=false` | 默认 `true` 会导致输出为空 |
| 注册 ngram logits processor | 服务端已通过 `--logits_processors ...NGramPerReqLogitsProcessor` 注册 |
| 请求传 `vllm_xargs` | 每请求指定 `ngram_size` / `window_size`，抑制长文档重复 |
| `model` 字段 | 固定填 `"Unlimited-OCR"` |

### Prompt 与 window_size

| 场景 | Prompt 文本 | `window_size` | 说明 |
|------|-------------|---------------|------|
| 单图（推荐） | `" document parsing."` | `128` | 本服务当前可靠路径 |
| 多页文档 | 同上，**逐页各请求一次** | `128` | 见下方「多图限制」 |
| `ngram_size` | — | 固定 `35` | 所有场景 |

> **多图限制（已实测）：** 当前 `vllm/vllm-openai:unlimited-ocr` 的 OpenAI `/v1/chat/completions`  
> 在一次请求里传多个 `image_url` 时，**只会解析第一张图**（调换顺序后始终只出「排在最前」的那张）。  
> `prompt_tokens` 虽约为双图，但生成内容不含后续页。  
> **生产请逐页调用单图接口**，客户端拼接结果。  
> 官方 Transformers `infer_multi` / 部分 SGLang 示例才支持真正的一请求多页；与本 vLLM 部署路径不同。

---

## 健康检查

```
GET /health
```

```bash
curl http://127.0.0.1:30010/health
```

成功：HTTP 200。

---

## 模型列表

```
GET /v1/models
```

```bash
curl http://127.0.0.1:30010/v1/models
```

响应中 `data[].id` 应为 `"Unlimited-OCR"`。

---

## 主接口：`POST /v1/chat/completions`

```
POST /v1/chat/completions
Content-Type: application/json
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | ✅ | 固定 `"Unlimited-OCR"` |
| `messages` | array | ✅ | OpenAI 多模态消息；`content` 含 `text` + 一个或多个 `image_url` |
| `temperature` | number | | OCR 场景建议 `0` |
| `max_tokens` | integer | | 生成上限；长文档建议 `8192` 或更大（受 `max-model-len 32768` 约束） |
| `stream` | boolean | | 是否流式；默认 `false` |
| `skip_special_tokens` | boolean | ✅ | **必须为 `false`** |
| `vllm_xargs` | object | ✅ | ngram 控制参数，见下表 |

#### `messages[].content` 结构

`content` 为数组：**第一项必须是 `text`（Prompt）**，其后为一个或多个 `image_url`。顺序：`text` → 第 1 页 → 第 2 页 → …

```json
[
  {"type": "text", "text": " document parsing."},
  {"type": "image_url", "image_url": {"url": "https://example.com/doc.png"}}
]
```

或 Base64 data URL：

```json
{"type": "image_url", "image_url": {"url": "data:image/png;base64,<BASE64>"}}
```

多图示例（注意 Prompt 与单图不同）：

```json
[
  {"type": "text", "text": " Multi page parsing."},
  {"type": "image_url", "image_url": {"url": "data:image/png;base64,<PAGE1>"}},
  {"type": "image_url", "image_url": {"url": "https://example.com/page2.png"}}
]
```

#### `vllm_xargs`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `ngram_size` | integer | ✅ | 固定 `35` |
| `window_size` | integer | ✅ | 单图 `128`；多页/PDF `1024` |

### 响应（非流式）

标准 OpenAI Chat Completions 结构。识别结果在：

```
choices[0].message.content
```

原始输出可能含 `<|det|>...<|/det|>` 版面标记，可用文末后处理函数清洗为纯文本。

---

## 调用示例

### 1. 单图 URL

```bash
curl -X POST "http://127.0.0.1:30010/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Unlimited-OCR",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": " document parsing."},
        {"type": "image_url", "image_url": {"url": "https://example.com/doc.png"}}
      ]
    }],
    "temperature": 0,
    "max_tokens": 8192,
    "skip_special_tokens": false,
    "vllm_xargs": {
      "ngram_size": 35,
      "window_size": 128
    }
  }'
```

### 2. 单图 Base64

```bash
IMG_B64=$(base64 -w 0 /path/to/doc.png)   # macOS: base64 -i

curl -X POST "http://127.0.0.1:30010/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"Unlimited-OCR\",
    \"messages\": [{
      \"role\": \"user\",
      \"content\": [
        {\"type\": \"text\", \"text\": \" document parsing.\"},
        {\"type\": \"image_url\", \"image_url\": {\"url\": \"data:image/png;base64,${IMG_B64}\"}}
      ]
    }],
    \"temperature\": 0,
    \"max_tokens\": 8192,
    \"skip_special_tokens\": false,
    \"vllm_xargs\": {
      \"ngram_size\": 35,
      \"window_size\": 128
    }
  }"
```

### 3. 多页图片（推荐：逐页请求）

> ⚠️ **不要**在一次请求里塞多个 `image_url`——当前 vLLM 服务只会返回第一张的内容（已复现）。  
> 多页请循环调用单图接口，再在客户端按页拼接。

```bash
# 第 1 页
IMG1=$(base64 -w 0 /path/to/page1.png)
curl -X POST "http://127.0.0.1:30010/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"Unlimited-OCR\",
    \"messages\": [{
      \"role\": \"user\",
      \"content\": [
        {\"type\": \"text\", \"text\": \" document parsing.\"},
        {\"type\": \"image_url\", \"image_url\": {\"url\": \"data:image/png;base64,${IMG1}\"}}
      ]
    }],
    \"temperature\": 0,
    \"max_tokens\": 8192,
    \"skip_special_tokens\": false,
    \"vllm_xargs\": {\"ngram_size\": 35, \"window_size\": 128}
  }"

# 第 2 页同理，换 IMG2 ...
```

### 4. Python（OpenAI SDK）

```python
import base64
from openai import OpenAI

client = OpenAI(api_key="EMPTY", base_url="http://127.0.0.1:30010/v1", timeout=1200)


def to_data_url(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower()
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"


def ocr_single(image_path: str) -> str:
    resp = client.chat.completions.create(
        model="Unlimited-OCR",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": " document parsing."},
                {"type": "image_url", "image_url": {"url": to_data_url(image_path)}},
            ],
        }],
        temperature=0,
        max_tokens=8192,
        extra_body={
            "skip_special_tokens": False,
            "vllm_xargs": {"ngram_size": 35, "window_size": 128},
        },
    )
    return resp.choices[0].message.content


def ocr_multi(image_paths: list[str]) -> str:
    """逐页单图请求后拼接。勿一次传多张 image_url（当前 vLLM 只会解析第一张）。"""
    parts = [ocr_single(p) for p in image_paths]
    return "\n\n".join(p for p in parts if p)


print(ocr_single("page.png"))
print(ocr_multi(["page1.png", "page2.png"]))
```

### 5. PDF → 多页解析

服务端不直接收 PDF。先用 PyMuPDF 转图，再**逐页**调单图接口：

```python
import os
import tempfile
import fitz  # pymupdf


def pdf_to_images(pdf_path: str, dpi: int = 300) -> list[str]:
    doc = fitz.open(pdf_path)
    tmp_dir = tempfile.mkdtemp(prefix="pdf_ocr_")
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    paths = []
    for i, page in enumerate(doc):
        out = os.path.join(tmp_dir, f"page_{i + 1:04d}.png")
        page.get_pixmap(matrix=mat).save(out)
        paths.append(out)
    doc.close()
    return paths


# 配合上文 ocr_multi()
text = ocr_multi(pdf_to_images("your_doc.pdf", dpi=300))
print(text)
```

---

## 输出后处理（可选）

原始结果可能带 `<|det|>type [bbox]<|/det|>` 标记。评估或只要纯文本时可剥离：

```python
import re

DET_RE = re.compile(
    r"<\|det\|>([^<\s]+)(?:\s*\[[^\]]*\])?\s*<\|/det\|>(.*)",
    re.DOTALL,
)


def remove_det(raw: str) -> str:
    """去掉 det 标记，同块用换行、不同块用空行分隔。"""
    blocks = []
    cur = None
    for line in raw.splitlines():
        line = line.rstrip()
        if not line:
            continue
        m = DET_RE.match(line)
        if m:
            category, content = m.group(1).strip(), m.group(2).strip()
            if category == "image":
                continue
            if cur is not None:
                blocks.append(cur)
            cur = [content] if content else []
            continue
        if cur is None:
            cur = []
        cur.append(line)
    if cur is not None:
        blocks.append(cur)
    return "\n\n".join("\n".join(b) for b in blocks).strip()
```

---

## 启动 / 停止

```bash
cd /media/source/model_deploy/Multimodal/OCR/PaddlePaddle/Unlimited-OCR

docker compose pull
docker compose up -d
docker compose logs -f
docker compose down
```

---

## 常见问题

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| `content` 为空 | 未设 `skip_special_tokens=false` | 请求体显式传 `false` |
| **多图只返回第一张** | 当前 vLLM OpenAI 路径的已知限制（即使带 `" Multi page parsing."` + `window_size=1024` 也一样） | **逐页单图请求**后客户端拼接；勿依赖一次多 `image_url` |
| 长文重复 / 卡在 det 标记 | 未传 `vllm_xargs` 或 `window_size` 不对 | 单图用 `128`；`ngram_size=35` |
| 模型报错 / 效果差 | Prompt 未以空格开头 | 使用 `" document parsing."` |
| PDF 无法解析 | 接口不收 PDF | 先转 PNG，再逐页单图请求 |
| 超时 | 多页 / 高 DPI 耗时长 | 客户端 `timeout` 加大（如 1200s）；适当降低 DPI 或分页批处理 |
