# Ming-omni-tts-0.5B API 使用文档

基于 [vLLM-Omni Text-To-Speech 在线服务文档](https://docs.vllm.ai/projects/vllm-omni/en/latest/user_guide/examples/online_serving/text_to_speech/) 与 [Speech API](https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/speech_api/) 编写。

## 模型能力（Supported Models）

| 项目 | 说明 |
|------|------|
| HuggingFace | [inclusionAI/Ming-omni-tts-0.5B](https://huggingface.co/inclusionAI/Ming-omni-tts-0.5B) |
| 架构 | Dense 0.5B 双 stage TTS（LLM+flow → Audio VAE） |
| 语音克隆 | ✓（`ref_audio` / `speaker_embedding`） |
| 流式输出 | ✓（PCM stream，async-chunk） |
| 音色 / 控制 | IP 音色标签 + `instructions` 结构化控制 |
| Gradio | — |

在线服务仅支持 speech 形态；music-only `bgm` 与 text-to-audio `tta` 仍为 offline 示例。

---

## 环境信息

| 项目 | 值 |
|------|-----|
| 本地模型路径 | `/media/llm/inclusionAI/Ming-omni-tts-0.5B` |
| vLLM-Omni 镜像 | `model.vnet.com/sjhl/vllm-omni:v0.24.0rc1` |
| Deploy 配置 | `./deploy/ming_tts.yaml`（对应官方 `vllm_omni/deploy/ming_tts.yaml`） |
| 服务端口 | `9132`（容器内 `8091`） |
| GPU | 默认物理卡 6 |
| 采样率 | 44100 Hz mono |

> **镜像版本**：Ming-omni-tts dense 0.5B 需要 vLLM-Omni **≥ v0.24.0rc1**（含 `ming_tts` pipeline）。v0.22.0 会误走 diffusion 并报 `BailingMMNativeForConditionalGeneration not found in diffusion model registry`。

---

## 启动服务

等价于官方命令（本地路径 + 自定义端口映射）：

```bash
vllm serve /media/llm/inclusionAI/Ming-omni-tts-0.5B \
  --omni \
  --deploy-config /deploy/ming_tts.yaml \
  --host 0.0.0.0 \
  --port 8091 \
  --served-model-name Ming-omni-tts-0.5B \
  --enforce-eager
```

本仓库使用 Docker Compose + Makefile：

```bash
cd /media/source/model_deploy/Multimodal/TTS/Ming-omni-tts-0.5B
make up          # 启动
make logs        # 日志
make health      # 健康检查
make down        # 停止
```

---

## API 基础信息

- **Base URL**：`http://<host>:9132/v1`
- **鉴权**：`api_key="none"` 或 `"EMPTY"`
- **模型名**（`model` 字段）：`Ming-omni-tts-0.5B`（由 `--served-model-name` 指定；官方示例亦可用 `inclusionAI/Ming-omni-tts-0.5B`）

---

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/audio/speech` | 文本转语音 |
| GET | `/health` | 健康检查 |

---

## 请求参数（POST /v1/audio/speech）

### 必需参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `input` | string | 待合成文本 |
| `model` | string | `Ming-omni-tts-0.5B` |

### Ming 专用字段

| 字段 | Ming 含义 |
|------|-----------|
| `input` | 目标文本 |
| `instructions` | 纯文本风格描述，或 JSON 结构化控制（语速/情感/方言等） |
| `voice` | Ming IP 音色标签 |
| `language` | Ming `方言` 控制 |
| `ref_audio` | 说话人参考；配合 `ref_text` 时同时提供 prompt 波形 |
| `ref_text` | 参考转录，用于 zero-shot 或播客式多说话人 |
| `speaker_embedding` | 192 维 Ming speaker embedding |
| `max_new_tokens` | 对应 Ming `max_decode_steps` |

### 通用字段

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `response_format` | string | `wav` | `wav`、`pcm` 等 |
| `stream` | boolean | `false` | 流式输出 |
| `stream_format` | string | - | 流式时需设为 `"audio"` |

### `ref_audio` 行为

| 组合 | 行为 |
|------|------|
| 仅 `ref_audio` | 提取 speaker embedding（`use_spk_emb=True`），不作 zero-shot prompt |
| `ref_audio` + `ref_text` | zero-shot 语音克隆 |
| 多个 `ref_audio` + 对应 `ref_text` | 播客式多说话人（文本含 `speaker_1:` / `speaker_2:`） |

`ref_audio` 支持：本地路径、`file://`、HTTP URL、`data:` base64 URL。

---

## 响应格式

| 模式 | 输出 |
|------|------|
| 非流式 | WAV 二进制（`response_format="wav"`） |
| 流式 | PCM 块（`stream=true` + `stream_format="audio"` + `response_format="pcm"`） |

流式 PCM：16-bit signed PCM，44100 Hz，mono。播放示例：

```bash
play -t raw -r 44100 -e signed -b 16 -c 1 ming_output.pcm
```

---

## 请求示例

端口 `9132` 对应本部署；将 `localhost` 替换为实际主机。

### 1. 基础 TTS

```bash
curl -X POST http://localhost:9132/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Ming-omni-tts-0.5B",
    "input": "你好，这是 Ming 在线语音合成测试。",
    "response_format": "wav"
  }' \
  --output ming_output.wav
```

### 2. 方言控制（广粤话）

```bash
curl -X POST http://localhost:9132/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Ming-omni-tts-0.5B",
    "input": "我觉得社会企业同个人都有责任",
    "instructions": {"方言": "广粤话"},
    "ref_audio": "/path/to/yue_prompt.wav",
    "response_format": "wav"
  }' \
  --output ming_yue.wav
```

### 3. Zero-shot 语音克隆

```bash
curl -X POST http://localhost:9132/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Ming-omni-tts-0.5B",
    "input": "我们的愿景是构建未来服务业的数字化基础设施，为世界带来更多微小而美好的改变。",
    "ref_audio": "/path/to/10002287-00000094.wav",
    "ref_text": "在此奉劝大家别乱打美白针。",
    "response_format": "wav"
  }' \
  --output ming_clone.wav
```

### 4. 结构化风格控制

```bash
curl -X POST http://localhost:9132/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Ming-omni-tts-0.5B",
    "input": "今天天气真好，我们出去散步吧。",
    "instructions": {"语速": "快速", "基频": "中", "音量": "中", "情感": "开心"},
    "response_format": "wav"
  }' \
  --output ming_style.wav
```

### 5. 流式 PCM

官方要求同时设置 `stream`、`stream_format`、`response_format`：

```bash
curl -X POST http://localhost:9132/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Ming-omni-tts-0.5B",
    "input": "你好，这是流式输出测试。",
    "stream": true,
    "stream_format": "audio",
    "response_format": "pcm"
  }' \
  --no-buffer \
  --output ming_stream.pcm
```

### 6. Python（OpenAI SDK）

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:9132/v1", api_key="none")

response = client.audio.speech.create(
    model="Ming-omni-tts-0.5B",
    input="你好，这是 Ming 在线语音合成测试。",
    response_format="wav",
)
response.stream_to_file("ming_output.wav")
```

### 7. Python（httpx）

```python
import httpx

resp = httpx.post(
    "http://localhost:9132/v1/audio/speech",
    json={
        "model": "Ming-omni-tts-0.5B",
        "input": "我觉得社会企业同个人都有责任",
        "instructions": {"方言": "广粤话"},
        "ref_audio": "/path/to/yue_prompt.wav",
        "max_new_tokens": 200,
        "response_format": "wav",
    },
    timeout=300.0,
)
resp.raise_for_status()
open("ming_yue.wav", "wb").write(resp.content)
```

---

## 错误排查

| 现象 | 处理 |
|------|------|
| `BailingMMNativeForConditionalGeneration not found in diffusion model registry` | 升级镜像至 **v0.24.0rc1+** |
| 连接失败 | `make up` 后确认端口 `9132` |
| 健康检查超时 | `make logs`，首次加载约 2–3 分钟 |
| OOM | 调低 `deploy/ming_tts.yaml` 中 `gpu_memory_utilization` |

---

## 参考链接

- [Supported Models（官方）](https://docs.vllm.ai/projects/vllm-omni/en/latest/user_guide/examples/online_serving/text_to_speech/#supported-models)
- [Ming-omni-tts 章节（官方）](https://docs.vllm.ai/projects/vllm-omni/en/latest/user_guide/examples/online_serving/text_to_speech/#ming-omni-tts)
- [Speech API Reference](https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/speech_api/)
- [Ming-omni-tts Recipe（ROCm/CUDA 验证环境）](https://github.com/vllm-project/vllm-omni/blob/main/recipes/inclusionAI/Ming-omni-tts-0.5B.md)
- [Ming-omni-tts 项目页](https://xqacmer.github.io/Ming-omni-tts/)
