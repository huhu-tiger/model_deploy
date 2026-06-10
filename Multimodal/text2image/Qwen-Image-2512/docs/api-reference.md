# Qwen-Image-2512 接口文档

本文档描述基于 `docker-compose-vllm.yml` 部署的 Qwen-Image-2512 文生图服务接口。

## 架构概览

```
客户端
  │
  ├─ 方式一：OpenAI 兼容接口 ──► vLLM 服务 (:9111)
  │
  └─ 方式二：阿里云百炼兼容接口 ──► 网关 api-for-vllm.py (:6003) ──► vLLM (:9111)
                                                                    └─► MinIO（response_format=url 时）
```

| 层级 | 地址 | 协议 | 说明 |
|------|------|------|------|
| vLLM 推理服务 | `http://<host>:9111` | OpenAI Images API | Docker 直接暴露，返回 base64 |
| 网关服务（可选） | `http://<host>:6003` | 阿里云百炼格式 | 参数转换 + MinIO 上传 |

**模型名称**：`qwen-image`（由 `--served-model-name` 注册）

---

## 一、部署与启动

### 1.1 启动 vLLM 推理服务

```bash
cd /media/source/model_deploy/Multimodal/text2image/Qwen-Image-2512
docker-compose -f docker-compose-vllm.yml up -d
```

| 配置项 | 值 |
|--------|-----|
| 容器端口 | 8000 |
| 宿主机端口 | **9111** |
| 模型路径 | `/media/llm/Qwen/Qwen-Image-2512` |
| GPU | 6,7（tensor-parallel-size=2） |
| 最大并发 | max-num-seqs=4 |

首次启动模型加载约需 2 分钟以上。

### 1.2 启动网关（可选）

需要百炼兼容格式或返回图片 URL 时启动：

```bash
conda activate /media/conda/envs/qwen-image-2512
cd /media/source/model_deploy/Multimodal/text2image/Qwen-Image-2512
python api-for-vllm.py
```

网关默认监听 **6003** 端口。

### 1.3 健康检查

```bash
# vLLM
curl http://localhost:9111/health

# 网关
curl http://localhost:6003/healthz
```

网关健康检查响应：

```json
{
  "status": "ok",
  "vllm_url": "http://localhost:9111/v1/images/generations"
}
```

---

## 二、vLLM 直连接口（OpenAI 兼容）

### 2.1 图像生成

```
POST /v1/images/generations
Content-Type: application/json
```

**完整 URL**：`http://<host>:9111/v1/images/generations`

#### 请求参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `prompt` | string | 是 | — | 图像描述文本 |
| `model` | string | 否 | `qwen-image` | 模型名称 |
| `n` | integer | 否 | 1 | 生成数量，范围 1–10 |
| `size` | string | 否 | 模型默认 | 尺寸，格式 `宽x高`，如 `1328x1328` |
| `response_format` | string | 否 | `b64_json` | 仅支持 `b64_json` |
| `user` | string | 否 | null | 用户标识 |

**扩展参数**（两种方式均可，推荐顶层扁平传递）：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `negative_prompt` | string | — | 负面提示词 |
| `num_inference_steps` | integer | 模型默认 | 推理步数，越大质量越高、耗时越长 |
| `guidance_scale` | float | 模型默认 | 引导系数，推荐 3.0–7.0 |
| `true_cfg_scale` | float | 模型默认 | 模型特定 CFG 参数 |
| `seed` | integer | — | 随机种子，用于复现 |

> 扩展参数也可放在 `extra_body` 对象中传递（OpenAI SDK 风格）。

#### 请求示例

**基础请求（cURL）**

```bash
curl -X POST http://localhost:9111/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-image",
    "prompt": "一副典雅庄重的对联悬挂于厅堂之中，房间是个安静古典的中式布置",
    "size": "1328x1328",
    "n": 1,
    "response_format": "b64_json"
  }'
```

**完整参数（cURL）**

```bash
curl -X POST http://localhost:9111/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-image",
    "prompt": "未来科技城市夜景，霓虹灯闪烁，赛博朋克风格",
    "n": 1,
    "size": "1328x1328",
    "response_format": "b64_json",
    "negative_prompt": "blurry, low quality, distorted",
    "num_inference_steps": 30,
    "guidance_scale": 4.0,
    "seed": 42
  }'
```

