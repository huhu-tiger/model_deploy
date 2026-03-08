# Qwen-Image OpenAI 兼容 API 接口文档

## 概述

这是一个基于 Qwen-Image 模型的图像生成 API，完全兼容 OpenAI 的图像生成接口规范，支持多 GPU 并行处理。

## 基础信息

- **服务地址**: `http://localhost:6002`
- **模型名称**: `Qwen-Image`
- **支持格式**: JSON
- **认证方式**: 无需认证（可根据需要添加）

## 接口列表

### 1. 健康检查接口

**接口地址**: `GET /healthz`

**功能**: 检查服务状态

**请求参数**: 无

**返回参数说明**:

| 参数名 | 类型 | 说明 |
|--------|------|------|
| status | string | 服务状态，固定值："ok" |
| model | string | 当前使用的模型名称 |

**返回示例**:
```json
{
  "status": "ok",
  "model": "Qwen-Image"
}
```

### 2. 模型列表接口

**接口地址**: `GET /v1/models`

**功能**: 获取支持的模型列表

**请求参数**: 无

**返回参数说明**:

| 参数名 | 类型 | 说明 |
|--------|------|------|
| object | string | 对象类型，固定值："list" |
| data | array | 模型列表数组 |

**data 数组中的对象参数**:

| 参数名 | 类型 | 说明 |
|--------|------|------|
| id | string | 模型唯一标识符 |
| object | string | 对象类型，固定值："model" |
| created | integer | 模型创建时间戳（Unix时间戳） |
| owned_by | string | 模型所有者 |

**返回示例**:
```json
{
  "object": "list",
  "data": [
    {
      "id": "Qwen-Image",
      "object": "model",
      "created": 0,
      "owned_by": "owner"
    }
  ]
}
```

### 3. 图像生成接口

**接口地址**: `POST /v1/images/generations`

**功能**: 根据文本提示词生成图像

#### 请求参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| model | string | 否 | "Qwen-Image" | 模型名称 |
| prompt | string | 是 | - | 生成提示词 |
| n | integer | 否 | 1 | 返回图片数量（1-4） |
| size | string | 否 | "1024x1024" | 图像尺寸，支持：256x256、512x512、1024x1024 |
| response_format | string | 否 | "b64_json" | 返回格式：b64_json 或 url |
| user | string | 否 | - | 用户标识 |
| negative_prompt | string | 否 | "" | 负向提示词 |
| seed | integer | 否 | 随机 | 随机种子，用于复现结果 |
| guidance_scale | float | 否 | 4.0 | 文本引导强度（3.0-6.0） |
| num_inference_steps | integer | 否 | 50 | 采样步数（1-50） |
| aspect_ratio | string | 否 | - | 宽高比快捷选项 |

#### aspect_ratio 支持的值

| 值 | 对应分辨率 | 说明 |
|----|------------|------|
| "1:1" | 1328x1328 | 正方形 |
| "16:9" | 1664x928 | 宽屏 |
| "9:16" | 928x1664 | 竖屏 |
| "4:3" | 1472x1140 | 标准 |
| "3:4" | 1140x1472 | 竖屏标准 |

#### 请求示例

**基本请求**:
```json
{
  "prompt": "一只可爱的小猫坐在花园里",
  "n": 1,
  "size": "1024x1024"
}
```

**高级请求**:
```json
{
  "prompt": "一只可爱的小猫坐在花园里，阳光明媚，花朵盛开",
  "negative_prompt": "模糊的，低质量的，水印",
  "n": 2,
  "aspect_ratio": "16:9",
  "guidance_scale": 5.0,
  "num_inference_steps": 40,
  "seed": 42,
  "response_format": "url"
}
```

#### 返回参数说明

| 参数名 | 类型 | 说明 |
|--------|------|------|
| created | integer | 创建时间戳（Unix时间戳） |
| data | array | 生成的图像数据数组 |

**data 数组中的对象参数**:

| 参数名 | 类型 | 说明 | 条件 |
|--------|------|------|------|
| b64_json | string | Base64编码的图像数据 | response_format="b64_json"时返回 |
| url | string | 图像文件的访问URL | response_format="url"时返回 |

#### 返回格式

**b64_json 格式返回**:
```json
{
  "created": 1703123456,
  "data": [
    {
      "b64_json": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    }
  ]
}
```

**url 格式返回**:
```json
{
  "created": 1703123456,
  "data": [
    {
      "url": "http://39.155.179.4:6002/images/abc123def456.png"
    }
  ]
}
```

## 错误处理

### HTTP 状态码

- `200`: 成功
- `400`: 请求参数错误
- `500`: 服务器内部错误

### 错误响应格式

**错误响应参数说明**:

| 参数名 | 类型 | 说明 |
|--------|------|------|
| detail | string | 错误描述信息，包含具体的错误原因 |

