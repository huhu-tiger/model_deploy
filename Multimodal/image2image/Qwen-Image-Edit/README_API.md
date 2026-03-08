# Qwen Image Edit API

基于Qwen-Image的图像编辑API，使用FastAPI框架构建，符合OpenAI格式规范。

## 功能特性

- 🎨 基于Qwen-Image-Edit模型的图像编辑
- 🔄 智能提示词重写和优化
- 📡 符合OpenAI格式的RESTful API
- 📁 支持JSON和文件上传两种方式
- 🚀 高性能异步处理
- 📊 完整的API文档和健康检查
- 📥 图片文件服务器，支持直接下载
- 🧹 自动清理旧图片文件

## 安装依赖

```bash
pip install -r requirements.txt
```

## 启动服务

```bash
python api.py
```

服务将在 `http://localhost:6003` 启动。

### 启动事件机制

API使用FastAPI的启动事件处理器(`@app.on_event("startup")`)来确保模型只在应用启动时加载一次：

- 🚀 **启动时加载**: 模型在应用启动时自动加载到GPU内存
- 🔄 **单次加载**: 避免重复加载模型，节省内存和时间
- ⚡ **快速响应**: 模型加载完成后，API请求可以立即处理
- 📊 **状态监控**: 通过健康检查端点监控模型加载状态

### 模型加载状态

启动后可以通过健康检查端点查看模型状态：

```bash
curl http://localhost:6003/health
```

响应示例：
```json
{
  "status": "healthy",
  "model_loaded": true,
  "device": "cuda",
  "model_type": "Qwen-Image-Edit"
}
```

## API端点

### 图像编辑

**端点:** `POST /v1/images/edits`

**Content-Type:** `application/json`

**请求体:**
```json
{
  "model": "qwen-image-edit",
  "prompt": "make the cat floating in the air",
  "image": "https://example.com/image.jpg",
  "n": 1,
  "size": "1024x1024",
  "quality": "standard",
  "seed": 42,
  "guidance_scale": 4.0,
  "num_inference_steps": 50,
  "rewrite_prompt": true
}
```

**image字段支持:**
- **图片URL**: `"image": "https://example.com/image.jpg"`
- **Base64编码**: `"image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."`

**特殊功能:**
- 自动IP地址替换: 如果图片URL中包含IP地址`39.155.179.4`，会自动替换为`192.168.0.2`

**响应:**
```json
{
  "id": "img_edit_abc123",
  "object": "image.edit",
  "created": 1703123456,
  "model": "qwen-image-edit",
  "data": [
    {
      "url": "http://39.155.179.4:6003/images/edit_abc123def456.png",
      "revised_prompt": "Make the cat floating in the air with a magical effect"
    }
  ]
}
```

**图片下载:** 使用返回的完整URL可以直接下载图片，例如：`http://39.155.179.4:6003/images/edit_abc123def456.png`

### 3. 图片下载

**端点:** `GET /images/{filename}`

**说明:** 下载生成的图片文件

**示例:** `GET /images/edit_abc123def456.png`

### 4. 健康检查

**端点:** `GET /health`

**响应:**
```json
{
  "status": "healthy",
  "model_loaded": true,
  "device": "cuda"
}
```

### 5. 根端点

**端点:** `GET /`

**响应:**
```json
{
  "message": "Qwen Image Edit API",
  "version": "1.0.0",
  "endpoints": {
    "POST /v1/images/edits": "创建图像编辑 (支持JSON和文件上传)",
    "GET /images/{filename}": "下载生成的图片",
    "GET /health": "健康检查",
    "GET /docs": "API文档"
  }
}
```

## 详细参数说明

### 请求参数 (Request Parameters)

#### 必需参数 (Required)

| 参数 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `prompt` | string | 图像编辑指令，描述要进行的编辑操作 | `"make the cat floating in the air"` |
| `image` | string | 输入图像，支持URL或Base64编码 | `"https://example.com/image.jpg"` 或 `"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."` |

#### 可选参数 (Optional)

