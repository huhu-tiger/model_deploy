# MiniMax-M3 双节点 API 说明

MiniMax-M3（`minimax_m3_vl`）通过 SGLang 提供 **OpenAI 兼容** HTTP API，支持文本对话、流式输出、推理（thinking）与图片理解。

## 服务入口

| 入口 | 地址 | 说明 |
|------|------|------|
| nginx 代理（对外） | `http://<node-44-ip>:30002` | 推荐生产调用 |
| SGLang 直连 | `http://<node-44-ip>:30003` | 本机调试 |

- **API 节点**：node-44（172.31.0.44），node-43 为纯计算 worker，不对外暴露 HTTP。
- **模型 ID**：`/nvme01/MiniMax/MiniMax-M3`（与 `model_info` 中 `model_path` 一致）

### 路径前缀

nginx（30002）提供两种等价转发方式：

| 前缀 | 示例 | 转发目标 |
|------|------|----------|
| `/v1/` | `POST /v1/chat/completions` | `http://127.0.0.1:30003/v1/chat/completions` |
| `/llm/` | `GET /llm/model_info` | `http://127.0.0.1:30003/model_info` |

`/llm/` 会去掉前缀后转发；`/v1/` 保留 `/v1/` 路径。

### 超时

nginx 代理：`proxy_read_timeout 300s`。长文本或首次推理建议客户端设置 `--max-time 300` 或更高。

### 认证

当前 nginx 配置中 Bearer Token 校验已注释，**默认无需** `Authorization` 头。若后续启用，需携带：

```http
Authorization: Bearer <token>
```

---

## 健康检查

```bash
# 直连
curl -s http://127.0.0.1:30003/model_info | jq .

# nginx
curl -s http://127.0.0.1:30002/llm/model_info | jq .
```

典型响应字段：

```json
{
  "model_path": "/nvme01/MiniMax/MiniMax-M3",
  "is_generation": true,
  "has_image_understanding": true,
  "has_audio_understanding": false,
  "model_type": "minimax_m3_vl"
}
```

---

## 文本对话

### 非流式

```bash
curl -s http://127.0.0.1:30002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/nvme01/MiniMax/MiniMax-M3",
    "messages": [
      {"role": "user", "content": "用一句话介绍你自己"}
    ],
    "max_tokens": 128,
    "temperature": 0.7
  }' | jq -r '.choices[0].message.content'
```

### 流式

```bash
curl -N http://127.0.0.1:30002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/nvme01/MiniMax/MiniMax-M3",
    "messages": [
      {"role": "user", "content": "写一首关于春天的短诗"}
    ],
    "max_tokens": 256,
    "stream": true
  }'
```

### 关闭思考（thinking）

MiniMax-M3 的 chat template 使用 `thinking_mode` 控制是否输出思考过程（不是 Qwen 的 `enable_thinking`）。

在请求体中加入：

```json
"chat_template_kwargs": {"thinking_mode": "disabled"}
```

可选值：

| 值 | 说明 |
|----|------|
| `"disabled"` | **关闭思考**，不生成 `reasoning_content` |
| `"enabled"` | 强制每轮都思考 |
| `"adaptive"` | 默认，模型自行决定是否思考 |

```bash
curl -s http://127.0.0.1:30002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/nvme01/MiniMax/MiniMax-M3",
    "messages": [
      {"role": "user", "content": "用一句话介绍你自己"}
    ],
    "max_tokens": 128,
    "chat_template_kwargs": {"thinking_mode": "disabled"}
  }' | jq -r '.choices[0].message.content'
```

关闭后 `choices[0].message.reasoning_content` 为 `null`，仅返回最终答案 `content`。

### 推理（thinking 开启）

默认 `thinking_mode` 为 `adaptive`，复杂问题可能自动思考；强制开启：

