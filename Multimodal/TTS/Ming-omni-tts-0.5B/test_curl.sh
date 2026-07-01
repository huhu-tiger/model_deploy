#!/usr/bin/env bash
# Ming-omni-tts 基础 TTS 请求测试
set -euo pipefail

HOST="${HOST:-localhost}"
PORT="${PORT:-9132}"
MODE="${MODE:-basic}"
MODEL="${MODEL:-Ming-omni-tts-0.5B}"
TEXT="${TEXT:-你好，这是 Ming 在线语音合成测试。}"
API_URL="http://${HOST}:${PORT}/v1/audio/speech"

payload=$(cat <<EOF
{
  "model": "${MODEL}",
  "input": "${TEXT}",
  "response_format": "wav"
}
EOF
)

stream_payload=$(cat <<EOF
{
  "model": "${MODEL}",
  "input": "${TEXT}",
  "stream": true,
  "stream_format": "audio",
  "response_format": "pcm"
}
EOF
)

case "${MODE}" in
  stream)
    payload="${stream_payload}"
    OUTPUT="${OUTPUT:-ming_output.pcm}"
    ;;
  *)
    payload="${payload}"
    OUTPUT="${OUTPUT:-ming_output.wav}"
    ;;
esac

echo "POST ${API_URL}"
curl -sS -X POST "${API_URL}" \
  -H "Content-Type: application/json" \
  -d "${payload}" \
  --output "${OUTPUT}"

echo "已保存: ${OUTPUT} ($(wc -c < "${OUTPUT}") bytes)"
