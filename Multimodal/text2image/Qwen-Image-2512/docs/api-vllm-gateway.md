# Qwen-Image-2512 vLLM 网关 API 说明

> 完整文档见 [api-reference.md](api-reference.md)

## 服务信息

- **网关地址**: `http://localhost:6003`
- **后端服务**: vLLM (http://localhost:9111)
- **接口格式**: 阿里云百炼兼容
- **功能**: 将阿里云百炼格式请求转换为 vLLM 格式，并将生成的图像上传到 MinIO

## 启动服务

```bash
cd /media/source/model_deploy/Qwen-Image-2512
python api-for-vllm.py
```

服务将在端口 6003 启动。

## 图像生成接口

### 端点

```
POST /api/v1/services/aigc/multimodal-generation/generation
Content-Type: application/json
```

### 请求参数

#### 顶层参数

- `model` (string, 必填): 模型名称

#### input 对象

支持两种格式之一：

**格式 1: 直接 prompt**
- `prompt` (string): 文本描述，最多800字符

**格式 2: messages 数组**
- `messages` (array): 消息数组
  - `role` (string): 角色，默认 "user"
  - `content` (array): 内容数组
    - `text` (string): 文本描述，最多800字符

#### parameters 对象（可选）

- `size` (string, 可选): 图像尺寸，格式 `宽*高` 或 `宽x高`，默认 `1024*1024`
- `n` (integer, 可选): 生成图片数量，范围 1-4，默认 1
- `seed` (integer, 可选): 随机种子，范围 0-2147483647
- `negative_prompt` (string, 可选): 反向提示词，最多500字符
- `num_inference_steps` (integer, 可选): 推理步数，范围 1-50，默认 30
- `guidance_scale` (float, 可选): 引导系数，默认 4.0
- `response_format` (string, 可选): 返回格式 `url` 或 `b64_json`，默认 `url`

### 请求示例

#### 示例 1: 基础请求（使用 input.prompt）

```bash
curl -X POST http://localhost:6003/api/v1/services/aigc/multimodal-generation/generation \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-image",
    "input": {
      "prompt": "一副典雅庄重的对联悬挂于厅堂之中，房间是个安静古典的中式布置"
    },
    "parameters": {
      "size": "1328*1328",
      "n": 1,
      "num_inference_steps": 30,
      "guidance_scale": 4.0,
      "response_format": "url"
    }
  }'
```

#### 示例 2: 使用 messages 格式

```bash
curl -X POST http://localhost:6003/api/v1/services/aigc/multimodal-generation/generation \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-image",
    "input": {
      "messages": [
        {
          "role": "user",
          "content": [
            {
              "text": "一副典雅庄重的对联悬挂于厅堂之中，房间是个安静古典的中式布置"
            }
          ]
        }
      ]
    },
    "parameters": {
      "size": "1328*1328",
      "n": 1,
      "num_inference_steps": 30,
      "guidance_scale": 4.0,
      "response_format": "url"
    }
  }'
```

#### 示例 3: 完整参数请求

```bash
curl -X POST http://localhost:6003/api/v1/services/aigc/multimodal-generation/generation \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-image",
    "input": {
      "prompt": "一副典雅庄重的对联悬挂于厅堂之中，房间是个安静古典的中式布置，桌子上放着一些青花瓷，对联上左书\"义本生知人机同道善思新\"，右书\"通云赋智乾坤启数高志远\"，横批\"智启通义\"，字体飘逸，在中间挂着一幅中国风的画作，内容是岳阳楼。"
    },
    "parameters": {
      "n": 1,
      "size": "1328*1328",
      "response_format": "url",
      "negative_prompt": "blurry, low quality, distorted",
      "num_inference_steps": 30,
      "guidance_scale": 4.0,
      "seed": 42
    }
  }'
```

#### 示例 4: 返回 base64 格式

```bash
curl -X POST http://localhost:6003/api/v1/services/aigc/multimodal-generation/generation \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-image",
    "input": {
      "prompt": "未来科技城市夜景，霓虹灯闪烁"
    },
    "parameters": {
      "size": "1024*1024",
      "n": 1,
      "num_inference_steps": 30,
      "guidance_scale": 4.0,
      "response_format": "b64_json"
    }
  }'
```

#### 示例 5: 使用随机种子

```bash
curl -X POST http://localhost:6003/api/v1/services/aigc/multimodal-generation/generation \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-image",
    "input": {
      "prompt": "宁静的湖边日出，薄雾和温暖的金色光芒"
    },
    "parameters": {
      "negative_prompt": "模糊，低质量",
      "size": "1024*1024",
      "n": 1,
      "seed": 42,
      "num_inference_steps": 30,
      "guidance_scale": 4.0,
      "response_format": "url"
    }
  }'
```

### 响应格式

#### 成功响应 (response_format: url)

```json
{
  "output": {
    "choices": [
      {
        "finish_reason": "stop",
        "message": {
          "content": [
            {
              "image": "https://minio.example.com/bucket/qwen3-image-2512/abc123.png"
            }
          ],
          "role": "assistant"
        }
      }
    ],
    "task_metric": {
      "TOTAL": 1,
      "SUCCEEDED": 1,
      "FAILED": 0
    }
  },
  "usage": {
    "image_count": 1,
    "width": 1328,
    "height": 1328
  },
  "request_id": "abc123def456..."
}
```

#### 成功响应 (response_format: b64_json)

```json
{
  "output": {
    "choices": [
      {
        "finish_reason": "stop",
        "message": {
          "content": [
            {
              "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
            }
          ],
          "role": "assistant"
        }
      }
    ],
    "task_metric": {
      "TOTAL": 1,
      "SUCCEEDED": 1,
      "FAILED": 0
    }
  },
  "usage": {
    "image_count": 1,
    "width": 1024,
    "height": 1024
  },
  "request_id": "xyz789..."
}
```

### Python 调用示例

#### 示例 1: 基础调用（使用 input.prompt）

```python
import requests

response = requests.post(
    "http://localhost:6003/api/v1/services/aigc/multimodal-generation/generation",
    json={
        "model": "qwen-image",
        "input": {
            "prompt": "一副典雅庄重的对联悬挂于厅堂之中"
        }
    }
)

if response.status_code == 200:
    result = response.json()
    image_url = result["output"]["choices"][0]["message"]["content"][0]["image"]
    print(f"图像 URL: {image_url}")
else:
    print(f"错误: {response.text}")
```

#### 示例 2: 使用 messages 格式

```python
import requests

response = requests.post(
    "http://localhost:6003/api/v1/services/aigc/multimodal-generation/generation",
    json={
        "model": "qwen-image",
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": "一副典雅庄重的对联悬挂于厅堂之中"
                        }
                    ]
                }
            ]
        },
        "parameters": {
            "size": "1328*1328",
            "n": 1,
            "response_format": "url"
        }
    }
)

if response.status_code == 200:
    result = response.json()
    image_url = result["output"]["choices"][0]["message"]["content"][0]["image"]
    print(f"图像 URL: {image_url}")
else:
    print(f"错误: {response.text}")
```

#### 示例 3: 完整参数调用

```python
import requests

response = requests.post(
    "http://localhost:6003/api/v1/services/aigc/multimodal-generation/generation",
    json={
        "model": "qwen-image",
        "input": {
            "prompt": "一副典雅庄重的对联悬挂于厅堂之中，房间是个安静古典的中式布置，桌子上放着一些青花瓷"
        },
        "parameters": {
            "size": "1328*1328",
            "n": 1,
            "seed": 42,
            "negative_prompt": "blurry, low quality, distorted",
            "num_inference_steps": 30,
            "guidance_scale": 4.0,
            "response_format": "url"
        }
    }
)

if response.status_code == 200:
    result = response.json()
    for idx, choice in enumerate(result["output"]["choices"]):
        image_url = choice["message"]["content"][0]["image"]
        print(f"图像 {idx + 1} URL: {image_url}")

    # 打印任务统计
    metric = result["output"]["task_metric"]
    print(f"总数: {metric['TOTAL']}, 成功: {metric['SUCCEEDED']}, 失败: {metric['FAILED']}")
else:
    print(f"错误: {response.status_code} - {response.text}")
```

#### 示例 4: 返回 base64 格式

```python
import requests
import base64
from pathlib import Path

response = requests.post(
    "http://localhost:6003/api/v1/services/aigc/multimodal-generation/generation",
    json={
        "model": "qwen-image",
        "input": {
            "prompt": "未来科技城市夜景，霓虹灯闪烁"
        },
        "parameters": {
            "size": "1024*1024",
            "n": 1,
            "num_inference_steps": 30,
            "guidance_scale": 4.0,
            "response_format": "b64_json"
        }
    }
)

if response.status_code == 200:
    result = response.json()
    # 获取 base64 图像数据
    image_data_uri = result["output"]["choices"][0]["message"]["content"][0]["image"]
    # 去掉 data:image/png;base64, 前缀
    base64_data = image_data_uri.split(",")[1]
    # 解码并保存
    image_bytes = base64.b64decode(base64_data)
    Path("output.png").write_bytes(image_bytes)
    print("图像已保存到 output.png")
else:
    print(f"错误: {response.text}")
```

## 工作流程

1. 接收阿里云百炼格式的请求（嵌套 input 和 parameters 结构）
2. 提取 prompt（支持 `input.prompt` 或 `input.messages` 格式）
3. 转换参数为 vLLM 格式（尺寸从 `*` 转为 `x`，扁平化参数）
4. 调用 vLLM API 生成图像（返回 base64）
5. 将 base64 图像保存为临时文件
6. 上传到 MinIO 获取下载 URL
7. 返回阿里云百炼格式的响应
8. 清理临时文件

## 环境变量配置

在 `.env` 文件中配置：

```bash
# vLLM API 地址
VLLM_API_URL=http://localhost:9111/v1/images/generations

# 模型名称
MODEL_NAME=qwen-image

# 临时图像目录
IMAGE_OUTPUT_DIR=/media/source/model_deploy/Qwen-Image-2512/images_tmp

# MinIO 上传目录
MINIO_UPLOAD_DIR=qwen3-image-2512

# MinIO 配置（继承自 vnet 配置）
```

## 健康检查

```bash
curl http://localhost:6003/healthz
```

响应：
```json
{
  "status": "ok",
  "vllm_url": "http://localhost:9111/v1/images/generations"
}
```

## 注意事项

1. 确保 vLLM 服务已启动（端口 9111）
2. 确保 MinIO 服务可访问
3. `response_format` 为 `url` 时会上传到 MinIO，`b64_json` 时直接返回 base64
4. 临时文件会在上传后自动清理
5. 支持批量生成（`n` 参数最大为 4）
6. 推理步数越大，生成质量越高但耗时越长

## 日志管理

服务会自动记录详细的运行日志：

- **日志目录**: `Qwen-Image-2512/logs/`
- **日志文件**: `api-vllm-gateway.log`
- **滚动策略**: 每天午夜自动滚动，旧日志文件命名为 `api-vllm-gateway.log.YYYY-MM-DD`
- **保留时间**: 保留最近 30 天的日志
- **日志内容**:
  - 接收到的请求参数明细
  - 参数验证结果
  - 发送至 vLLM 的参数明细
  - API 调用耗时和状态
  - 图像处理和上传过程
  - 错误和异常信息

查看实时日志：
```bash
tail -f Qwen-Image-2512/logs/api-vllm-gateway.log
```
