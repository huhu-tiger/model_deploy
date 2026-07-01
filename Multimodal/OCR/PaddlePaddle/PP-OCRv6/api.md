# PP-OCRv6 medium OCR 接口文档

## 服务概览

| 项目 | 说明 |
|------|------|
| 协议 | HTTP / JSON |
| 默认地址 | `http://<host>:9410` |
| 容器内端口 | `8080` |
| 产线 | PaddleX 通用 OCR（`PP-OCRv6_medium_det` + `PP-OCRv6_medium_rec`） |
| 官方参考 | [通用 OCR 产线 - 开发集成/部署](https://paddlepaddle.github.io/PaddleX/latest/pipeline_usage/tutorials/ocr_pipelines/OCR.html) |

### 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `POST` | `/ocr` | 通用 OCR（检测 + 识别） |

> 本服务为 **PaddleX 基础服务化**接口，非 OpenAI 兼容格式。请求体统一为 JSON，**不支持** `multipart/form-data` 上传。

---

## 公共说明

### 文件输入方式

`file` 字段支持两种形式：

1. **URL**：服务端可访问的图片或 PDF 地址（HTTP/HTTPS）
2. **Base64**：文件内容的 Base64 编码字符串（本地文件需先编码）

```bash
# Linux
IMG_B64=$(base64 -w 0 /path/to/image.jpg)
PDF_B64=$(base64 -w 0 /path/to/document.pdf)

# macOS
IMG_B64=$(base64 -i /path/to/image.jpg)
```

### 支持的文件类型

| fileType | 含义 |
|----------|------|
| `0` | PDF |
| `1` | 图片（含 PNG/JPG/BMP/TIFF 等） |

- 传 URL 时可省略 `fileType`，按后缀自动推断
- 传 Base64 时**建议显式指定** `fileType`

### PDF 页数限制

默认 PDF / 多页 TIFF **仅处理前 10 页**。当前部署已在产线配置中设置 `Serving.extra.max_num_input_imgs: null`，**无页数上限**。

### 当前部署默认行为

| 配置项 | 值 | 说明 |
|--------|-----|------|
| 文档预处理 | 关闭 | 无方向矫正、畸变矫正 |
| 文本行方向分类 | 关闭 | 无竖排/旋转行矫正 |
| 响应可视化图 | 关闭 | `Serving.visualize: false`，响应体更小 |

---

## 健康检查

```
GET /health
```

### 请求示例

```bash
curl http://127.0.0.1:9410/health
```

### 成功响应（HTTP 200）

```json
{
  "logId": "ea1903d4-cda7-4055-b1ca-732b590602c9",
  "errorCode": 0,
  "errorMsg": "Healthy"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `logId` | string | 请求 UUID |
| `errorCode` | integer | `0` 表示健康 |
| `errorMsg` | string | `"Healthy"` |

---

## OCR 识别

```
POST /ocr
Content-Type: application/json
```

对输入图片或 PDF 执行 **文本检测 + 文本识别**，返回每页/每张图的文本框与识别结果。

### 请求参数

除 `file` 外均为可选；不传时使用服务实例化时的默认值。传 `null` 表示沿用配置文件默认值。

#### 输入

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `file` | string | ✅ | — | 图片/PDF 的 **URL** 或 **Base64** 编码内容 |
| `fileType` | integer \| null | | 自动推断 | `0`=PDF，`1`=图片 |

#### 文档预处理（当前部署默认关闭）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `useDocOrientationClassify` | boolean \| null | `false` | 文档方向分类（0°/90°/180°/270°） |
| `useDocUnwarping` | boolean \| null | `false` | 文档畸变矫正（UVDoc） |

> 扫描件场景可在请求中设为 `true`，但需在产线配置中启用 `use_doc_preprocessor` 及对应子模型，否则无效。

#### 文本行方向（当前部署默认关闭）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `useTextlineOrientation` | boolean \| null | `false` | 文本行方向分类（竖排/旋转文本行） |

#### 检测参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `textDetLimitSideLen` | integer \| null | `64` | 检测图像边长限制（>0） |
| `textDetLimitType` | string \| null | `"min"` | 边长限制类型：`min`（最短边不小于限制值）/ `max`（最长边不大于限制值） |
| `textDetThresh` | number \| null | `0.3` | 文本像素置信度阈值 |
| `textDetBoxThresh` | number \| null | `0.6` | 文本框置信度阈值 |
| `textDetUnclipRatio` | number \| null | `1.5` | 检测框膨胀系数 |

#### 识别参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `textRecScoreThresh` | number \| null | `0.0` | 识别结果过滤阈值，低于此值的文本行丢弃 |
| `returnWordBox` | boolean \| null | `false` | 是否返回每个字的坐标 |

#### 响应控制

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `visualize` | boolean \| null | `false` | 是否返回可视化图像（Base64 JPEG）。生产环境建议 `false` 以减小响应体 |

---

### 请求示例

**图片 URL（推荐快速测试）**

```bash
curl -X POST "http://127.0.0.1:9410/ocr" \
  -H "Content-Type: application/json" \
  -d '{
    "file": "https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/general_ocr_002.png",
    "visualize": false,
    "useDocOrientationClassify": false,
    "useDocUnwarping": false,
    "useTextlineOrientation": false
  }'