**Python**

```python
import requests
import base64
from pathlib import Path

resp = requests.post(
    "http://localhost:9111/v1/images/generations",
    json={
        "model": "qwen-image",
        "prompt": "宁静的湖边日出，薄雾和温暖的金色光芒",
        "size": "1328x1328",
        "n": 1,
        "response_format": "b64_json",
        "negative_prompt": "",
        "num_inference_steps": 30,
        "guidance_scale": 4.0,
    },
    timeout=300,
)
resp.raise_for_status()

image_b64 = resp.json()["data"][0]["b64_json"]
Path("output.png").write_bytes(base64.b64decode(image_b64))
print("已保存 output.png")
```

#### 成功响应

```json
{
  "created": 1701234567,
  "data": [
    {
      "b64_json": "<base64 编码的 PNG 图像>",
      "url": null,
      "revised_prompt": null
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `created` | integer | Unix 时间戳 |
| `data[].b64_json` | string | Base64 编码的 PNG 图像 |
| `data[].url` | string/null | 固定为 null |
| `data[].revised_prompt` | string/null | 固定为 null |

#### 常见尺寸

| 尺寸 | 说明 |
|------|------|
| `1024x1024` | 标准方形 |
| `1328x1328` | 高清方形（推荐） |
| `1024x768` | 横向 |
| `768x1024` | 纵向 |

---

## 三、网关接口（阿里云百炼兼容）

### 3.1 图像生成

```
POST /api/v1/services/aigc/multimodal-generation/generation
Content-Type: application/json
```

**完整 URL**：`http://<host>:6003/api/v1/services/aigc/multimodal-generation/generation`

#### 请求体结构

```json
{
  "model": "qwen-image",
  "input": { },
  "parameters": { }
}
```

#### 顶层参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | 是 | 模型名称，填 `qwen-image` |
| `input` | object | 是 | 输入内容 |
| `parameters` | object | 否 | 生成参数 |

#### input 对象

`prompt` 与 `messages` 二选一：

| 字段 | 类型 | 说明 |
|------|------|------|
| `input.prompt` | string | 文本描述，最多 800 字符 |
| `input.messages` | array | 百炼消息格式，取首条 `content[0].text` |

`messages` 格式示例：

```json
{
  "messages": [
    {
      "role": "user",
      "content": [{ "text": "图像描述文本" }]
    }
  ]
}
```

#### parameters 对象

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| `size` | string | `1024*1024` | — | 尺寸，支持 `宽*高` 或 `宽x高` |
| `n` | integer | 1 | 1–4 | 生成数量 |
| `seed` | integer | — | 0–2147483647 | 随机种子 |
| `negative_prompt` | string | `""` | ≤500 字符 | 负面提示词 |
| `num_inference_steps` | integer | 30 | 1–50 | 推理步数 |
| `steps` | integer | — | 1–50 | `num_inference_steps` 别名 |
| `guidance_scale` | float | 4.0 | — | 引导系数 |
| `scale` | float | — | — | `guidance_scale` 别名 |
| `response_format` | string | `url` | `url` / `b64_json` | 返回格式 |

#### 请求示例

**基础请求（返回 URL）**

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

**messages 格式**

```bash
curl -X POST http://localhost:6003/api/v1/services/aigc/multimodal-generation/generation \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-image",
    "input": {
      "messages": [
        {
          "role": "user",
          "content": [{ "text": "未来科技城市夜景，霓虹灯闪烁" }]
        }
      ]
    },
    "parameters": {
      "size": "1024*1024",
      "response_format": "url"
    }
  }'
```

**返回 base64**

```bash
curl -X POST http://localhost:6003/api/v1/services/aigc/multimodal-generation/generation \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-image",
    "input": {
      "prompt": "宁静的湖边日出，薄雾和温暖的金色光芒"
    },
    "parameters": {
      "size": "1024*1024",
      "n": 1,
      "seed": 42,
      "negative_prompt": "模糊，低质量",
      "response_format": "b64_json"
    }
  }'
```

**Python（返回 URL）**

