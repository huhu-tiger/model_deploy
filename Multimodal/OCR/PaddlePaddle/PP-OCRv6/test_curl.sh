#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-9410}"
BASE_URL="http://localhost:${PORT}"
DEMO_IMAGE="https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/general_ocr_002.png"

echo "==> Health: ${BASE_URL}/health"
curl -fsS "${BASE_URL}/health"
echo ""

echo "==> OCR: ${BASE_URL}/ocr"
curl -fsS -X POST "${BASE_URL}/ocr" \
  -H "Content-Type: application/json" \
  -d "{\"file\": \"${DEMO_IMAGE}\", \"visualize\": false, \"useDocOrientationClassify\": false, \"useDocUnwarping\": false, \"useTextlineOrientation\": false}" \
  | python3 -m json.tool

echo ""
echo "测试完成"
