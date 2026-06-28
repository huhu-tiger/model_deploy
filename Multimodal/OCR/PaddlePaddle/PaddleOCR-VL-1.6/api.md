# PaddleOCR-VL-1.6 接口文档

## 服务概览

| 端口 | 容器 | 协议 | 适用场景 |
|---|---|---|---|
| `30008` | paddleocr-vl-api | PaddleX 专有 | 完整文档解析：版面检测 + OCR + 结构化输出 |
| `30009` | paddleocr-vlm-server | **OpenAI 兼容** | 轻量 VLM 推理，直连 vLLM，支持自定义 prompt |

> **30009 说明**：`paddleocr-vlm-server` 内部使用 `vllm.entrypoints.openai.api_server`，
> 是标准 vLLM OpenAI 实现，支持所有 `/v1/*` 标准端点。
> 两个容器均由 `docker-compose-baidu.yml` 启动。

---

## 选择哪个接口？

| | `30008 /layout-parsing` | `30009 /v1/chat/completions` |
|---|---|---|
| **PDF 输入** | ✅ 原生支持 | ❌ 需先转为图片 |
| **图片输入** | ✅ URL 或 Base64 | ✅ URL 或 Base64 |
| **版面分析** | ✅ 自动（PP-DocLayoutV3）| ❌ |
| **输出格式** | 结构化 JSON（坐标 + 分类 + 文本）| 纯文本 |
| **自定义 prompt** | ❌ | ✅ |
| **适用场景** | 文档归档、坐标提取、Markdown 导出 | 自定义 OCR、问答、对话 |

---

## 公共说明：文件转 Base64

所有接口均通过 JSON body 传文件，不支持 multipart form。

**Linux**
```bash
# 图片
FILE_B64=$(base64 -w 0 /path/to/image.png)
# PDF
PDF_B64=$(base64 -w 0 /path/to/document.pdf)
```

**macOS**（`base64` 不支持 `-w`，用 `-i` 即可）
```bash
FILE_B64=$(base64 -i /path/to/image.png)
PDF_B64=$(base64 -i /path/to/document.pdf)
```

**Python（跨平台）**
```python
import base64

with open("/path/to/file", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()
```

**Shell 单行（跨平台）**
```bash
FILE_B64=$(python3 -c "import base64; print(base64.b64encode(open('/path/to/file','rb').read()).decode())")
```

---

## 接口一：`POST /layout-parsing`（端口 30008）

文档版面解析 + OCR 全流程，支持图片和 PDF。

### 健康检查

```bash
curl http://localhost:30008/health
```

### 请求参数

```
POST /layout-parsing
Content-Type: application/json
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | string | ✅ | Base64 编码的文件内容，或可访问的公网 URL |
| `fileType` | integer | | `0` = PDF，`1` = 图片；不传时自动识别 |
| `useDocOrientationClassify` | boolean | | 启用文档方向矫正，默认 `false` |
| `useDocUnwarping` | boolean | | 启用文档畸变矫正，默认 `false` |
| `useLayoutDetection` | boolean | | 启用版面检测，默认 `true` |
| `formatBlockContent` | boolean | | 格式化块内容（表格/公式），默认 `false` |
| `visualize` | boolean | | 返回可视化标注图，默认 `true` |

### 响应结构

```json
{
  "logId": "xxx",
  "errorCode": 0,
  "result": {
    "layoutParsingResults": [
      {
        "prunedResult": {
          "markdown": "# 标题\n\n正文...",
          "parsing_res_list": [
            {
              "block_label": "text",
              "block_content": "识别出的文字",
              "block_bbox": [x1, y1, x2, y2]
            }
          ]
        },
        "outputImages": {
          "layoutImage": "<base64 PNG>",
          "ocrImage": "<base64 PNG>"
        }
      }
    ]
  }
}
```

> 每个元素对应输入的一页（PDF 多页时返回多个元素）。

### 示例：图片 URL

```bash
curl -X POST "http://localhost:30008/layout-parsing" \
  -H "Content-Type: application/json" \
  -d '{
    "file": "https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/paddleocr_vl_demo.png",
    "fileType": 1
  }'
```

### 示例：本地图片（Base64）

```bash
FILE_B64=$(base64 -w 0 /path/to/image.png)      # Linux
# FILE_B64=$(base64 -i /path/to/image.png)       # macOS

curl -X POST "http://localhost:30008/layout-parsing" \
  -H "Content-Type: application/json" \
  -d "{\"file\": \"${FILE_B64}\", \"fileType\": 1}"
```

### 示例：PDF（Base64）

```bash
PDF_B64=$(base64 -w 0 /path/to/document.pdf)    # Linux
# PDF_B64=$(base64 -i /path/to/document.pdf)     # macOS

curl -X POST "http://localhost:30008/layout-parsing" \
  -H "Content-Type: application/json" \
  -d "{\"file\": \"${PDF_B64}\", \"fileType\": 0}"
