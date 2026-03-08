# Wan2.2-T2V-A14B API 接口文档

## 基础信息

- **Base URL**: `http://localhost:9141`
- **API 版本**: v1
- **协议**: HTTP/HTTPS
- **数据格式**: multipart/form-data (请求), JSON (响应)

## 接口列表

### 1. 生成视频

#### 请求

**端点**: `POST /v1/videos`

**Content-Type**: `multipart/form-data`

#### 请求参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `prompt` | string | 是 | - | 视频描述文本，详细描述想要生成的视频内容 |
| `negative_prompt` | string | 否 | "" | 负面提示词，描述不希望出现的内容（如 "low quality, blurry, static"） |
| `width` | integer | 否 | 832 | 视频宽度（像素），推荐 832 |
| `height` | integer | 否 | 480 | 视频高度（像素），推荐 480 |
| `num_frames` | integer | 否 | 33 | 视频帧数，推荐 33 |
| `fps` | integer | 否 | 16 | 帧率（每秒帧数），推荐 16 |
| `num_inference_steps` | integer | 否 | 40 | 推理步数，越大质量越高但速度越慢，推荐 40 |
| `guidance_scale` | float | 否 | 4.0 | 第一阶段引导强度，控制生成内容与提示词的匹配度 |
| `guidance_scale_2` | float | 否 | 4.0 | 第二阶段引导强度 |
| `boundary_ratio` | float | 否 | 0.875 | 边界比例，控制视频边界处理 |
| `flow_shift` | float | 否 | 5.0 | 流动偏移，控制运动流畅度 |
| `seed` | integer | 否 | -1 | 随机种子，用于可重复生成（-1 为随机） |

#### 请求示例

**cURL**:
```bash
curl -X POST http://localhost:9141/v1/videos \
  -F "prompt=A cinematic view of a futuristic city at sunset" \
  -F "width=832" \
  -F "height=480" \
  -F "num_frames=33" \
  -F "negative_prompt=low quality, blurry, static" \
  -F "fps=16" \
  -F "num_inference_steps=40" \
  -F "guidance_scale=4.0" \
  -F "guidance_scale_2=4.0" \
  -F "boundary_ratio=0.875" \
  -F "flow_shift=5.0" \
  -F "seed=42"
```

**Python**:
```python
import requests

url = "http://localhost:9141/v1/videos"
data = {
    "prompt": "A cinematic view of a futuristic city at sunset",
    "width": 832,
    "height": 480,
    "num_frames": 33,
    "negative_prompt": "low quality, blurry, static",
    "fps": 16,
    "num_inference_steps": 40,
    "guidance_scale": 4.0,
    "guidance_scale_2": 4.0,
    "boundary_ratio": 0.875,
    "flow_shift": 5.0,
    "seed": 42
}

response = requests.post(url, data=data)
result = response.json()
```

**JavaScript**:
```javascript
const formData = new FormData();
formData.append('prompt', 'A cinematic view of a futuristic city at sunset');
formData.append('width', '832');
formData.append('height', '480');
formData.append('num_frames', '33');
formData.append('negative_prompt', 'low quality, blurry, static');
formData.append('fps', '16');
formData.append('num_inference_steps', '40');
formData.append('guidance_scale', '4.0');
formData.append('guidance_scale_2', '4.0');
formData.append('boundary_ratio', '0.875');
formData.append('flow_shift', '5.0');
formData.append('seed', '42');

fetch('http://localhost:9141/v1/videos', {
  method: 'POST',
  body: formData
})
.then(response => response.json())
.then(data => console.log(data));
```

#### 响应格式

**成功响应** (200 OK):
```json
{
  "created": 1709884800,
  "data": [
    {
      "b64_json": "AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAAIZnJlZQAB..."
    }
  ]
}
```

**响应字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `created` | integer | Unix 时间戳，视频生成时间 |
| `data` | array | 生成结果数组 |
| `data[].b64_json` | string | Base64 编码的 MP4 视频文件 |

#### 解码视频

**命令行**:
```bash
# 保存响应到文件
curl -X POST http://localhost:9141/v1/videos \
  -F 'prompt=A cat playing piano' \
  -F 'width=1280' \
  -F 'height=720' \
  > response.json

# 解码 Base64 并保存为 MP4
cat response.json | jq -r '.data[0].b64_json' | base64 -d > output.mp4
```

