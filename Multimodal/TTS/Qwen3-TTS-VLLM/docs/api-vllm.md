# vLLM-Omni Qwen3-TTS API 使用文档

本文档基于 [vLLM-Omni Qwen3-TTS API](https://docs.vllm.ai/projects/vllm-omni/en/latest/user_guide/examples/online_serving/qwen3_tts/) 和 [Speech API](https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/speech_api/) 编写。

## 启动服务器

使用 Docker Compose 启动 vLLM-Omni 服务器：

```bash
cd /media/source/model_deploy/Qwen3-TTS-VLLM
docker-compose -f docker-compose-vllm.yml up -d
```

或者直接使用 vllm 命令：

```bash
vllm serve /media/llm/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice \
    --omni \
    --stage-configs-path vllm_omni/model_executor/stage_configs/qwen3_tts.yaml \
    --host 0.0.0.0 \
    --port 8091 \
    --gpu-memory-utilization 0.9 \
    --trust-remote-code \
    --enforce-eager
```

参数说明：
- `--omni`: 启用 vLLM-Omni 多模态支持
- `--stage-configs-path`: 指定 Qwen3-TTS 的 stage 配置文件
- `--port 8091`: 指定服务端口（默认 8091）
- `--gpu-memory-utilization 0.9`: GPU 内存使用率（0-1）
- `--enforce-eager`: 强制使用 eager 模式

## API 端点

### 1. 文本转语音

```
POST /v1/audio/speech
Content-Type: application/json
```

### 2. 获取可用音色列表

```
GET /v1/audio/voices
```

## 请求参数

### POST /v1/audio/speech

#### 必需参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `input` | string | 要合成的文本内容 |
| `model` | string | 模型名称，如 "Qwen3-TTS-12Hz-1.7B-CustomVoice" |

#### 可选参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `voice` | string | "vivian" | 音色/说话人名称（CustomVoice 任务） |
| `language` | string | "Auto" | 语言提示：Auto, Chinese, English 等 |
| `instructions` | string | - | 语音风格/情感指令，如 "用愉快的语气说" |
| `task_type` | string | "CustomVoice" | 任务类型：CustomVoice, VoiceDesign, Base |
| `response_format` | string | "wav" | 音频输出格式：wav, mp3, flac, pcm, aac, opus |
| `stream` | boolean | false | 是否流式输出（需配合 response_format="pcm"） |
| `speed` | float | 1.0 | 语速倍数（0.25-4.0），流式输出时不支持 |
| `max_new_tokens` | integer | - | 最大生成 token 数 |

#### 语音克隆参数（Base 任务）

| 参数 | 类型 | 说明 |
|------|------|------|
| `ref_audio` | string | 参考音频（URL 或 base64 data URL） |
| `ref_text` | string | 参考音频的转录文本（ICL 模式必需） |
| `x_vector_only_mode` | boolean | false | 是否仅使用 x-vector（true 时不需要 ref_text） |

## 响应格式

### 成功响应（非流式）

API 返回二进制音频数据，Content-Type 根据 `response_format` 设置：

- `wav`: `audio/wav`
- `mp3`: `audio/mpeg`
- `flac`: `audio/flac`
- `pcm`: `application/octet-stream`
- `aac`: `audio/aac`
- `opus`: `audio/opus`

响应头示例：
```
Content-Type: audio/wav
Content-Length: <audio_file_size>
```

### 流式响应（stream=true）

当 `stream=true` 且 `response_format="pcm"` 时，返回原始 PCM 音频块（每个 Code2Wav 窗口一个块，默认 25 帧，可在 stage config 中配置）。

格式：16-bit signed PCM, 24 kHz, mono

## 请求示例

### cURL - CustomVoice（预定义音色）

#### 中文示例

```bash
curl -X POST http://localhost:8091/v1/audio/speech \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer EMPTY" \
    -d '{
        "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "input": "你好，今天心情不错，想去散散步。",
        "voice": "vivian",
        "language": "Chinese",
        "instructions": "用愉快的语气说",
        "response_format": "wav"
    }' \
    --output output.wav
```

#### 英文示例

```bash
curl -X POST http://localhost:8091/v1/audio/speech \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer EMPTY" \
    -d '{
        "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "input": "Hello, how are you?",
        "voice": "vivian",
        "language": "English",
        "instructions": "Speak with excitement",
        "response_format": "wav"
    }' \
    --output output.wav
```

#### 使用不同音色

```bash
curl -X POST http://localhost:8091/v1/audio/speech \
    -H "Content-Type: application/json" \
    -d '{
        "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "input": "This is a test message.",
        "voice": "ryan",
        "language": "English",
        "response_format": "wav"
    }' \
    --output ryan_voice.wav
```

#### 输出不同格式（MP3）

```bash
curl -X POST http://localhost:8091/v1/audio/speech \
    -H "Content-Type: application/json" \
    -d '{
        "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "input": "Hello world",
        "voice": "vivian",
        "response_format": "mp3"
    }' \
    --output output.mp3
```

#### 调整语速

```bash
curl -X POST http://localhost:8091/v1/audio/speech \
    -H "Content-Type: application/json" \
    -d '{
        "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "input": "This is a test with faster speech.",
        "voice": "vivian",
        "speed": 1.5,
        "response_format": "wav"
    }' \
    --output fast_speech.wav
```

### cURL - 流式输出（PCM）

流式输出返回原始 PCM 音频块，适合实时播放。

```bash
curl -X POST http://localhost:8091/v1/audio/speech \
    -H "Content-Type: application/json" \
    -d '{
        "input": "Hello, how are you?",
        "voice": "vivian",
        "language": "English",
        "stream": true,
        "response_format": "pcm"
    }' --no-buffer | play -t raw -r 24000 -e signed -b 16 -c 1 -
```

保存流式 PCM 到文件：

```bash
curl -X POST http://localhost:8091/v1/audio/speech \
    -H "Content-Type: application/json" \
    -d '{
        "input": "Hello, how are you?",
        "voice": "vivian",
        "stream": true,
        "response_format": "pcm"
    }' --no-buffer > output.pcm
```

**注意**：
- 流式输出必须使用 `response_format="pcm"`
- 流式输出时不支持 `speed` 参数调整
- PCM 格式：16-bit signed, 24 kHz, mono

### cURL - VoiceDesign（从描述生成音色）

#### 英文描述示例

```bash
curl -X POST http://localhost:8091/v1/audio/speech \
    -H "Content-Type: application/json" \
    -d '{
        "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "input": "Hello world",
        "task_type": "VoiceDesign",
        "instructions": "A warm, friendly female voice",
        "response_format": "wav"
    }' \
    --output voice_design.wav
```

#### 中文描述示例

```bash
curl -X POST http://localhost:8091/v1/audio/speech \
    -H "Content-Type: application/json" \
    -d '{
        "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "input": "这是一段测试文本",
        "task_type": "VoiceDesign",
        "instructions": "温柔、亲切的女性声音",
        "language": "Chinese",
        "response_format": "wav"
    }' \
    --output voice_design_cn.wav
```

### cURL - Base（语音克隆）

#### 使用参考音频 URL

#### 使用 base64 编码的音频

首先将音频文件编码为 base64：

```bash
# 将音频文件编码为 base64 data URL
REF_AUDIO_B64=$(base64 -w 0 reference.wav)
REF_AUDIO_DATA_URL="data:audio/wav;base64,${REF_AUDIO_B64}"

# 发送请求
curl -X POST http://localhost:8091/v1/audio/speech \
    -H "Content-Type: application/json" \
    -d "{
        \"model\": \"Qwen3-TTS-12Hz-1.7B-CustomVoice\",
        \"input\": \"Hello world\",
        \"task_type\": \"Base\",
        \"ref_audio\": \"${REF_AUDIO_DATA_URL}\",
        \"ref_text\": \"This is the reference transcript\",
        \"response_format\": \"wav\"
    }" \
    --output cloned.wav
```

或者使用 Python 生成 base64（仅用于生成 data URL）：

```bash
# 使用 Python 生成 base64 data URL（一次性使用）
python3 -c "
import base64
with open('reference.wav', 'rb') as f:
    audio_b64 = base64.b64encode(f.read()).decode('utf-8')
    print(f'data:audio/wav;base64,{audio_b64}')
" > ref_audio_b64.txt

# 然后在 curl 中使用
REF_AUDIO_DATA_URL=$(cat ref_audio_b64.txt)
curl -X POST http://localhost:8091/v1/audio/speech \
    -H "Content-Type: application/json" \
    -d "{
        \"model\": \"Qwen3-TTS-12Hz-1.7B-CustomVoice\",
        \"input\": \"Hello world\",
        \"task_type\": \"Base\",
        \"ref_audio\": \"${REF_AUDIO_DATA_URL}\",
        \"ref_text\": \"This is the reference transcript\",
        \"response_format\": \"wav\"
    }" \
    --output cloned.wav
```

#### x-vector 模式（不需要 ref_text）

```bash
curl -X POST http://localhost:8091/v1/audio/speech \
    -H "Content-Type: application/json" \
    -d '{
        "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "input": "Hello world",
        "task_type": "Base",
        "ref_audio": "https://example.com/reference.wav",
        "x_vector_only_mode": true,
        "response_format": "wav"
    }' \
    --output cloned_xvector.wav
```

## GET /v1/audio/voices

获取当前加载模型支持的所有音色列表。

### 请求示例

```bash
curl http://localhost:8091/v1/audio/voices
```

### 响应示例

```json
{
  "voices": [
    "vivian",
    "ryan",
    "aiden",
    "emma",
    "olivia"
  ]
}
```

## 错误处理

### 400 Bad Request

```json
{
  "error": {
    "message": "stream=true requires response_format='pcm'",
    "type": "invalid_request_error"
  }
}
```

原因：流式输出必须使用 `response_format="pcm"`

### 422 Unprocessable Entity

```json
{
  "error": {
    "message": "Unsupported speaker: unknown_voice",
    "type": "invalid_request_error"
  }
}
```

原因：使用了不支持的音色名称，可通过 `/v1/audio/voices` 查询可用音色

### 500 Internal Server Error

```json
{
  "error": {
    "message": "TTS model did not produce audio output",
    "type": "internal_server_error"
  }
}
```

原因：模型推理失败，检查模型类型是否与任务类型匹配

## 使用建议

1. **任务类型选择**：
   - `CustomVoice`: 使用预定义音色（如 vivian, ryan），适合常规 TTS
   - `VoiceDesign`: 通过自然语言描述生成音色，需要 VoiceDesign 模型
   - `Base`: 语音克隆，需要参考音频，适合个性化需求

2. **模型选择**：
   - CustomVoice 任务：使用 `Qwen3-TTS-12Hz-1.7B-CustomVoice`
   - VoiceDesign 任务：使用 `Qwen3-TTS-12Hz-1.7B-VoiceDesign`
   - Base 任务：使用 `Qwen3-TTS-12Hz-1.7B-Base`

3. **流式输出**：
   - 仅支持 `response_format="pcm"`（16-bit signed, 24 kHz, mono）
   - 流式输出时不能使用 `speed` 参数
   - 需要服务器 stage config 中启用 `async_chunk: true`（默认已启用）

4. **语音克隆**：
   - ICL 模式（`x_vector_only_mode=false`）：需要提供 `ref_text`，效果更好
   - x-vector 模式（`x_vector_only_mode=true`）：不需要 `ref_text`，速度更快但效果可能略差

5. **性能优化**：
   - 使用较小的模型变体（如 0.6B）可减少内存占用
   - 调整 `--gpu-memory-utilization` 参数平衡内存和性能
   - 批量处理当前未优化，建议单请求处理

## 限制

- **单请求处理**：批量处理尚未针对在线服务优化
- **流式输出**：仅支持 PCM 格式，且不支持语速调整
- **内存占用**：1.7B 模型需要较大 GPU 内存，建议至少 8GB

## 故障排查

1. **TTS 模型未产生音频输出**：
   - 确保使用的模型变体与任务类型匹配
   - CustomVoice 任务 → CustomVoice 模型
   - VoiceDesign 任务 → VoiceDesign 模型
   - Base 任务 → Base 模型

2. **连接被拒绝**：
   - 检查服务器是否在正确的端口运行（默认 8091）
   - 检查防火墙设置

3. **内存不足**：
   - 使用较小的模型变体（`Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`）
   - 降低 `--gpu-memory-utilization` 参数（如 0.7）

4. **不支持的音色**：
   - 使用 `/v1/audio/voices` 端点查询当前模型支持的音色列表

5. **语音克隆失败**：
   - 确保使用 Base 模型变体进行语音克隆
   - 检查参考音频格式是否支持（WAV, MP3, FLAC, OGG）
   - ICL 模式必须提供 `ref_text`

## 参考链接

- [vLLM-Omni Qwen3-TTS 文档](https://docs.vllm.ai/projects/vllm-omni/en/latest/user_guide/examples/online_serving/qwen3_tts/)
- [vLLM-Omni Speech API 文档](https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/speech_api/)
