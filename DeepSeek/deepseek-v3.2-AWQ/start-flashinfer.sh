#!/bin/bash

# 使用 FlashInfer 后端（更稳定，但可能稍慢）
python3 -m sglang.launch_server \
	--model-path /media/llm/DeepSeek-V3.2-AWQ \
	--tp 8 \
	--trust-remote-code \
	--port 30001 \
	--host 0.0.0.0 \
	--attention-backend flashinfer \
	--page-size 64 \
	--kv-cache-dtype auto \
	--mem-fraction-static 0.85 \
	--max-running-requests 64 \
	--max-queued-requests 256 \
	--cuda-graph-max-bs 128 \
	--tool-call-parser deepseekv31 \
	--reasoning-parser deepseek-v3 \
	--chunked-prefill-size 8192 \
	--context-length 32768 \
	--allow-auto-truncate \
	--log-requests \
	--log-requests-level 2 \
	--log-level info
