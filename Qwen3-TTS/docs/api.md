# Qwen3-TTS（OpenAI 风格）音频接口文档

本文档描述 `Qwen3-TTS/api.py` 提供的 3 个端点：
- `/v1/audio/speech`：CustomVoice（预置音色 + 可选风格指令）
- `/v1/audio/voice_design`：VoiceDesign（自然语言“设计”音色/风格）
- `/v1/audio/voice_clone`：Base / VoiceClone（参考音频克隆音色）

接口返回尽量对齐 OpenAI 的“choices/message/content”结构，生成的音频会先保存为临时文件并上传到 MinIO，最终返回 **MinIO 下载 URL**。

## Base URL

默认：

```
http://<host>:<port>
```

直接运行 `api.py` 时默认端口是 `6006`（可用环境变量 `PORT` 覆盖）。

## 健康检查与模型列表

- `GET /healthz` → `{ "status": "ok", "model": "..." }`
- `GET /v1/models` → OpenAI 风格的模型列表（包含 CustomVoice / Base / VoiceDesign 三个 model id）

## 通用约束

- `Content-Type: application/json`
- `stream`：当前不支持，必须为 `false`
- `response_format`：
  - `url`：上传 WAV 到 MinIO 并返回下载链接
  - `wav` / `flac`：会以对应扩展名保存临时文件后上传（底层仍返回 URL）

## POST /v1/audio/speech（CustomVoice）

使用 CustomVoice 模型根据文本生成语音。

### 请求体

```json
{
  "model": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
  "input": "你好，今天心情不错，想去散散步。",
  "voice": "Vivian",
  "language": "Chinese",
  "instruct": "用愉快的语气说",
  "response_format": "url",
  "stream": false,
  "max_new_tokens": 2048
}
```

字段说明：
- `model`：必须匹配环境变量 `TTS_MODEL_ID`
- `input`：要合成的文本
- `voice`：音色/说话人（默认 `TTS_DEFAULT_VOICE`）
- `language`：语言提示（默认 `TTS_DEFAULT_LANGUAGE`）
- `instruct`：风格控制（可为空字符串）
- `max_new_tokens`：生成长度提示

### 成功响应（示例）

```json
{
  "id": "8f6e0d3f-7c9c-4c8b-9b0a-0b8c5f3a9f90",
  "object": "audio.speech",
  "created": 1737979200,
  "model": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
  "voice": "Vivian",
  "output": {
    "choices": [
      {
        "index": 0,
        "finish_reason": "stop",
        "message": {
          "role": "assistant",
          "content": [
            {
              "audio": "http://<minio-host>:9000/files/qwen3-tts/2026-01-27/1706332800/qwen3_tts.wav",
              "format": "wav",
              "minio_path": "qwen3-tts/2026-01-27/1706332800/qwen3_tts.wav",
              "duration": 3.42
            }
          ]
        }
      }
    ],
    "task_metric": { "FAILED": 0, "SUCCEEDED": 1, "TOTAL": 1 }
  },
  "usage": { "duration": 3.42, "input_length": 16 },
  "request_id": "2c3c8fb0-9a6a-4bc4-8c1d-6fb6a9c45c12"
}
```

关注字段：
- `output.choices[0].message.content[0].audio`：MinIO 下载链接
- `output.choices[0].message.content[0].minio_path`：MinIO 对象 key
- `usage.duration`：音频时长（秒）

### 错误响应

- 400：`model` 不匹配 / `stream=true`
- 500：推理失败或 MinIO 上传失败

### curl 示例

```bash
curl -X POST http://127.0.0.1:6006/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "input": "请用温柔的语气读下面这句话，祝你有美好的一天。",
    "voice": "Vivian",
    "language": "Chinese",
    "instruct": "温柔，微笑，放松",
    "response_format": "url",
    "stream": false
  }'
```

## POST /v1/audio/voice_design（VoiceDesign）

使用 VoiceDesign 模型生成语音，风格/音色主要由 `instruct` 控制。

### 请求体

```json
{
  "model": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
  "input": "哥哥，你回来啦，人家等了你好久好久了，要抱抱！",
  "language": "Chinese",
  "instruct": "体现撒娇稚嫩的萝莉女声，音调偏高且起伏明显",
  "response_format": "url",
  "stream": false,
  "max_new_tokens": 2048
}
```

与 `/v1/audio/speech` 的差异：
- 不使用 `voice` 字段；音色/风格来自 `instruct`
- `model` 必须匹配 `TTS_VOICE_DESIGN_MODEL_ID`

