#!/bin/bash
NO_PROXY=0.0.0.0,localhost,127.0.0.1 
no_proxy=0.0.0.0,localhost,127.0.0.1 
python3 -m sglang.launch_server --model-path /media/llm/moonshotai/Kimi-K2.6 \
    --tp-size 8 \
    --host 0.0.0.0 \
    --port 30003 \
    --mem-fraction-static 0.85 \
    --trust-remote-code \
    --reasoning-parser kimi_k2 \
    --tool-call-parser kimi_k2 \

