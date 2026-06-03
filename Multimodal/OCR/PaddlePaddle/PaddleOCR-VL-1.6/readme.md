## PaddleOCR-VL-1.5 部署与接口说明

### 一、服务信息

- **模型**：PaddleOCR-VL-1.5-0.9B（vLLM 推理）
- **主页**：[https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5)
- **容器**：`ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-genai-vllm-server:latest-nvidia-gpu`
- **监听地址**：`0.0.0.0`
- **端口**：`8081`
- **GPU 使用**：仅使用第 **7** 号 GPU
- **容器用户**：`root`（`user: "0:0"`，`privileged: true`）
- **数据挂载**：宿主机 `/media/llm/paddleocr` → 容器 `/home/paddleocr/.paddlex`

对应 `docker-compose.yml` 关键片段（简化）：

```yaml
services:
  paddleocr-vl:
    image: ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-genai-vllm-server:latest-nvidia-gpu
    container_name: paddleocr-genai-vllm-server
    runtime: nvidia
    user: "0:0"
    privileged: true
    volumes:
      - /media/llm/paddleocr:/home/paddleocr/.paddlex
    ipc: host
    ports:
      - "8081:8081"
    command: >
      paddleocr genai_server
      --model_name PaddleOCR-VL-1.5-0.9B
      --host 0.0.0.0
      --port 8081
      --backend vllm
```

启动 / 停止命令：

```bash
cd /media/source/model_deploy/Multimodal/OCR/PaddlePaddle/PaddleOCR-VL-1.5
docker compose up -d    # 启动
docker compose down     # 停止并删除容器
```

---

### 二、HTTP API 概览

本服务兼容 **OpenAI Chat Completions** 协议，可直接使用 OpenAI 官方 SDK 访问。

- **Base URL**：`http://<服务器IP>:8081/v1`
- **主要接口**：`POST /v1/chat/completions`
- **内容类型**：`application/json`
- **鉴权**：示例中使用 `Authorization: Bearer EMPTY`，可根据需要自行实现真实鉴权。

---

### 三、接口定义：`POST /v1/chat/completions`

#### 1. 请求头

- `Content-Type: application/json`
- `Authorization: Bearer <API_KEY>`（如无鉴权，可写任意值或省略）

#### 2. 请求体（Request Body）

```json
{
  "model": "PaddleOCR-VL-1.5-0.9B",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "image_url",
          "image_url": {
            "url": "https://example.com/your-image.png"
          }
        },
        {
          "type": "text",
          "text": "OCR:"
        }
      ]
    }
  ],
  "temperature": 0.0
}
```

- **model**
  - 默认：`"PaddlePaddle/PaddleOCR-VL"`
  - 如启动 vLLM 时指定 `--served-model-name PaddleOCR-VL-0.9B`，则此处填 `"PaddleOCR-VL-0.9B"`。
- **messages**
  - `role`：`"user" | "system" | "assistant"`
  - `content`：数组，支持多模态内容：
    - 图像块：
      - `type: "image_url"`
      - `image_url.url`：图片 URL（HTTP/HTTPS）
    - 文本块：
      - `type: "text"`
      - `text`：任务提示词（见下文任务类型）
- **temperature**
  - 采样温度，OCR 场景建议 `0.0`，提高稳定性。

#### 3. 任务类型提示词

参考官方文档 [PaddleOCR-VL Usage Guide](https://docs.vllm.ai/projects/recipes/en/latest/PaddlePaddle/PaddleOCR-VL.html#querying-with-openai-api-client)，不同任务通过文本提示词区分：

- **通用 OCR**：`"OCR:"`
- **表格识别**：`"Table Recognition:"`
- **公式识别**：`"Formula Recognition:"`
- **图表识别**：`"Chart Recognition:"`

示例：表格识别时仅需将上面示例中的 `"OCR:"` 替换为 `"Table Recognition:"`。

---

### 四、响应说明（Response）

成功时返回与 OpenAI Chat Completions 类似的结构，例如：

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1737360000,
  "model": "PaddlePaddle/PaddleOCR-VL",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "识别结果文本..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 123,
    "completion_tokens": 45,
    "total_tokens": 168
  }
}
```

- **主要字段**
  - `choices[0].message.content`：模型输出的文本内容，即 OCR / 表格 / 公式 / 图表解析结果。
  - `usage`：提示词、生成内容 token 统计（如启动时开启统计）。

HTTP 状态码：

- `200`：请求成功。
- `4xx / 5xx`：请求失败，含错误信息（与 vLLM/OpenAI 兼容）。

---

### 五、调用示例

#### 1. curl 示例（通用 OCR，固定 IP）

```bash
curl --location --request POST 'http://39.155.179.4:8081/v1/chat/completions' \
--header 'Content-Type: application/json' \
--data-raw '{
    "model": "PaddleOCR-VL-1.5-0.9B",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "image_url",
            "image_url": {
              "url": "https://ofasys-multimodal-wlcb-3-toshanghai.oss-accelerate.aliyuncs.com/wpf272043/keepme/image/receipt.png"
            }
          },
          {
            "type": "text",
            "text": "OCR:"
          }
        ]
      }
    ],
    "temperature": 0.0
  }'
```

#### 2. Python 示例（官方 OpenAI 客户端）

```python
from openai import OpenAI

client = OpenAI(
    api_key="EMPTY",  # 如有真实鉴权，可替换
    base_url="http://<服务器IP>:8081/v1",
    timeout=3600
)

TASKS = {
    "ocr": "OCR:",
    "table": "Table Recognition:",
    "formula": "Formula Recognition:",
    "chart": "Chart Recognition:",
}

messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://ofasys-multimodal-wlcb-3-toshanghai.oss-accelerate.aliyuncs.com/wpf272043/keepme/image/receipt.png"
                }
            },
            {
                "type": "text",
                "text": TASKS["ocr"]  # 根据任务选择不同提示词
            }
        ]
    }
]

response = client.chat.completions.create(
    model="PaddlePaddle/PaddleOCR-VL",
    messages=messages,
    temperature=0.0,
)

print("Generated text:", response.choices[0].message.content)
```

---

### 六、注意事项与配置建议

- 本说明基于官方文档 [PaddleOCR-VL Usage Guide](https://docs.vllm.ai/projects/recipes/en/latest/PaddlePaddle/PaddleOCR-VL.html#querying-with-openai-api-client)。
- OCR 场景通常不需要多轮长对话，建议：
  - 关闭前缀缓存、图片复用等特性（由后端 vLLM 配置负责）。
  - 根据显存情况调整 `max_num_batched_tokens` 以提升吞吐。
- 若遇到报错 `The model PaddleOCR-VL-0.9B does not exist.`：
  - 启动 vLLM 时增加参数：`--served-model-name PaddleOCR-VL-0.9B`
  - 并在请求中将 `model` 字段改为 `"PaddleOCR-VL-0.9B"`。

