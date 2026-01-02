# Qwen-Image OpenAI 兼容接口技术文档

## 目标
- 提供基于 FastAPI 的 `/v1/images/generations` OpenAI 兼容图片生成接口。
- 支持在请求进入后首先按需重写提示词（prompt），利用 `rewrite()` 实现自动中英双语润色。
- 调用现有推理脚本 `Qwen-Image-2512/service/generate.py` 返回图片（base64 或 URL），对接产品文档中的请求/响应格式。
- 返回图片的url，将图片上传到minio服务器，并返回对应的下载链接。

## 依赖与环境
- 运行环境：Python，CUDA 可选（自动选择 `bfloat16/cuda` 或 `float32/cpu`）。
- 模型路径：`/media/llm/Qwen/Qwen-Image-2512`（在 `generate.py` 中配置）。
- 主要库：`fastapi`、`pydantic`、`torch`、`diffusers`、`PIL`、`modelscope`。
- 提示词重写依赖 Qwen 模型（`qwen-plus`）调用，逻辑在 `Qwen-Image-2512/service/prompt_utils_2512.py` 的 `rewrite()`、`polish_prompt_zh()`、`polish_prompt_en()` 中。

## 接口定义（POST /v1/images/generations）
### 请求体字段（与示例一致）
- `model`：字符串，需与部署模型名一致（示例：`aliyun/aliyun/qwen-image-plus`）。
- `input.messages[].content[].text`：必填，用户原始提示词文本。
- `parameters`：扩展参数：
    - `negative_prompt`：负向提示词，可空。
    - `prompt_extend`：布尔，是否先调用 `rewrite()` 润色/翻译。
    - `watermark`：布尔，是否添加水印。
    - `size`：分辨率字符串（如 `1328*1328`）。
    - `response_format`：返回格式，`url` 或 `b64_json`。
    - `num_inference_steps`：采样步数，示例 10，范围 1–50。
    - `guidance_scale`：文本引导强度，示例 4.5，建议 3.0–6.0。
    - `seed`：随机种子，示例 12345，未提供则随机。
    - `n`：生成图片数量，示例 1，支持 1–4。
    - `width` / `height`：整数宽高，示例 1328/1328（当提供时优先生效）。

### 处理流程
1. 校验 `model` 是否匹配当前部署模型。
2. 解析分辨率：若传入 `aspect_ratio`，使用内置映射；否则按 `size` 解析宽高，异常时退回 1024x1024。
3. 提示词重写：当 `prompt_extend=true` 时调用 `rewrite(prompt)`。
	 - `rewrite()` 先检测语种（中/英），再分别调用 `polish_prompt_zh` 或 `polish_prompt_en`，由 Qwen 模型输出高质量英文或中文 Prompt，用于提升画质与安全性。
4. 推理调用：
     - 组装 `prompt`、`negative_prompt`、`width`、`height`、`guidance_scale`、`num_inference_steps`、`seed`。
     - 通过 `DiffusionPipeline.from_pretrained(model_name, torch_dtype).to(device)` 构建管线并执行生成，逻辑参考 `Qwen-Image-2512/service/generate.py`。
5. 响应封装：
     - `response_format=b64_json`：将 PIL Image 转为 base64 返回；
     - `response_format=url`：将图片保存到临时目录后，上传到 MinIO（路径约为 `upload_dir/<date>/<timestamp>/<filename>`），返回 MinIO 直链或对外下载链接。

    ### 响应体字段（与示例一致）
    - `output.choices[].message.content[].image`：当 `response_format=url` 时返回图片直链。
    - `output.choices[].message.content[].b64_json`：当 `response_format=b64_json` 时返回 base64 编码 PNG 字符串。
    - `output.choices[].finish_reason`：生成终止原因，示例为 `stop`。
    - `output.task_metric`：任务统计，含 `FAILED`/`SUCCEEDED`/`TOTAL`。
    - `usage.height` / `usage.width`：实际生成的图片分辨率。
    - `usage.image_count`：本次返回的图片数量。
    - `request_id`：请求唯一标识，便于追踪。

### 请求示例（产品文档对齐）
```json
{
    "model": "aliyun/aliyun/qwen-image-plus",
    "input": {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "text": "一副典雅庄重的对联悬挂于厅堂之中，房间是个安静古典的中式布置，桌子上放着一些青花瓷，对联上左书“义本生知人机同道善思新”，右书“通云赋智乾坤启数高志远”， 横批“智启通义”，字体飘逸，在中间挂着一幅中国风的画作，内容是岳阳楼。"
                    }
                ]
            }
        ]
    },
    "parameters": {
        "negative_prompt": "",
        "prompt_extend": true,
        "watermark": false,
        "size": "1328*1328",
        "response_format": "url",
        "num_inference_steps": 10,
        "guidance_scale": 4.5,
        "seed": 12345,
        "n": 1,
        "width": 1328,
        "height": 1328
    }
}
```

### 响应示例
```json
{
    "output": {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": [
                        {
                            "image": "https://dashscope-result-wlcb-acdr-1.oss-cn-wulanchabu-acdr-1.aliyuncs.com/7d/41/20260102/cfc32567/c8a0a4ec-b160-4e86-8d35-fc52faa9af32-1.png?Expires=1767954867&OSSAccessKeyId=LTAI5tKPD3TMqf2Lna1fASuh&Signature=gJiSKUo9HV11ag%2BIDtSMds%2BRYPE%3D"
                        }
                    ],
                    "role": "assistant"
                }
            }
        ],
        "task_metric": {
            "FAILED": 0,
            "SUCCEEDED": 1,
            "TOTAL": 1
        }
    },
    "usage": {
        "height": 1328,
        "image_count": 1,
        "width": 1328
    },
    "request_id": "c8a0a4ec-b160-4e86-8d35-fc52faa9af32"
}
```

## 与 generate.py 的集成要点
- `generate.py` 已使用 `DiffusionPipeline` 加载同一模型，可作为推理核心：
	- 自动选择 `cuda`/`cpu` 与精度。
	- 支持 `prompt`、`negative_prompt`、`width`、`height`、`num_inference_steps`、`true_cfg_scale`、`seed`。
- 在接口实现中，可将经过 `rewrite()` 的 `prompt` 与请求参数传递给与 `generate.py` 等价的推理函数，返回 `image.save()` 或 base64。
- 建议复用 `generator=torch.Generator(device=device).manual_seed(seed)` 保持可重复性。

## 注意事项
- `prompt_extend` 建议默认开启，以提升可读性和合规性；若需完全原样生成，可将其设为 `false`。
- 当 `response_format=url` 时需提前配置 `PUBLIC_BASE_URL` 或 `IMAGE_DOWNLOAD_URL_PREFIX` 并确保静态文件挂载。
- 采样步数和 CFG 值过高会增加延迟或产生伪影，推荐 `num_inference_steps` 30–50、`guidance_scale` 3.5–5.0。