```

**本地图片 Base64**

```bash
IMG_B64=$(base64 -w 0 ./test.jpg)
curl -X POST "http://127.0.0.1:9410/ocr" \
  -H "Content-Type: application/json" \
  -d "{\"file\": \"${IMG_B64}\", \"fileType\": 1, \"visualize\": false}"
```

**本地 PDF Base64**

```bash
PDF_B64=$(base64 -w 0 ./document.pdf)
curl -X POST "http://127.0.0.1:9410/ocr" \
  -H "Content-Type: application/json" \
  -d "{\"file\": \"${PDF_B64}\", \"fileType\": 0, \"visualize\": false}"
```

**Python**

```python
import base64
import requests

API_URL = "http://127.0.0.1:9410/ocr"

with open("test.jpg", "rb") as f:
    file_b64 = base64.b64encode(f.read()).decode("ascii")

resp = requests.post(
    API_URL,
    json={
        "file": file_b64,
        "fileType": 1,
        "visualize": False,
        "useDocOrientationClassify": False,
        "useDocUnwarping": False,
        "useTextlineOrientation": False,
    },
    timeout=120,
)
resp.raise_for_status()

data = resp.json()
for i, page in enumerate(data["result"]["ocrResults"]):
    pruned = page["prunedResult"]
    for text, score in zip(pruned["rec_texts"], pruned["rec_scores"]):
        print(f"[{score:.3f}] {text}")
```

---

### 成功响应（HTTP 200）

```json
{
  "logId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "errorCode": 0,
  "errorMsg": "Success",
  "result": {
    "ocrResults": [
      {
        "prunedResult": { },
        "ocrImage": null,
        "docPreprocessingImage": null,
        "inputImage": null
      }
    ],
    "dataInfo": { }
  }
}
```

#### 顶层字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `logId` | string | 请求 UUID |
| `errorCode` | integer | `0` 表示成功 |
| `errorMsg` | string | `"Success"` |
| `result` | object | 业务结果 |

#### `result` 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `ocrResults` | array | OCR 结果列表。单张图片长度为 1；PDF 每页一个元素 |
| `dataInfo` | object | 输入数据元信息 |

#### `ocrResults[]` 元素

| 字段 | 类型 | 说明 |
|------|------|------|
| `prunedResult` | object | OCR 核心结果（见下表） |
| `ocrImage` | string \| null | 标注检测框的结果图（JPEG Base64）；`visualize=false` 时为 `null` |
| `docPreprocessingImage` | string \| null | 文档预处理可视化图；未启用预处理时为 `null` |
| `inputImage` | string \| null | 输入图（JPEG Base64）；`visualize=false` 时为 `null` |

#### `prunedResult` 主要字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `model_settings` | object | 本次推理使用的模块开关 |
| `dt_polys` | array | 检测多边形框，每个框 4 顶点 `[[x,y],...]` |
| `dt_scores` | array[float] | 各检测框置信度 |
| `text_det_params` | object | 实际使用的检测参数 |
| `rec_texts` | array[string] | 识别文本列表（按检测框顺序） |
| `rec_scores` | array[float] | 各文本行识别置信度 |
| `rec_polys` | array | 过滤后的文本框多边形 |
| `rec_boxes` | array | 矩形框 `[x_min, y_min, x_max, y_max]` |
| `textline_orientation_angles` | array[int] | 文本行方向角；未启用时为 `-1` |
| `text_rec_score_thresh` | float | 识别过滤阈值 |
| `text_word` | array \| null | 单字文本（`returnWordBox=true` 时） |
| `text_word_boxes` | array \| null | 单字坐标（`returnWordBox=true` 时） |

**解析示例：提取全部文本**

```python
result = response.json()["result"]
for page in result["ocrResults"]:
    texts = page["prunedResult"]["rec_texts"]
    print("\n".join(texts))
```

**解析示例：文本 + 坐标**

```python
for page in result["ocrResults"]:
    pruned = page["prunedResult"]
    for text, box, score in zip(
        pruned["rec_texts"],
        pruned["rec_boxes"],
        pruned["rec_scores"],
    ):
        print(f"{text}\t{score:.3f}\tbox={box}")
```

---

### 错误响应

请求失败时 HTTP 状态码非 200，响应体示例：

```json
{
  "logId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "errorCode": 422,
  "errorMsg": "具体错误信息"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `errorCode` | integer | 与 HTTP 状态码一致 |
| `errorMsg` | string | 错误描述 |

常见原因：

| 场景 | 说明 |
|------|------|
| `file` 无效 | Base64 解码失败、URL 不可达 |
| 文件类型不支持 | 格式不在支持列表内 |
| 服务未就绪 | 模型加载中，稍后重试 `/health` |

---

## 与 PaddleOCR-VL 的区别

| | PP-OCRv6（本服务 `:9410`） | PaddleOCR-VL（`:30008`） |
|---|---|---|
| 能力 | 文字检测 + 识别 | 版面分析 + VLM 结构化解析 |
| 端点 | `POST /ocr` | `POST /layout-parsing` |
| PDF | ✅ | ✅ |
| 表格/公式结构化 | ❌ | ✅ |
| 适用场景 | 通用 OCR、文字抽取 | 文档解析、Markdown 归档 |

---

## 运维

```bash
# 健康检查
curl http://127.0.0.1:9410/health

# 一键测试（项目目录）
make test

# 查看日志
make logs
```

部署说明见 [readme.md](./readme.md)。