| 参数 | 类型 | 默认值 | 说明 | 示例 |
|------|------|--------|------|------|
| `model` | string | "qwen-image-edit" | 使用的模型名称 | `"qwen-image-edit"` |
| `n` | integer | 1 | 生成图像的数量 | `1`, `2`, `3` |
| `size` | string | "1024x1024" | 输出图像的尺寸 | `"1024x1024"`, `"512x512"` |
| `quality` | string | "standard" | 图像质量设置 | `"standard"`, `"hd"` |
| `style` | string | null | 图像风格 | `"vivid"`, `"natural"` |
| `seed` | integer | null | 随机种子，用于可重现的结果 | `42`, `12345` |
| `guidance_scale` | float | 4.0 | 引导比例，控制生成质量 | `3.0`, `7.0` |
| `num_inference_steps` | integer | 50 | 推理步数，影响生成质量和速度 | `20`, `100` |
| `rewrite_prompt` | boolean | true | 是否启用提示词重写优化 | `true`, `false` |

### 返回参数 (Response Parameters)

#### 响应结构 (Response Structure)

```json
{
  "id": "img_edit_abc123def456",
  "object": "image.edit",
  "created": 1703123456,
  "model": "qwen-image-edit",
  "data": [
    {
      "url": "http://39.155.179.4:6003/images/edit_abc123def456.png",
      "revised_prompt": "Make the cat floating in the air with a magical effect"
    }
  ]
}
```

#### 字段说明 (Field Descriptions)

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `id` | string | 请求的唯一标识符 | `"img_edit_abc123def456"` |
| `object` | string | 对象类型，固定为 "image.edit" | `"image.edit"` |
| `created` | integer | 创建时间戳（Unix时间戳） | `1703123456` |
| `model` | string | 使用的模型名称 | `"qwen-image-edit"` |
| `data` | array | 生成的图像数据数组 | `[...]` |

#### data数组中的字段

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `url` | string | 生成图像的完整下载URL | `"http://39.155.179.4:6003/images/edit_abc123def456.png"` |
| `revised_prompt` | string | 经过重写优化的提示词 | `"Make the cat floating in the air with a magical effect"` |

### 错误响应 (Error Responses)

#### 常见错误码

| 状态码 | 错误类型 | 说明 | 解决方案 |
|--------|----------|------|----------|
| `400` | Bad Request | 请求参数错误 | 检查请求参数格式和必需字段 |
| `503` | Service Unavailable | 模型尚未加载完成 | 等待模型加载完成或检查服务状态 |
| `500` | Internal Server Error | 服务器内部错误 | 检查服务器日志或联系管理员 |

#### 错误响应格式

```json
{
  "error": {
    "message": "错误描述",
    "type": "error_type",
    "code": "error_code"
  }
}
```

### 特殊功能说明

#### 1. 图像输入格式

**URL格式:**
```json
{
  "image": "https://example.com/image.jpg"
}
```

**Base64格式:**
```json
{
  "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
}
```

#### 2. IP地址自动替换

当输入图片URL中包含IP地址 `39.155.179.4` 时，系统会自动替换为 `192.168.0.2`：

```json
// 输入
{
  "image": "http://39.155.179.4:8080/image.jpg"
}

// 实际处理
"image": "http://192.168.0.2:8080/image.jpg"
```

#### 3. 提示词重写

当 `rewrite_prompt` 为 `true` 时，系统会使用AI优化原始提示词：

```json
// 原始提示词
"prompt": "add a cat"

// 重写后的提示词
"revised_prompt": "Add a light-gray cat in the bottom-right corner, sitting and facing the camera"
```

## 使用示例

### cURL 示例

#### 1. 使用图片URL

```bash
curl -X POST "http://localhost:6003/v1/images/edits" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-image-edit",
    "prompt": "make the cat floating in the air",
    "image": "https://example.com/cat.jpg",
    "n": 1,
    "size": "1024x1024",
    "guidance_scale": 4.0,
    "num_inference_steps": 50,
    "rewrite_prompt": true
  }'
```

#### 2. 使用Base64编码图片

```bash
curl -X POST "http://localhost:6003/v1/images/edits" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-image-edit",
    "prompt": "change the background to sunset",
    "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
    "n": 1,
    "size": "1024x1024",
    "seed": 42,
    "rewrite_prompt": true
  }'
```

#### 3. 生成多张图片