```python
import requests

resp = requests.post(
    "http://localhost:6003/api/v1/services/aigc/multimodal-generation/generation",
    json={
        "model": "qwen-image",
        "input": {"prompt": "一副典雅庄重的对联悬挂于厅堂之中"},
        "parameters": {
            "size": "1328*1328",
            "n": 1,
            "response_format": "url",
        },
    },
    timeout=300,
)
resp.raise_for_status()

result = resp.json()
image_url = result["output"]["choices"][0]["message"]["content"][0]["image"]
print(f"图像 URL: {image_url}")
```

#### 成功响应（response_format=url）

```json
{
  "output": {
    "choices": [
      {
        "finish_reason": "stop",
        "message": {
          "content": [
            { "image": "https://minio.example.com/bucket/qwen-image/abc123.png" }
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
  "request_id": "abc123def456"
}
```

#### 成功响应（response_format=b64_json）

```json
{
  "output": {
    "choices": [
      {
        "finish_reason": "stop",
        "message": {
          "content": [
            { "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..." }
          ],
          "role": "assistant"
        }
      }
    ],
    "task_metric": { "TOTAL": 1, "SUCCEEDED": 1, "FAILED": 0 }
  },
  "usage": { "image_count": 1, "width": 1024, "height": 1024 },
  "request_id": "xyz789"
}
```

---

## 四、错误响应

### 4.1 vLLM 服务

| HTTP 状态码 | 说明 |
|-------------|------|
| 400 | 请求参数错误 |
| 500 | 推理失败或内部错误 |
| 503 | 服务未就绪（模型加载中） |

### 4.2 网关服务

| HTTP 状态码 | 场景 | 响应示例 |
|-------------|------|----------|
| 400 | 缺少 prompt | `{"detail": "缺少 prompt 参数，请在 input.prompt 或 input.messages 中提供"}` |
| 400 | 无效 size | `{"detail": "无效的 size 格式，应为 '宽*高' 或 '宽x高'，如 '1024*1024'"}` |
| 400 | 无效 response_format | `{"detail": "无效的 response_format，有效值: ['url', 'b64_json']"}` |
| 400 | 多余字段 | `{"detail": "请求包含无效字段: xxx", "errors": [...], "valid_fields": "..."}` |
| 500 | vLLM 调用失败 | `{"detail": "vLLM API 调用失败: ..."}` |
| 500 | 图像处理失败 | `{"detail": "图像处理失败: ..."}` |

---

## 五、环境变量（网关）

在项目目录 `.env` 中配置：

```bash
# vLLM 后端地址
VLLM_API_URL=http://localhost:9111/v1/images/generations

# 转发至 vLLM 的模型名
MODEL_NAME=qwen-image

# 临时图像目录
IMAGE_OUTPUT_DIR=/media/source/model_deploy/Multimodal/text2image/Qwen-Image-2512/images_tmp

# MinIO 上传目录
MINIO_UPLOAD_DIR=qwen-image
```

MinIO 连接配置继承自 `vnet` 公共配置。

---

## 六、注意事项

1. **模型名称**：请求中 `model` 字段使用 `qwen-image`，与 `docker-compose-vllm.yml` 中 `--served-model-name` 一致。
2. **尺寸格式**：vLLM 直连用 `x` 分隔（`1328x1328`）；网关两种格式均支持（`1328*1328` 或 `1328x1328`）。
3. **返回格式**：vLLM 直连仅支持 `b64_json`；网关支持 `url`（上传 MinIO）和 `b64_json`。
4. **超时**：单次生成建议设置 300 秒超时；`num_inference_steps` 越大耗时越长。
5. **并发**：vLLM 当前配置 `max-num-seqs=4`，高并发时注意显存与排队延迟。
6. **远程访问**：将 `localhost` 替换为宿主机 IP，并确保防火墙放行对应端口（9111 / 6003）。

---

## 七、相关文档

| 文档 | 说明 |
|------|------|
| [api-vllm.md](api-vllm.md) | vLLM 直连接口补充说明 |
| [api-vllm-gateway.md](api-vllm-gateway.md) | 网关接口补充说明 |
| [vllm-deploy.md](vllm-deploy.md) | 部署快速指引 |
