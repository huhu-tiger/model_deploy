# Wan2.2-I2V-A14B API 接口文档

## 基础信息

- **Base URL**: `http://localhost:9141`
- **API 版本**: v1
- **协议**: HTTP/HTTPS
- **数据格式**: multipart/form-data (请求), JSON (响应)
- **模型类型**: Image-to-Video (I2V) - 基于参考图片生成视频

## 接口列表

### 1. 生成视频

#### 请求

**端点**: `POST /v1/videos`

**Content-Type**: `multipart/form-data`

#### 请求参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `prompt` | string | 是 | - | 视频描述文本，详细描述想要生成的视频内容和动作 |
| `input_reference` | file | 是 | - | **参考图片文件**（支持 PNG、JPG、JPEG），基于此图片生成视频 |
| `negative_prompt` | string | 否 | "" | 负面提示词，描述不希望出现的内容（如 "low quality, blurry, static"） |
| `width` | integer | 否 | 832 | 视频宽度（像素），推荐 832 |
| `height` | integer | 否 | 480 | 视频高度（像素），推荐 480 |
| `num_frames` | integer | 否 | 33 | 视频帧数，推荐 33 |
| `fps` | integer | 否 | 16 | 帧率（每秒帧数），推荐 16 |
| `num_inference_steps` | integer | 否 | 40 | 推理步数，越大质量越高但速度越慢，推荐 40 |
| `guidance_scale` | float | 否 | 1.0 | 第一阶段引导强度，控制生成内容与提示词的匹配度 |
| `guidance_scale_2` | float | 否 | 1.0 | 第二阶段引导强度 |
| `boundary_ratio` | float | 否 | 0.875 | 边界比例，控制视频边界处理 |
| `flow_shift` | float | 否 | 12.0 | 流动偏移，控制运动流畅度 |
| `seed` | integer | 否 | -1 | 随机种子，用于可重复生成（-1 为随机） |

**重要说明**：
- `input_reference` 是 **必填参数**，需要上传一张参考图片
- 图片格式支持：PNG、JPG、JPEG
- 推荐图片尺寸与生成的视频尺寸一致（如 832x480）

#### 请求示例

**cURL**:
```bash
curl -X POST http://localhost:9141/v1/videos \
  -H "Accept: application/json" \
  -F "prompt=A bear playing with yarn, smooth motion" \
  -F "negative_prompt=low quality, blurry, static" \
  -F "input_reference=@/path/to/qwen-bear.png" \
  -F "width=832" \
  -F "height=480" \
  -F "num_frames=33" \
  -F "fps=16" \
  -F "num_inference_steps=40" \
  -F "guidance_scale=1.0" \
  -F "guidance_scale_2=1.0" \
  -F "boundary_ratio=0.875" \
  -F "flow_shift=12.0" \
  -F "seed=42" | jq -r '.data[0].b64_json' | base64 -d > wan22_i2v_output.mp4
```

**Python**:
```python
import requests
import base64

url = "http://localhost:9141/v1/videos"

# 准备文件和数据
files = {
    'input_reference': ('image.png', open('/path/to/image.png', 'rb'), 'image/png')
}

data = {
    "prompt": "A bear playing with yarn, smooth motion",
    "negative_prompt": "low quality, blurry, static",
    "width": 832,
    "height": 480,
    "num_frames": 33,
    "fps": 16,
    "num_inference_steps": 40,
    "guidance_scale": 1.0,
    "guidance_scale_2": 1.0,
    "boundary_ratio": 0.875,
    "flow_shift": 12.0,
    "seed": 42
}

response = requests.post(url, files=files, data=data)
result = response.json()

# 解码并保存视频
video_b64 = result['data'][0]['b64_json']
video_bytes = base64.b64decode(video_b64)

with open('output.mp4', 'wb') as f:
    f.write(video_bytes)

print("视频已保存到 output.mp4")
```

**JavaScript (Node.js)**:
```javascript
const FormData = require('form-data');
const fs = require('fs');
const fetch = require('node-fetch');

const formData = new FormData();
formData.append('prompt', 'A bear playing with yarn, smooth motion');
formData.append('negative_prompt', 'low quality, blurry, static');
formData.append('input_reference', fs.createReadStream('/path/to/image.png'));
formData.append('width', '832');
formData.append('height', '480');
formData.append('num_frames', '33');
formData.append('fps', '16');
formData.append('num_inference_steps', '40');
formData.append('guidance_scale', '1.0');
formData.append('guidance_scale_2', '1.0');
formData.append('boundary_ratio', '0.875');
formData.append('flow_shift', '12.0');
formData.append('seed', '42');

fetch('http://localhost:9141/v1/videos', {
  method: 'POST',
  body: formData
})
.then(response => response.json())
.then(data => {
  const videoB64 = data.data[0].b64_json;
  const videoBuffer = Buffer.from(videoB64, 'base64');
  fs.writeFileSync('output.mp4', videoBuffer);
  console.log('视频已保存到 output.mp4');
});
```