```

### Python 示例

```python
import base64, requests

BASE_URL = "http://localhost:30008"

def layout_parse(file_path: str, is_pdf: bool = False) -> dict:
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    resp = requests.post(
        f"{BASE_URL}/layout-parsing",
        json={
            "file": b64,
            "fileType": 0 if is_pdf else 1,
        },
        timeout=3600,
    )
    resp.raise_for_status()
    return resp.json()


# 图片
result = layout_parse("document.png")

# PDF
result = layout_parse("document.pdf", is_pdf=True)

# 提取文本
for page in result["result"]["layoutParsingResults"]:
    # 方式一：Markdown
    print(page["prunedResult"].get("markdown", ""))

    # 方式二：逐块
    for block in page["prunedResult"].get("parsing_res_list", []):
        print(f"[{block['block_label']}] {block.get('block_content', '')}")
```

---

## 接口二：`POST /v1/chat/completions`（端口 30009）

标准 vLLM OpenAI 兼容接口，仅支持图片输入，不支持 PDF。

### 健康检查 & 模型列表

```bash
curl http://localhost:30009/health
curl http://localhost:30009/v1/models
```

### 任务提示词

| 任务 | `text` 字段值 |
|---|---|
| 通用 OCR | `"OCR:"` |
| 表格识别 | `"Table Recognition:"` |
| 公式识别 | `"Formula Recognition:"` |
| 图表识别 | `"Chart Recognition:"` |
| 自由问答 | 任意自然语言 |

### 请求格式

```json
{
  "model": "PaddleOCR-VL-1.6-0.9B",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "image_url",
          "image_url": {"url": "<图片URL 或 data:image/png;base64,...>"}
        },
        {
          "type": "text",
          "text": "OCR:"
        }
      ]
    }
  ],
  "temperature": 0.0,
  "max_tokens": 2048
}
```

### 示例：图片 URL

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

### 示例：本地图片（Base64）

```bash
FILE_B64=$(base64 -w 0 /path/to/image.png)      # Linux
# FILE_B64=$(base64 -i /path/to/image.png)       # macOS

curl -X POST "http://localhost:30009/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"PaddleOCR-VL-1.6-0.9B\",
    \"messages\": [{
      \"role\": \"user\",
      \"content\": [
        {\"type\": \"image_url\", \"image_url\": {\"url\": \"data:image/png;base64,${FILE_B64}\"}},
        {\"type\": \"text\", \"text\": \"OCR:\"}
      ]
    }],
    \"temperature\": 0.0,
    \"max_tokens\": 2048
  }"
```

### Python 示例（openai 库）

```python
import base64
from openai import OpenAI

client = OpenAI(
    api_key="EMPTY",
    base_url="http://localhost:30009/v1",
    timeout=120,
)

MODEL = "PaddleOCR-VL-1.6-0.9B"

def ocr_url(image_url: str, task: str = "OCR:") -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": task},
            ],
        }],
        temperature=0.0,
        max_tokens=2048,
    )
    return resp.choices[0].message.content


def ocr_file(image_path: str, task: str = "OCR:") -> str:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return ocr_url(f"data:image/png;base64,{b64}", task)


# 调用示例
print(ocr_url("https://example.com/img.png"))
print(ocr_file("/path/to/table.png", task="Table Recognition:"))
print(ocr_file("/path/to/formula.png", task="Formula Recognition:"))
```

### PDF 处理（需先转图片）

> `/v1/chat/completions` **不支持 PDF**，传入 PDF 会返回 400 错误。
> 处理 PDF 推荐优先使用 `30008 /layout-parsing`（原生支持、无需额外依赖）。
> 如果必须使用 vLLM 接口，需先将 PDF 逐页转为图片。

安装依赖：
```bash
pip install pdf2image
apt-get install poppler-utils   # Linux
# brew install poppler           # macOS
```

```python
import base64, io, requests
from pdf2image import convert_from_path

def ocr_pdf_vlm(pdf_path: str, task: str = "OCR:",
                api_url: str = "http://localhost:30009") -> list[str]:
    pages = convert_from_path(pdf_path, dpi=150)
    results = []
    for i, page in enumerate(pages):
        buf = io.BytesIO()
        page.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        resp = requests.post(
            f"{api_url}/v1/chat/completions",
            json={
                "model": "PaddleOCR-VL-1.6-0.9B",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                        {"type": "text", "text": task},
                    ],
                }],
                "temperature": 0.0,
                "max_tokens": 2048,
            },
            timeout=120,
        )
        resp.raise_for_status()
        results.append(resp.json()["choices"][0]["message"]["content"])
        print(f"第 {i+1}/{len(pages)} 页完成")

    return results


pages_text = ocr_pdf_vlm("document.pdf")
for i, text in enumerate(pages_text):
    print(f"\n=== 第 {i+1} 页 ===\n{text}")
```