```bash
curl -X POST "http://localhost:6003/v1/images/edits" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-image-edit",
    "prompt": "add a hat to the person",
    "image": "https://example.com/person.jpg",
    "n": 3,
    "size": "1024x1024",
    "guidance_scale": 6.0,
    "num_inference_steps": 30,
    "rewrite_prompt": true
  }'
```

### Python 示例

```python
import requests
import json

# API配置
api_url = "http://localhost:6003/v1/images/edits"
headers = {"Content-Type": "application/json"}

# 请求数据
data = {
    "model": "qwen-image-edit",
    "prompt": "make the cat floating in the air",
    "image": "https://example.com/cat.jpg",
    "n": 1,
    "size": "1024x1024",
    "guidance_scale": 4.0,
    "num_inference_steps": 50,
    "rewrite_prompt": True
}

# 发送请求
response = requests.post(api_url, headers=headers, json=data)

if response.status_code == 200:
    result = response.json()
    print("✅ 图像编辑成功!")
    print(f"请求ID: {result['id']}")
    print(f"生成图片数量: {len(result['data'])}")
    
    for i, image_data in enumerate(result['data']):
        print(f"图片 {i+1}:")
        print(f"  下载URL: {image_data['url']}")
        print(f"  优化提示词: {image_data['revised_prompt']}")
else:
    print(f"❌ 请求失败: {response.status_code}")
    print(f"错误信息: {response.text}")
```

### JavaScript 示例

```javascript
// 使用fetch API
const apiUrl = 'http://localhost:6003/v1/images/edits';

const requestData = {
    model: 'qwen-image-edit',
    prompt: 'make the cat floating in the air',
    image: 'https://example.com/cat.jpg',
    n: 1,
    size: '1024x1024',
    guidance_scale: 4.0,
    num_inference_steps: 50,
    rewrite_prompt: true
};

fetch(apiUrl, {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
    },
    body: JSON.stringify(requestData)
})
.then(response => response.json())
.then(data => {
    console.log('✅ 图像编辑成功!');
    console.log('请求ID:', data.id);
    console.log('生成图片数量:', data.data.length);
    
    data.data.forEach((imageData, index) => {
        console.log(`图片 ${index + 1}:`);
        console.log('  下载URL:', imageData.url);
        console.log('  优化提示词:', imageData.revised_prompt);
    });
})
.catch(error => {
    console.error('❌ 请求失败:', error);
});
```

## 文件管理端点

### 1. 列出所有图片

**端点:** `GET /images`

**响应:**
```json
{
  "total": 5,
  "images": [
    {
      "filename": "edit_abc123def456.png",
      "url": "/images/edit_abc123def456.png",
      "size": 1024000,
      "created": 1703123456,
      "modified": 1703123456
    }
  ]
}
```

### 2. 获取图片统计信息

**端点:** `GET /images/stats`

**响应:**
```json
{
  "total_images": 5,
  "total_size_bytes": 5120000,
  "total_size_mb": 4.88,
  "directory": "output_images"
}
```

### 3. 删除指定图片

**端点:** `DELETE /images/{filename}`

**响应:**
```json
{
  "message": "图片 edit_abc123def456.png 已删除"
}
```

## 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `CUDA_VISIBLE_DEVICES` | GPU设备ID | "4" |
| `vl_base_url` | 视觉语言模型API地址 | "http://192.168.0.2:9116/v1" |
| `vl_model` | 视觉语言模型名称 | "Qwen2.5-VL-7B-Instruct" |
| `download_url` | 图片下载URL前缀 | "http://39.155.179.4:6003" |
| `OPENAI_API_KEY` | OpenAI API密钥 | 无 |
| `OPENAI_API_BASE` | OpenAI API基础URL | 无 |

## 注意事项

1. **模型加载**: 首次启动时需要等待模型加载完成，可通过健康检查端点监控状态
2. **内存管理**: 建议定期清理不需要的图片文件以节省存储空间
3. **网络配置**: 确保 `download_url` 环境变量正确设置，以便返回正确的图片下载URL
4. **IP地址替换**: 系统会自动将输入URL中的 `39.155.179.4` 替换为 `192.168.0.2`
5. **提示词优化**: 建议启用 `rewrite_prompt` 以获得更好的编辑效果

## 许可证

本项目基于Qwen-Image-Edit模型，请遵循相应的许可证要求。 