```bash
curl -s http://127.0.0.1:30003/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/nvme01/MiniMax/MiniMax-M3",
    "messages": [
      {"role": "user", "content": "9.11 和 9.8 哪个大？请一步步推理"}
    ],
    "max_tokens": 512,
    "temperature": 0.6,
    "chat_template_kwargs": {"thinking_mode": "enabled"}
  }' | jq .
```

思考内容在 `message.reasoning_content`，最终回答在 `message.content`。

---

## 图片理解（Vision）

`messages[].content` 使用 OpenAI 多模态数组格式：`text` + `image_url`。

### 网络图片 URL

```bash
curl -s --max-time 300 http://127.0.0.1:30002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/nvme01/MiniMax/MiniMax-M3",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "text", "text": "请用中文详细描述这张图片的内容"},
          {
            "type": "image_url",
            "image_url": {
              "url": "https://img95.699pic.com/photo/40241/6812.jpg_wh300.jpg!/fh/300/quality/90"
            }
          }
        ]
      }
    ],
    "max_tokens": 512,
    "temperature": 0.7
  }' | jq -r '.choices[0].message.content'
```

> 服务端需能访问图片 URL；若外网不可达，请使用本地 base64 方式。

### 本地图片（base64）

```bash
IMG_B64=$(base64 -w0 /path/to/image.jpg)

curl -s --max-time 300 http://127.0.0.1:30003/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"/nvme01/MiniMax/MiniMax-M3\",
    \"messages\": [
      {
        \"role\": \"user\",
        \"content\": [
          {\"type\": \"text\", \"text\": \"图片里有什么？\"},
          {\"type\": \"image_url\", \"image_url\": {\"url\": \"data:image/jpeg;base64,${IMG_B64}\"}}
        ]
      }
    ],
    \"max_tokens\": 512
  }" | jq -r '.choices[0].message.content'
```

PNG 请将 `data:image/jpeg` 改为 `data:image/png`。

### 流式识图

```bash
curl -N --max-time 300 http://127.0.0.1:30003/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/nvme01/MiniMax/MiniMax-M3",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "用一句话概括这张图的主题"},
        {
          "type": "image_url",
          "image_url": {
            "url": "https://img95.699pic.com/photo/40241/6812.jpg_wh300.jpg!/fh/300/quality/90"
          }
        }
      ]
    }],
    "max_tokens": 256,
    "stream": true
  }'
```

---

## 常用请求参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `model` | string | 固定为 `/nvme01/MiniMax/MiniMax-M3` |
| `messages` | array | 对话历史，含 `role` / `content` |
| `max_tokens` | int | 最大生成 token 数 |
| `temperature` | float | 采样温度，默认参考模型 generation config（约 1.0） |
| `top_p` | float | 核采样，默认约 0.95 |
| `stream` | bool | `true` 启用 SSE 流式 |
| `chat_template_kwargs` | object | 模板参数；关闭思考：`{"thinking_mode": "disabled"}` |

---

## 响应格式

与非流式 OpenAI Chat Completions 兼容：

```json
{
  "id": "...",
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

流式响应为 `data: {...}` SSE 行，以 `data: [DONE]` 结束。

---

## 部署与运维

```bash
# 启动 / 重启双节点
./run restart

# 环境检查（含 hosts / ufw）
./run check

# 查看本机日志
./run logs
docker logs -f sg-minimax-m3
```

| 端口 | 用途 |
|------|------|
| 30002 | nginx OpenResty 代理 |
| 30003 | SGLang HTTP API |
| 20000 | 双节点 dist-init（内部，非业务 API） |

---

## 注意事项

1. **冷启动**：双节点握手 + 模型加载 + CUDA Graph 捕获约需 10–15 分钟，期间 `/model_info` 可能不可用。
2. **首次推理**：首条请求可能较慢（JIT / 预热），属正常现象。
3. **MoE 调优警告**：日志中 `Config file not found ... NVIDIA_H20.json` 为性能提示，不影响功能与正确性。
4. **防火墙**：node-44 若启用 ufw，需允许 node-43（172.31.0.43）入站；可执行 `./run firewall` 自动配置。
