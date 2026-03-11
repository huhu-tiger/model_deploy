# vLLM 图像编辑 API 使用文档

本文档基于 [vLLM-Omni Image Edit API](https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/image_edit_api/) 编写。

## 启动服务器

使用以下命令启动 vLLM 服务器：

```bash
vllm serve Qwen/Qwen-Image-Edit-2511 --omni --port 8000
```

参数说明：
- `Qwen/Qwen-Image-Edit-2511`: 模型名称
- `--omni`: 启用多模态支持
- `--port 8000`: 指定服务端口（默认 8000）

## API 端点

```
POST /v1/images/edits
Content-Type: multipart/form-data
```

## 请求参数

### 必需参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `prompt` | string | 图像编辑的文本描述，说明想要进行的修改 |
| `image` 或 `url` | file/string | 要编辑的图像文件或图像 URL |

### 可选参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `size` | string | "auto" | 输出图像尺寸，如 "1024x1024"、"512x512" |
| `n` | integer | 1 | 生成图像数量（1-10） |
| `output_format` | string | "png" | 输出格式："png"、"jpg"、"jpeg" 或 "webp" |
| `num_inference_steps` | integer | - | 扩散模型推理步数，步数越多质量越高但速度越慢 |
| `guidance_scale` | float | - | 分类器自由引导强度，控制生成结果与提示词的贴合度 |
| `seed` | integer | - | 随机种子，用于生成可复现的结果 |
| `negative_prompt` | string | - | 负面提示词，描述不希望出现在输出中的内容 |

## 响应格式

API 返回 JSON 格式的响应，包含 base64 编码的图像数据：

```json
{
  "created": 1701234567,
  "data": [
    {
      "b64_json": "<base64编码的图像数据>",
      "url": null,
      "revised_prompt": null
    }
  ]
}
```

响应字段说明：
- `created`: Unix 时间戳
- `data`: 图像数据数组
  - `b64_json`: Base64 编码的图像数据
  - `url`: 图像 URL（当前为 null）
  - `revised_prompt`: 修订后的提示词（当前为 null）

## 请求示例

### Python (OpenAI SDK) - 本地文件

```python
import base64
from openai import OpenAI

# 初始化客户端
client = OpenAI(
    api_key="None",  # vLLM 不需要 API key
    base_url="http://localhost:8000/v1"
)

# 发送图像编辑请求（本地文件）
result = client.images.edit(
    image=open("input.jpg", "rb"),  # 本地图像文件
    model="Qwen-Image-Edit-2511",
    prompt="将背景改为蓝天白云",
    size="512x512",
    output_format="jpeg",
    extra_body={
        "num_inference_steps": 50,
        "seed": 777,
        "guidance_scale": 7.5,
        # Qwen 官方建议：negative_prompt 传入空白字符串（而不是省略字段）
        "negative_prompt": " "
    }
)

# 保存结果
image_data = base64.b64decode(result.data[0].b64_json)
with open("output.jpg", "wb") as f:
    f.write(image_data)
```

### Python (OpenAI SDK) - URL 格式

```python
import base64
from openai import OpenAI

client = OpenAI(
    api_key="None",
    base_url="http://localhost:8000/v1"
)

input_image_url1 = "https://example.com/image1.png"
input_image_url2 = "https://example.com/image2.png"

# 使用 URL 格式的图像输入（支持多张图像）
result = client.images.edit(
    image=[],  # 使用 URL 时 image 参数为空列表
    model="Qwen-Image-Edit-2511",
    prompt="Change the bears in the two input images into walking together.",
    size="512x512",
    stream=False,
    output_format="jpeg",
    extra_body={
        "url": [input_image_url1, input_image_url2],  # URL 列表
        "num_inference_steps": 50,
        "guidance_scale": 1,
        "seed": 777,
        # Qwen 官方建议：negative_prompt 传入空白字符串（而不是省略字段）
        "negative_prompt": " ",
    }
)

# 保存结果
image_base64 = result.data[0].b64_json
image_bytes = base64.b64decode(image_base64)
with open("edit_out_http.jpeg", "wb") as f:
    f.write(image_bytes)
```

### cURL - 本地文件

```bash
curl --location --request POST 'http://39.155.179.4:9121/v1/images/edits' \
--header 'Authorization: Bearer tk-OvOx9M2qhHxYHcO8SQJdAkFVHVnf1tUD' \
--form 'image=@"C:\\Users\\tao.jun\\Downloads\\864d038a61884653a452f7d82e855ac9.png"' \
--form 'prompt="改成两只小猫"' \
--form 'size="512x512"' \
--form 'output_format="jpeg"' \
--form 'num_inference_steps="10"' \
--form 'guidance_scale="7.5"' \
--form 'negative_prompt=" "' \
--form 'seed="777"' \
--form 'n="1"'
```

### cURL - URL 格式（多图像）

