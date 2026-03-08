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
        "guidance_scale": 7.5
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
    "seed": 777
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
    "guidance_scale": 7.5
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
    "seed": 777
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
