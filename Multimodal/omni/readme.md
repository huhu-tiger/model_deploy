# Qwen3-Omni-30B-A3B-Instruct 部署文档

基于 [vLLM-Omni](https://github.com/vllm-project/vllm-omni) 部署 Qwen3-Omni 全模态模型，支持文本、图像、音频、视频输入，并可输出文本与语音。

---

## 环境信息

| 项目 | 值 |
|---|---|
| 模型 | Qwen3-Omni-30B-A3B-Instruct |
| 模型路径 | `/media/llm/Qwen/Qwen3-Omni-30B-A3B-Instruct/` |
| vLLM-Omni 镜像 | `model.vnet.com/sjhl/vllm-omni:v0.22.0` |
| 服务端口 | `9117`（容器内 `8091`） |
| GPU | 物理卡 2、3（容器内 cuda:0、cuda:1） |
| Stage 布局 | Stage 0 Thinker → cuda:0；Stage 1 Talker + Stage 2 Code2Wav → cuda:1 |

---

## 快速启动

```bash
cd /media/source/model_deploy/Multimodal/omni
docker compose up -d
```

查看日志：

```bash
docker logs -f vllm-qwen3-omni-30b
```

健康检查：

```bash
curl http://localhost:9117/health
```

停止服务：

```bash
docker compose down
```

---

## 启动参数说明

| 参数 / 配置 | 值 | 说明 |
|---|---|---|
| `--omni` | 启用 | 必须开启，走三阶段流水线 |
| `--deploy-config` | `deploy/qwen3_omni_a800.yaml` | A800 生产调优配置 |
| Stage 0 `max_num_seqs` | 20 | Thinker 并发上限 |
| Stage 1 `max_num_seqs` | 10 | Talker 并发上限 |
| Stage 2 `max_num_seqs` | 10 | Code2Wav 并发上限 |
| `async_chunk` | true | 默认开启流式分块输出 |

> 镜像内置默认配置路径：`/usr/local/lib/python3.12/dist-packages/vllm_omni/deploy/qwen3_omni_moe.yaml`

> 默认开启 `async_chunk` 时，`/v1/realtime` WebSocket 不可用；如需实时语音对话，将 deploy 配置中 `async_chunk` 改为 `false`。

---

## API 地址

```
http://<host>:9117/v1
```

模型名：`Qwen3-Omni-30B-A3B-Instruct`

---

## 输出模态控制

通过 `modalities` 字段控制输出类型：

| modalities | 输出 | 说明 |
|---|---|---|
| `["text"]` | 仅文本 | 跳过语音生成，延迟更低 |
| `["audio"]` | 文本 + 语音 | 返回文本理解与 TTS 音频 |
| `["text", "audio"]` | 文本 + 语音 | 同上 |
| 不指定 | 文本 + 语音 | 默认行为 |

---

## curl 调用示例

以下示例均使用端口 `9117`，将 `localhost` 替换为实际主机地址即可。

> **字段格式注意**：`type` 为 `image_url` / `audio_url` / `video_url` 时，必须使用嵌套的 `url` 字段，**不能**直接写 `image`、`audio`、`video`。
>
> | type | ✅ 正确 | ❌ 错误 |
> |---|---|---|
> | `image_url` | `{ "image_url": { "url": "..." } }` | `{ "image": "..." }` |
> | `audio_url` | `{ "audio_url": { "url": "..." } }` | `{ "audio": "..." }` |
> | `video_url` | `{ "video_url": { "url": "..." } }` | `{ "video": "..." }` |

### 1. 纯文本（仅文本输出）

```bash
curl http://localhost:9117/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-Omni-30B-A3B-Instruct",
    "modalities": ["text"],
    "messages": [
      {
        "role": "user",
        "content": "用一句话介绍你自己"
      }
    ]
  }'
```

### 2. 纯文本（文本 + 语音输出）

```bash
curl http://localhost:9117/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-Omni-30B-A3B-Instruct",
    "modalities": ["text", "audio"],
    "messages": [
      {
        "role": "user",
        "content": "用一句话介绍你自己"
      }
    ]
  }'
```

响应中 `choices[0]` 为文本，`choices[1]` 含音频数据（Base64）。

---

### 3. 图像 + 文本（图片 URL）

```bash
curl http://localhost:9117/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-Omni-30B-A3B-Instruct",
    "modalities": ["text"],
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "image_url",
            "image_url": {
              "url": "https://vllm-public-assets.s3.us-west-2.amazonaws.com/vision_model_images/cherry_blossom.jpg"
            }
          },
          {
            "type": "text",
            "text": "描述这张图片的内容"
          }
        ]
      }
    ]
  }'
```

### 4. 图像 + 文本（本地图片 Base64）

```bash
IMG_B64=$(base64 -w 0 /path/to/photo.jpg)

curl http://localhost:9117/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"Qwen3-Omni-30B-A3B-Instruct\",
    \"modalities\": [\"text\"],
    \"messages\": [
      {
        \"role\": \"user\",
        \"content\": [
          {
            \"type\": \"image_url\",
            \"image_url\": {
              \"url\": \"data:image/jpeg;base64,${IMG_B64}\"
            }
          },
          {
            \"type\": \"text\",
            \"text\": \"图中有什么内容？\"
          }
        ]
      }
    ]
  }"
```

---

### 5. 音频 + 文本（音频 URL）

```bash
curl http://localhost:9117/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-Omni-30B-A3B-Instruct",
    "modalities": ["text"],
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "audio_url",
            "audio_url": {
              "url": "https://vllm-public-assets.s3.us-west-2.amazonaws.com/multimodal_asset/mary_had_lamb.ogg"
            }
          },
          {
            "type": "text",
            "text": "这段音频的内容是什么？"
          }
        ]
      }
    ]
  }'
```

### 6. 音频 + 文本（本地音频 Base64）

```bash
AUDIO_B64=$(base64 -w 0 /path/to/audio.wav)

curl http://localhost:9117/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"Qwen3-Omni-30B-A3B-Instruct\",
    \"modalities\": [\"text\"],
    \"messages\": [
      {
        \"role\": \"user\",
        \"content\": [
          {
            \"type\": \"audio_url\",
            \"audio_url\": {
              \"url\": \"data:audio/wav;base64,${AUDIO_B64}\"
            }
          },
          {
            \"type\": \"text\",
            \"text\": \"转写并总结这段音频\"
          }
        ]
      }
    ]
  }"
```

---

### 7. 图像 + 音频 + 文本（多模态联合理解）

同时使用图片与音频输入，模型综合视觉与听觉信息作答：

```bash
curl http://localhost:9117/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-Omni-30B-A3B-Instruct",
    "stream": false,
    "modalities": ["text"],
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "image_url",
            "image_url": {
              "url": "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-Omni/demo/cars.jpg"
            }
          },
          {
            "type": "audio_url",
            "audio_url": {
              "url": "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-Omni/demo/cough.wav"
            }
          },
          {
            "type": "text",
            "text": "What can you see and hear? Answer in one short sentence."
          }
        ]
      }
    ]
  }'
```

---

### 8. 图像 + 文本输入，语音输出

理解图片后以语音形式回答（`modalities` 含 `audio` 会触发 Talker + Code2Wav 阶段）：

```bash
curl http://localhost:9117/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-Omni-30B-A3B-Instruct",
    "modalities": ["text", "audio"],
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "image_url",
            "image_url": {
              "url": "https://vllm-public-assets.s3.us-west-2.amazonaws.com/vision_model_images/cherry_blossom.jpg"
            }
          },
          {
            "type": "text",
            "text": "用简短的语言描述这张图片"
          }
        ]
      }
    ]
  }'
```

---

### 9. 带 System Prompt 的完整请求（推荐生产格式）

```bash
curl http://localhost:9117/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-Omni-30B-A3B-Instruct",
    "modalities": ["text"],
    "messages": [
      {
        "role": "system",
        "content": [
          {
            "type": "text",
            "text": "You are Qwen, a virtual human developed by the Qwen Team, Alibaba Group, capable of perceiving auditory and visual inputs, as well as generating text and speech."
          }
        ]
      },
      {
        "role": "user",
        "content": [
          {
            "type": "image_url",
            "image_url": {
              "url": "https://vllm-public-assets.s3.us-west-2.amazonaws.com/vision_model_images/cherry_blossom.jpg"
            }
          },
          {
            "type": "text",
            "text": "What is the content of this image?"
          }
        ]
      }
    ]
  }'
```

---

## 支持的多模态格式

### content 字段结构

每条 `content` 数组元素由 `type` 决定字段名：

```json
{ "type": "text",      "text": "..." }
{ "type": "image_url", "image_url": { "url": "https://..." } }
{ "type": "audio_url", "audio_url": { "url": "https://..." } }
{ "type": "video_url", "video_url": { "url": "https://..." } }
```

Base64 示例：

```json
{ "type": "image_url", "image_url": { "url": "data:image/jpeg;base64,<BASE64>" } }
{ "type": "audio_url", "audio_url": { "url": "data:audio/wav;base64,<BASE64>" } }
```

### 图像

| 格式 | MIME 类型 |
|---|---|
| JPEG / JPG | `image/jpeg` |
| PNG | `image/png` |
| WebP | `image/webp` |
| GIF | `image/gif` |

传入方式：HTTP/HTTPS URL、Base64 Data URI

### 音频

| 格式 | MIME 类型 |
|---|---|
| WAV | `audio/wav` |
| MP3 | `audio/mpeg` |
| OGG | `audio/ogg` |
| FLAC | `audio/flac` |
| M4A | `audio/mp4` |

传入方式：HTTP/HTTPS URL、Base64 Data URI

---

## 响应结构说明

**仅文本输出**（`modalities: ["text"]`）：

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "..."
      }
    }
  ]
}
```

**文本 + 语音输出**（`modalities: ["text", "audio"]`）：

```json
{
  "choices": [
    { "message": { "content": "文本回答..." } },
    { "message": { "audio": { "data": "<base64>", "format": "wav" } } }
  ]
}
```

提取文本回答：

```bash
curl -s http://localhost:9117/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen3-Omni-30B-A3B-Instruct","modalities":["text"],"messages":[{"role":"user","content":"你好"}]}' \
  | jq -r '.choices[0].message.content'
