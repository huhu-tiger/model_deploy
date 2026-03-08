# Qwen3-TTS Service Startup Guide

This guide shows how to start the OpenAI-compatible TTS service defined in `Qwen3-TTS/api.py` and verify it works end to end with MinIO upload.

## Prerequisites
- Python environment with project dependencies installed (`pip install -e .` inside `Qwen3-TTS` or use the existing `qwen3-tts` env).
- GPU with CUDA is recommended; CPU works but will be slower.
- Access to MinIO with valid credentials.
- Model weights accessible via `TTS_MODEL_PATH` (CustomVoice) and `TTS_VOICE_DESIGN_MODEL_PATH` (VoiceDesign); each can be a local path or hub id. Examples: `/media/llm/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice/`, `/media/llm/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign/`.

## Environment Variables
Set these before launching (example values):
```bash
export TTS_MODEL_ID="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
export TTS_MODEL_PATH="/media/llm/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice/"
export TTS_VOICE_DESIGN_MODEL_ID="Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
export TTS_VOICE_DESIGN_MODEL_PATH="/media/llm/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign/"
export TTS_DEVICE="cuda:0"
export TTS_DTYPE="bfloat16"
export TTS_ATTN_IMPL="flash_attention_2"
export TTS_DEFAULT_VOICE="Vivian"
export TTS_DEFAULT_LANGUAGE="Chinese"
export TTS_OUTPUT_DIR="/tmp/qwen3-tts-outputs"
export TTS_MINIO_UPLOAD_DIR="qwen3-tts"
export MINIO_IP="120.133.137.142"
export MINIO_UPLOAD_PORT="9000"
export MINIO_ACCESS_KEY="<your-key>"
export MINIO_SECRET_KEY="<your-secret>"
export MINIO_BUCKET_NAME="files"
export PORT=6006
```

## Launch
From the repository root `/media/source/model_deploy`:
```bash
cd Qwen3-TTS
uvicorn api:app --host 0.0.0.0 --port ${PORT:-6006}
```
The first run will load the model; expect GPU memory allocation logs. Keep the terminal open.

## Quick Health Checks
```bash
curl -s http://127.0.0.1:6006/healthz
curl -s http://127.0.0.1:6006/v1/models
```

## Smoke Test (audio generation)
```bash
curl -X POST http://127.0.0.1:6006/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "input": "你好，测试一下语音合成。",
    "voice": "Vivian",
    "language": "Chinese",
    "instruct": "温柔",
    "response_format": "url",
    "stream": false
  }'
```
- Expect a JSON response containing `output.choices[0].message.content[0].audio`, which should be a MinIO download URL.
- If MinIO upload fails, check credentials, bucket, and network reachability.

### VoiceDesign smoke test
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
 - Expect the MinIO download URL in `output.choices[0].message.content[0].audio`.

## Common Issues
- **Model mismatch (400)**: Ensure the request `model` matches `TTS_MODEL_ID` (speech) or `TTS_VOICE_DESIGN_MODEL_ID` (voice_design).
- **stream not supported (400)**: Set `"stream": false`.
- **CUDA errors**: Confirm `CUDA_VISIBLE_DEVICES` includes the selected GPU; try `TTS_DTYPE=float16` or `float32` if bfloat16 unsupported.
- **MinIO upload errors**: Verify `MINIO_*` envs and that the bucket exists; the service auto-adds the MinIO host to `NO_PROXY`.

## Stopping
Press `Ctrl+C` in the uvicorn terminal.
