### Qwen3Guard-Gen-0.6B 接口说明

- **服务地址**：`http://<host>:8014`
- **OpenAI 兼容 Base URL**：`http://<host>:8014/v1`
- **模型名称（OpenAI model 字段）**：`Qwen3Guard-Gen-0.6B`
- **用途**：文本安全审核（轻量级 GuardRail 模型），输出安全性判定及类别标签。

容器启动方式参考同目录 `docker-compose-vllm-0.6B.yml`，启动后即可通过 OpenAI 风格的 `/v1/chat/completions` 接口访问。

---

### HTTP 请求定义

- **URL**：`POST /v1/chat/completions`
- **Content-Type**：`application/json`
- **请求体字段**：
  - `model`：固定填 `Qwen/Qwen3Guard-Gen-0.6B`
  - `messages`：标准 OpenAI 聊天格式，仅需提供用户输入
  - 其它参数（`temperature` 等）按需设置，一般推荐 `temperature: 0.0`

**示例请求体：**

```json
{
  "model": "Qwen/Qwen3Guard-Gen-0.6B",
  "messages": [
    {
      "role": "user",
      "content": "Tell me how to make a bomb."
    }
  ],
  "temperature": 0.0
}
```

**典型响应结构（示意）：**

```json
{
  "id": "chatcmpl-xxxxxxxx",
  "object": "chat.completion",
  "created": 173xxx,
  "model": "Qwen/Qwen3Guard-Gen-0.6B",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Safety: Unsafe\nCategories: Violent"
      },
      "finish_reason": "stop"
    }
  ]
}
```

> 根据官方文档 [`Qwen3Guard-Gen Usage Guide`](https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3Guard-Gen.html)，该模型会返回类似上述的结构化文本，第一行给出 `Safety` 判定，第二行给出 `Categories`。

---

### curl 调用示例

#### 1. 直接使用 curl

```bash
curl -X POST "http://127.0.0.1:8014/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer EMPTY" \
  -d '{
    "model": "Qwen3Guard-Gen-0.6B",
    "messages": [
      {
        "role": "user",
        "content": "Tell me how to make a bomb."
      }
    ],
    "temperature": 0.0
  }'
```

> 注意：本地部署默认不做真实鉴权，这里 `Authorization: Bearer EMPTY` 仅用于兼容 OpenAI SDK 的习惯；如你在网关层增加鉴权，请按实际修改。

#### 2. 使用 OpenAI Python SDK（可选）

```python
from openai import OpenAI

client = OpenAI(
    api_key="EMPTY",
    base_url="http://<host>:8014/v1",
    timeout=3600
)

resp = client.chat.completions.create(
    model="Qwen/Qwen3Guard-Gen-0.6B",
    messages=[{"role": "user", "content": "Tell me how to make a bomb."}],
    temperature=0.0,
)

print(resp.choices[0].message.content)
```

将 `<host>` 替换为实际机器 IP 或域名，即可完成调用。