**错误响应示例**:
```json
{
  "detail": "错误描述信息"
}
```

### 常见错误

**常见错误类型及说明**:

| 错误类型 | HTTP状态码 | 错误信息 | 解决方案 |
|----------|------------|----------|----------|
| 模型不存在 | 400 | "Model not available: {model_name}" | 检查请求的模型名称是否正确 |
| 推理失败 | 500 | "Inference failed: {error_message}" | 检查GPU内存、模型加载状态 |
| 任务超时 | 500 | "Task timeout" | 减少推理步数或简化提示词 |
| 队列已满 | 500 | "Task queue is full" | 等待队列清空或减少并发请求 |
| 参数错误 | 400 | "Validation error" | 检查请求参数格式和取值范围 |

**错误响应示例**:

1. **模型不存在**:
```json
{
  "detail": "Model not available: Qwen-Image"
}
```

2. **推理失败**:
```json
{
  "detail": "Inference failed: GPU memory insufficient"
}
```

3. **任务超时**:
```json
{
  "detail": "Task timeout"
}
```

4. **队列已满**:
```json
{
  "detail": "Task queue is full"
}
```

## 使用示例

### cURL 示例

**基本图像生成**:
```bash
curl -X POST "http://localhost:6002/v1/images/generations" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "一只可爱的小猫坐在花园里",
    "n": 1,
    "size": "1024x1024"
  }'
```

**高级图像生成**:
```bash
curl -X POST "http://localhost:6002/v1/images/generations" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "一只可爱的小猫坐在花园里，阳光明媚，花朵盛开",
    "negative_prompt": "模糊的，低质量的，水印",
    "n": 2,
    "aspect_ratio": "16:9",
    "guidance_scale": 5.0,
    "num_inference_steps": 40,
    "seed": 42,
    "response_format": "url"
  }'
```

### Python 示例

```python
import requests
import json

# 基本请求
def generate_image_basic():
    url = "http://localhost:6002/v1/images/generations"
    data = {
        "prompt": "一只可爱的小猫坐在花园里",
        "n": 1,
        "size": "1024x1024"
    }
    
    response = requests.post(url, json=data)
    return response.json()

# 高级请求
def generate_image_advanced():
    url = "http://localhost:6002/v1/images/generations"
    data = {
        "prompt": "一只可爱的小猫坐在花园里，阳光明媚，花朵盛开",
        "negative_prompt": "模糊的，低质量的，水印",
        "n": 2,
        "aspect_ratio": "16:9",
        "guidance_scale": 5.0,
        "num_inference_steps": 40,
        "seed": 42,
        "response_format": "url"
    }
    
    response = requests.post(url, json=data)
    return response.json()

# 使用示例
if __name__ == "__main__":
    # 基本生成
    result = generate_image_basic()
    print("基本生成结果:", json.dumps(result, indent=2, ensure_ascii=False))
    
    # 高级生成
    result = generate_image_advanced()
    print("高级生成结果:", json.dumps(result, indent=2, ensure_ascii=False))
```

## 性能优化建议

1. **批量生成**: 使用 `n` 参数一次生成多张图片，比多次调用更高效
2. **参数调优**: 
   - `guidance_scale`: 3.0-6.0，数值越大越贴近提示词
   - `num_inference_steps`: 30-50，步数越多质量越好但速度越慢
3. **种子控制**: 使用固定 `seed` 可以复现结果，便于调试
4. **负向提示词**: 使用 `negative_prompt` 可以抑制不希望出现的元素

## 注意事项

1. **GPU 资源**: 服务使用多 GPU 并行处理，确保有足够的 GPU 内存
2. **队列管理**: 任务队列有大小限制，避免同时提交过多请求
3. **超时设置**: 单个任务有超时限制，复杂提示词可能需要更长时间
4. **图片存储**: 使用 `url` 格式时，图片会保存到服务器，注意磁盘空间
5. **提示词优化**: 使用详细、具体的提示词可以获得更好的生成效果

## 环境变量配置

服务支持以下环境变量配置：

- `MODEL_PATH`: 模型路径
- `MODEL_NAME`: 模型名称
- `NUM_GPUS_TO_USE`: 使用的 GPU 数量
- `TASK_QUEUE_SIZE`: 任务队列大小
- `TASK_TIMEOUT`: 任务超时时间
- `IMAGE_OUTPUT_DIR`: 图片输出目录
- `IMAGE_DOWNLOAD_URL_PREFIX`: 图片下载 URL 前缀
- `ENABLE_PROMPT_REWRITE`: 是否启用提示词重写
- `OPENAI_API_KEY`: OpenAI API 密钥（用于提示词重写）
- `OPENAI_BASE_URL`: OpenAI API 基础 URL
- `OPENAI_MODEL`: OpenAI 模型名称 