**Python**:
```python
import requests
import base64

response = requests.post(
    "http://localhost:9141/v1/videos",
    data={"prompt": "A cat playing piano", "width": 1280, "height": 720}
)

result = response.json()
video_b64 = result['data'][0]['b64_json']
video_bytes = base64.b64decode(video_b64)

with open('output.mp4', 'wb') as f:
    f.write(video_bytes)
```

**JavaScript (Node.js)**:
```javascript
const fs = require('fs');

fetch('http://localhost:9141/v1/videos', {
  method: 'POST',
  body: formData
})
.then(response => response.json())
.then(data => {
  const videoB64 = data.data[0].b64_json;
  const videoBuffer = Buffer.from(videoB64, 'base64');
  fs.writeFileSync('output.mp4', videoBuffer);
});
```

### 2. 健康检查

#### 请求

**端点**: `GET /health`

**响应**:
```json
{
  "status": "ok"
}
```

### 3. 模型信息

#### 请求

**端点**: `GET /v1/models`

**响应**:
```json
{
  "object": "list",
  "data": [
    {
      "id": "Wan2.2-T2V-A14B-Diffusers",
      "object": "model",
      "created": 1709884800,
      "owned_by": "vllm"
    }
  ]
}
```

## 错误处理

### 错误响应格式

```json
{
  "error": {
    "message": "错误描述信息",
    "type": "invalid_request_error",
    "code": "invalid_parameter"
  }
}
```

### 常见错误码

| HTTP 状态码 | 错误类型 | 说明 |
|------------|---------|------|
| 400 | Bad Request | 请求参数错误 |
| 422 | Unprocessable Entity | 参数验证失败 |
| 500 | Internal Server Error | 服务器内部错误 |
| 503 | Service Unavailable | 服务暂时不可用 |

## 最佳实践

### 1. Prompt 编写建议

**正面提示词（prompt）**:
- 使用详细、具体的描述
- 包含场景、主体、动作、风格等元素
- 示例：`"A cinematic view of a futuristic city at sunset, flying cars, neon lights, 4K quality"`

**负面提示词（negative_prompt）**:
- 描述不希望出现的内容
- 常用词：`"low quality, blurry, static, distorted, watermark, text"`
- 示例：`"low quality, blurry, static, bad anatomy, deformed"`

### 2. 参数调优

**推荐配置（默认）**:
```bash
width=832
height=480
num_frames=33
fps=16
num_inference_steps=40
guidance_scale=4.0
guidance_scale_2=4.0
boundary_ratio=0.875
flow_shift=5.0
```

**高质量生成**:
```bash
width=1280
height=720
num_frames=65
fps=24
num_inference_steps=60
guidance_scale=5.0
guidance_scale_2=5.0
boundary_ratio=0.875
flow_shift=5.0
```

**快速预览**:
```bash
width=640
height=360
num_frames=17
fps=12
num_inference_steps=20
guidance_scale=3.0
guidance_scale_2=3.0
boundary_ratio=0.875
flow_shift=5.0
```

### 3. 性能优化

- 使用固定 `seed` 进行 A/B 测试
- 较小分辨率先验证效果，再提升分辨率
- 批量生成时控制并发数，避免 GPU 内存溢出

### 4. 可重复生成

使用相同的 `seed` 和参数可以生成相同的视频：

```bash
curl -X POST http://localhost:9141/v1/videos \
  -F 'prompt=A cat playing piano' \
  -F 'seed=12345' \
  -F 'width=1280' \
  -F 'height=720'
```

## 限制说明

- 单次请求最大视频时长取决于 `num_frames` 和 `fps`
- 推荐分辨率：832x480（默认），支持范围 640x360 至 1280x720
- 推荐帧数：33（默认），支持范围 17-65 帧
- 推荐帧率：16 fps（默认）
- 生成时间与分辨率、帧数、推理步数成正比
- `boundary_ratio` 和 `flow_shift` 为模型特定参数，建议使用默认值

## 技术支持

- 文档: https://docs.vllm.ai/projects/vllm-omni/
- GitHub: https://github.com/vllm-project/vllm
