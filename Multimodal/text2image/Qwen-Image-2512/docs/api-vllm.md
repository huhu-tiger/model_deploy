# Qwen-Image-2512 vLLM API 接口说明

> 完整文档见 [api-reference.md](api-reference.md)

## 服务信息

- **基础地址**: `http://localhost:9111`
- **模型名称**: `qwen-image`
- **API 版本**: OpenAI 兼容接口

## 健康检查

```
GET /health
```

## 图像生成接口

### 端点

```
POST /v1/images/generations
Content-Type: application/json
```

### OpenAI 标准参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `prompt` | string | **必填** | 图像描述文本 |
| `model` | string | `qwen-image` | 模型名称 |
| `n` | integer | 1 | 生成图像数量(1-10) |
| `size` | string | 模型默认 | 图像尺寸,格式: `WxH` (如 `1328x1328`) |
| `response_format` | string | "b64_json" | 响应格式,仅支持 `b64_json` |
| `user` | string | null | 用户标识符 |

### 扩展参数

可直接放在请求体顶层，或放在 `extra_body` 中：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `negative_prompt` | string | null | 负面提示词,描述要避免的内容 |
| `num_inference_steps` | integer | 模型默认 | 推理步数 |
| `guidance_scale` | float | 模型默认 | 引导系数(0.0-20.0) |
| `true_cfg_scale` | float | 模型默认 | 模型特定 CFG 参数 |
| `seed` | integer | null | 随机种子,用于结果复现 |

### 请求示例

#### cURL 基础请求

```bash
curl -X POST http://localhost:9111/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-image",
    "prompt": "一副典雅庄重的对联悬挂于厅堂之中，房间是个安静古典的中式布置",
    "size": "1328x1328",
    "n": 1
  }'
```

#### cURL 完整参数请求

```bash
curl -X POST http://localhost:9111/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-image",
    "prompt": "一副典雅庄重的对联悬挂于厅堂之中，房间是个安静古典的中式布置，桌子上放着一些青花瓷，对联上左书\"义本生知人机同道善思新\"，右书\"通云赋智乾坤启数高志远\"，横批\"智启通义\"，字体飘逸，在中间挂着一幅中国风的画作，内容是岳阳楼。",
    "n": 1,
    "size": "1328x1328",
    "response_format": "b64_json",
    "negative_prompt": "blurry, low quality, distorted",
    "num_inference_steps": 30,
    "guidance_scale": 4.0,
    "seed": 42
  }'
```

#### Python 请求示例

```python
import requests
import base64
from pathlib import Path

response = requests.post(
    "http://localhost:9111/v1/images/generations",
    json={
        "model": "qwen-image",
        "prompt": "一副典雅庄重的对联悬挂于厅堂之中，房间是个安静古典的中式布置",
        "size": "1328x1328",
        "n": 1,
        "response_format": "b64_json",
        "negative_prompt": "",
        "num_inference_steps": 30,
        "guidance_scale": 4.0
    },
    timeout=300,
)

# 保存图像
if response.status_code == 200:
    result = response.json()
    image_data = base64.b64decode(result["data"][0]["b64_json"])
    Path("output.png").write_bytes(image_data)
    print("图像已保存到 output.png")
```

### 响应格式

```json
{
  "created": 1701234567,
  "data": [
    {
      "b64_json": "<base64编码的PNG图像>",
      "url": null,
      "revised_prompt": null
    }
  ]
}
```

### 常见尺寸

- `1024x1024` - 标准方形
- `1328x1328` - 高清方形
- `1024x768` - 横向
- `768x1024` - 纵向

### 注意事项

1. `response_format` 目前仅支持 `b64_json`，返回 base64 编码的图像
2. 扩展参数可顶层传递或放在 `extra_body` 对象中
3. `size` 格式使用 `x` 分隔符，如 `1328x1328`
4. 推理步数 `num_inference_steps` 越大，生成质量越高，但耗时更长
