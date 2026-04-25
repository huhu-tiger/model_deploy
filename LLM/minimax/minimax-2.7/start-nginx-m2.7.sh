#!/bin/bash
NO_PROXY=0.0.0.0,localhost,127.0.0.1 
no_proxy=0.0.0.0,localhost,127.0.0.1 
python3 -m sglang.launch_server --model-path /nvme01/MiniMax/MiniMax-M2.7 \
    --tp-size 8 \
    --ep-size 2 \
    --tool-call-parser minimax-m2 \
    --trust-remote-code \
    --host 0.0.0.0 \
    --reasoning-parser minimax \
    --port 30003 \
    --mem-fraction-static 0.85 \
    --context-length 65536