**JavaScript (Browser)**:
```javascript
const formData = new FormData();
formData.append('prompt', 'A bear playing with yarn, smooth motion');
formData.append('negative_prompt', 'low quality, blurry, static');

// 从文件输入获取图片
const fileInput = document.querySelector('input[type="file"]');
formData.append('input_reference', fileInput.files[0]);

formData.append('width', '832');
formData.append('height', '480');
formData.append('num_frames', '33');
formData.append('fps', '16');
formData.append('num_inference_steps', '40');
formData.append('guidance_scale', '1.0');
formData.append('guidance_scale_2', '1.0');
formData.append('boundary_ratio', '0.875');
formData.append('flow_shift', '12.0');
formData.append('seed', '42');

fetch('http://localhost:9141/v1/videos', {
  method: 'POST',
  body: formData
})
.then(response => response.json())
.then(data => {
  const videoB64 = data.data[0].b64_json;
  // 创建视频元素并显示
  const video = document.createElement('video');
  video.src = 'data:video/mp4;base64,' + videoB64;
  video.controls = true;
  document.body.appendChild(video);
});
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
  -F "prompt=A cat playing piano" \
  -F "input_reference=@/path/to/cat.png" \
  -F "width=832" \
  -F "height=480" \
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
    files={'input_reference': open('/path/to/image.png', 'rb')},
    data={
        "prompt": "A cat playing piano",
        "width": 832,
        "height": 480
    }
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
      "id": "Wan2.2-I2V-A14B",
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
| 400 | Bad Request | 请求参数错误（如缺少 input_reference） |
| 422 | Unprocessable Entity | 参数验证失败（如图片格式不支持） |
| 500 | Internal Server Error | 服务器内部错误 |
| 503 | Service Unavailable | 服务暂时不可用 |

## 最佳实践

### 1. 参考图片选择

**推荐**:
- 使用清晰、高质量的图片
- 图片尺寸与目标视频尺寸一致（如 832x480）
- 图片内容与 prompt 描述的场景匹配
- 避免过于复杂的背景，主体清晰

**不推荐**:
- 模糊、低分辨率的图片
- 包含大量文字的图片
- 尺寸过小的图片（建议至少 640x360）

### 2. Prompt 编写建议

**正面提示词（prompt）**:
- 重点描述**动作和运动**，因为是基于静态图片生成动态视频
- 使用详细、具体的动作描述
- 示例：
  - ✅ `"A bear playing with yarn, smooth motion, gentle movement"`
  - ✅ `"A cat playing piano, fingers moving gracefully, smooth animation"`
  - ❌ `"A bear"`（缺少动作描述）

**负面提示词（negative_prompt）**:
- 描述不希望出现的内容
- 常用词：`"low quality, blurry, static, distorted, watermark, text, jittery, flickering"`
- 示例：`"low quality, blurry, static, bad anatomy, deformed, jittery motion"`

### 3. 参数调优

**推荐配置（默认）**:
```bash
width=832
height=480
num_frames=33
fps=16
num_inference_steps=40
guidance_scale=1.0
guidance_scale_2=1.0
boundary_ratio=0.875
flow_shift=12.0
```

**高质量生成**:
```bash
width=1280
height=720
num_frames=65
fps=24
num_inference_steps=60
guidance_scale=1.5
guidance_scale_2=1.5
boundary_ratio=0.875
flow_shift=12.0
```

**快速预览**:
```bash
width=640
height=360
num_frames=17
fps=12
num_inference_steps=20
guidance_scale=1.0
guidance_scale_2=1.0
boundary_ratio=0.875
flow_shift=12.0
```

### 4. 性能优化

- 使用固定 `seed` 进行 A/B 测试
- 较小分辨率先验证效果，再提升分辨率
- 批量生成时控制并发数，避免 GPU 内存溢出
- 参考图片尺寸与视频尺寸一致可减少预处理时间

### 5. 可重复生成

使用相同的 `seed`、`input_reference` 和参数可以生成相同的视频：

```bash
curl -X POST http://localhost:9141/v1/videos \
  -F "prompt=A cat playing piano" \
  -F "input_reference=@/path/to/cat.png" \
  -F "seed=12345" \
  -F "width=832" \
  -F "height=480"
```

## 限制说明

- **必填参数**: `prompt` 和 `input_reference` 为必填
- 单次请求最大视频时长取决于 `num_frames` 和 `fps`
- 推荐分辨率：832x480（默认），支持范围 640x360 至 1280x720
- 推荐帧数：33（默认），支持范围 17-65 帧
- 推荐帧率：16 fps（默认）
- 生成时间与分辨率、帧数、推理步数成正比
- `boundary_ratio` 和 `flow_shift` 为模型特定参数，建议使用默认值（0.875 和 12.0）
- 参考图片格式：PNG、JPG、JPEG
- 参考图片大小：建议不超过 10MB

## Image-to-Video vs Text-to-Video

**Wan2.2-I2V-A14B** (Image-to-Video):
- ✅ 需要上传参考图片 (`input_reference`)
- ✅ 基于静态图片生成动态视频
- ✅ 适合：已有图片，想让它动起来

**Wan2.2-T2V-A14B** (Text-to-Video):
- ❌ 不需要图片
- ✅ 仅基于文本描述生成视频
- ✅ 适合：从零开始生成视频

## 技术支持

- **vLLM-Omni 官方文档**: https://github.com/vllm-project/vllm-omni
- **Image-to-Video 示例**: https://github.com/vllm-project/vllm-omni/tree/main/examples/online_serving/image_to_video
- **Wan2.2 模型文档**: https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B-Diffusers
