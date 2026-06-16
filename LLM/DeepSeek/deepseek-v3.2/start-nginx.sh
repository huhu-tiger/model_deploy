#!/bin/bash
NO_PROXY=0.0.0.0,localhost,127.0.0.1
no_proxy=0.0.0.0,localhost,127.0.0.1
python3 -m sglang.launch_server \
	--model-path /media/llm/DeepSeek-V3.2 \
	--tp 8 \
	--trust-remote-code \
	--port 30003 \
	--host 0.0.0.0 \
	--attention-backend nsa \
	--nsa-prefill-backend flashmla_sparse \
	--nsa-decode-backend fa3 \
	--page-size 32 \
	--kv-cache-dtype bfloat16 \
	--mem-fraction-static 0.92 \
	--max-running-requests 32 \
	--max-queued-requests 32 \
	--cuda-graph-max-bs 32 \
	--tool-call-parser deepseekv32 \
	--reasoning-parser deepseek-v3 \
	--context-length 65536 \
	--chunked-prefill-size 2048 \
	--log-requests \
	--log-requests-level 2 \
	--log-level info \
	--schedule-policy lpm