响应结构与 `/v1/audio/speech` 一致（返回 `audio` URL、`minio_path`、`duration` 等）。

### curl 示例

```bash
curl -X POST http://127.0.0.1:6006/v1/audio/voice_design \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "input": "哥哥，你回来啦，人家等了你好久好久了，要抱抱！",
    "language": "Chinese",
    "instruct": "体现撒娇稚嫩的萝莉女声，音调偏高且起伏明显",
    "response_format": "url",
    "stream": false
  }'
```

## POST /v1/audio/voice_clone（Base / VoiceClone）

使用 Base 模型做音色克隆：给一段参考音频（可选参考文本），对目标文本进行合成。

### 请求体

```json
{
  "model": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
  "input": "Good one. Okay, fine, I'm just gonna leave this sock monkey here. Goodbye.",
  "language": "Auto",
  "ref_audio": "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-TTS-Repo/clone_2.wav",
  "ref_text": "Okay. Yeah. I resent you. I love you. I respect you. But you know what? You blew it! And thanks to you.",
  "x_vector_only_mode": false,
  "response_format": "url",
  "stream": false,
  "max_new_tokens": 2048
}
```

字段说明：
- `model`：必须匹配 `TTS_BASE_MODEL_ID`
- `ref_audio`：
  - `string`：参考音频（URL / 本地 wav 路径 / base64 音频字符串）
  - `string[]`：批量参考音频
- `ref_text`：
  - 当 `x_vector_only_mode=false`（ICL 模式）时 **必须提供**（字符串或列表）
  - 当 `x_vector_only_mode=true` 时可省略（只用说话人 embedding）
- `x_vector_only_mode`：`true` 仅克隆音色，不做 ICL；`false` 使用 ICL（更依赖 ref_text）

响应结构与 `/v1/audio/speech` 一致（`audio` URL、`minio_path`、`duration` 等）。其中响应里的 `voice` 字段固定为 `"voice_clone"`。

### curl 示例

```bash
curl -X POST http://127.0.0.1:6006/v1/audio/voice_clone \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    "input": "Good one. Okay, fine, I\\u0027m just gonna leave this sock monkey here. Goodbye.",
    "language": "Auto",
    "ref_audio": "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-TTS-Repo/clone_2.wav",
    "ref_text": "Okay. Yeah. I resent you. I love you. I respect you. But you know what? You blew it! And thanks to you.",
    "x_vector_only_mode": false,
    "response_format": "url",
    "stream": false
  }'
```

## 配置（环境变量）

服务读取如下环境变量（见 `api.py`）：
- `TTS_MODEL_ID`：CustomVoice 的期望 model 名称（默认 `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`）
- `TTS_MODEL_PATH`：CustomVoice 的模型路径/ID（默认同 `TTS_MODEL_ID`）
- `TTS_BASE_MODEL_ID`：Base 的期望 model 名称（默认 `Qwen/Qwen3-TTS-12Hz-1.7B-Base`）
- `TTS_BASE_MODEL_PATH`：Base 的模型路径/ID（默认同 `TTS_BASE_MODEL_ID`）
- `TTS_VOICE_DESIGN_MODEL_ID`：VoiceDesign 的期望 model 名称（默认 `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`）
- `TTS_VOICE_DESIGN_MODEL_PATH`：VoiceDesign 的模型路径/ID（默认同 `TTS_VOICE_DESIGN_MODEL_ID`）
- `TTS_DEVICE`：device map（默认 `cuda:0`，无 CUDA 则 `cpu`）
- `TTS_DTYPE`：torch dtype 字符串（默认 CUDA 用 `bfloat16`，CPU 用 `float32`）
- `TTS_ATTN_IMPL`：attention 实现（默认 `flash_attention_2`）
- `TTS_DEFAULT_VOICE`：CustomVoice 默认 speaker（默认 Vivian）
- `TTS_DEFAULT_LANGUAGE`：默认语言（默认 Chinese）
- `TTS_OUTPUT_DIR`：生成临时文件目录（默认 `<repo>/Qwen3-TTS/outputs`）
- `TTS_MINIO_UPLOAD_DIR`：MinIO 上传前缀目录（默认 `qwen3-tts`）
- MinIO 连接配置：来自 `vnet.common.storage.dal.minio.minio_conn` 相关环境变量（如 `MINIO_IP`, `MINIO_UPLOAD_PORT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET_NAME`）
- `PORT`：HTTP 端口（默认 6006）

## 备注

- 目前 3 个端点都已接入，并统一上传 MinIO 返回下载 URL。
- `stream` 仍被禁用（需要先实现真正的流式返回再开启）。