```bash
curl -X POST http://localhost:8000/v1/images/edits \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen-Image-Edit-2511",
    "prompt": "Change the bears in the two input images into walking together.",
    "size": "512x512",
    "output_format": "jpeg",
    "url": [
      "https://example.com/image1.png",
      "https://example.com/image2.png"
    ],
    "num_inference_steps": 50,
    "guidance_scale": 1,
    "seed": 777,
    "negative_prompt": " "
  }'
```

### Python (requests) - 本地文件

```python
import requests
import base64

url = "http://localhost:8000/v1/images/edits"

# 准备请求数据
files = {
    "image": open("input.jpg", "rb")
}

data = {
    "prompt": "将背景改为蓝天白云",
    "size": "512x512",
    "output_format": "jpeg",
    "num_inference_steps": 50,
    "seed": 777,
    "guidance_scale": 7.5,
    "negative_prompt": " "
}

# 发送请求
response = requests.post(url, files=files, data=data)
result = response.json()

# 保存结果
image_data = base64.b64decode(result["data"][0]["b64_json"])
with open("output.jpg", "wb") as f:
    f.write(image_data)
```

### Python (requests) - URL 格式

```python
import requests
import base64

url = "http://localhost:8000/v1/images/edits"

# 使用 JSON 格式发送 URL 请求
payload = {
    "model": "Qwen-Image-Edit-2511",
    "prompt": "Change the bears in the two input images into walking together.",
    "size": "512x512",
    "output_format": "jpeg",
    "url": [
        "https://example.com/image1.png",
        "https://example.com/image2.png"
    ],
    "num_inference_steps": 50,
    "guidance_scale": 1,
    "seed": 777,
    "negative_prompt": " "
}

# 发送请求
response = requests.post(url, json=payload)
result = response.json()

# 保存结果
image_base64 = result["data"][0]["b64_json"]
image_bytes = base64.b64decode(image_base64)
with open("edit_out_http.jpeg", "wb") as f:
    f.write(image_bytes)
```

## 错误处理

常见错误响应：

### 400 Bad Request
```json
{
  "error": {
    "message": "Invalid size format",
    "type": "invalid_request_error"
  }
}
```
原因：参数格式错误，如 size 格式不正确

### 422 Unprocessable Entity
```json
{
  "error": {
    "message": "Missing required field: image or url",
    "type": "invalid_request_error"
  }
}
```
原因：缺少必需字段，如未提供 image 或 url

## 使用建议

1. **图像尺寸**：建议使用 "512x512" 或 "1024x1024"，过大的尺寸会增加处理时间
2. **推理步数**：通常 20-50 步即可获得较好效果，步数过多收益递减
3. **引导强度**：guidance_scale 建议设置在 7.0-9.0 之间，过高可能导致过饱和
4. **批量生成**：使用 `n` 参数可一次生成多张图像，但会增加处理时间
5. **随机种子**：固定 seed 可确保相同输入产生相同输出，便于调试和复现

## 速度优化（出图更快）

下面这些参数对“单张出图耗时”的影响最大，按优先级从高到低：

1. **num_inference_steps（最关键）**
   - 速度档（推荐）：`8~15`
   - 均衡档：`20~30`
   - 质量档：`40+`（通常会明显变慢）

2. **size（计算量随分辨率快速增长）**
   - 速度档（推荐）：`512x512`
   - 均衡档：`768x768`
   - 质量档：`1024x1024`（明显更慢）

3. **guidance_scale（过大可能更慢且收益不稳定）**
   - 速度/稳定（推荐）：`3~7`
   - 质量偏好：`7~9`

4. **output_format（影响编码与网络传输）**
   - 速度优先：`jpeg`（体积更小，传输更快）
   - 质量/无损：`png`（更大更慢）

5. **n（一次返回多张图）**
   - 追求单张最快：保持 `n=1`
   - 追求吞吐：可用 `n>1`，但单次请求耗时会增加

### 推荐参数组合

**极速预览（最快出图）**

- `size="512x512"`
- `num_inference_steps=10`
- `guidance_scale=5`
- `output_format="jpeg"`
- `n=1`

**质量/速度均衡（多数场景默认）**

- `size="768x768"`
- `num_inference_steps=20`
- `guidance_scale=7`
- `negative_prompt=" "`
- `output_format="jpeg"`
- `n=1`

## 常见告警与排查

### 1) `negative_prompt is not set`（质量建议）

Qwen 官方建议：**传入空白字符串作为 negative_prompt**（例如 `" "`），而不是省略该字段。省略时可能出现质量下降提示，这不是服务故障。

### 2) `RuntimeWarning: invalid value encountered in divide`（数值边界）

这类告警通常来自 diffusers scheduler 在某些参数组合下触发数值边界。若你发现输出出现 NaN/花屏/全黑图，可按以下顺序处理：

- **优先保证 `negative_prompt=" "`**
- **避免极端参数**：不要把 `guidance_scale` 设为 `0`；建议 `1~9`
- **提高 steps**：把 `num_inference_steps` 提到 `15~30`（过低可能更容易触发不稳定）
- **先回到“均衡默认”组合**：确认输出稳定后，再逐步加大分辨率或 steps