```

---

## GPU 配置

使用物理 GPU `2` 和 `3`，修改 `docker-compose.yml`：

```yaml
environment:
  - NVIDIA_VISIBLE_DEVICES=2,3
deploy:
  resources:
    reservations:
      devices:
        - device_ids: ["2", "3"]
```

deploy 配置中 `devices: "0"` / `"1"` 为容器内编号，无需随物理卡号修改。

---

## 常见问题

**Q: 启动报 `max_num_batched_tokens is smaller than max_model_len`？**

Stage 2（Code2Wav）的 `max_num_batched_tokens` 必须 ≥ `65536`，参见 `deploy/qwen3_omni_a800.yaml`。

**Q: 只需要理解图片/音频，不需要语音回答？**

请求中加 `"modalities": ["text"]`，跳过 Talker 和 Code2Wav，延迟显著降低。

**Q: 报错 `image_url Field required` 或 `audio_url Field required`？**

`type` 与字段名必须匹配。`type: "image_url"` 时用 `image_url.url`，不能用 `image`；`type: "audio_url"` 时用 `audio_url.url`，不能用 `audio`。参见上文「字段格式注意」。

**Q: 远程图片/音频拉取超时？**

已配置 `VLLM_IMAGE_FETCH_TIMEOUT=60`、`VLLM_AUDIO_FETCH_TIMEOUT=60`，可在 `docker-compose.yml` 中调大。

**Q: OOM 如何处理？**

依次降低 `deploy/qwen3_omni_a800.yaml` 中各 stage 的 `max_num_seqs`，再降 `gpu_memory_utilization`。

**Q: 如何切换为镜像内置默认配置？**

删除 `--deploy-config` 及对应 volume 挂载，vLLM-Omni 将自动加载 `qwen3_omni_moe.yaml`。

---

## 参考

- [vLLM-Omni Qwen3-Omni 官方文档](https://docs.vllm.ai/projects/vllm-omni/en/latest/)
- [Qwen3-Omni 在线服务示例](https://github.com/vllm-project/vllm-omni/tree/main/examples/online_serving/qwen3_omni)
