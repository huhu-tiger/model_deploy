#!/usr/bin/env python3
"""
量化精度快速验证：计算困惑度（Perplexity）
用于对比 模式A（sequential）vs 模式B（multi-gpu）的量化精度

加载方式说明：
  ┌─────────────────┬──────────────┬──────────────────────────────┐
  │ 评估目标        │ 权重大小     │ 是否需要 CPU offload         │
  ├─────────────────┼──────────────┼──────────────────────────────┤
  │ AWQ-INT4 量化后 │ ~400 GB      │ 否（8×H100=640GB 完全装入）  │
  │ BF16 原始基线   │ ~1.5 TB      │ 是（640GB GPU + 860GB CPU）  │
  └─────────────────┴──────────────┴──────────────────────────────┘
  日常只需评估量化模型，BF16 基线对比可选。

用法：
  # 验证量化模型（推荐：8 卡，无需 CPU offload，加载快）
  python3 eval_ppl.py --model-path /media/llm/ZhipuAI/GLM-5.2-AWQ-4bit-LC --gpus 0,1,2,3,4,5,6,7

  # 验证量化模型（单卡，需 CPU offload）
  python3 eval_ppl.py --model-path /media/llm/ZhipuAI/GLM-5.2-AWQ-4bit-LC --gpus 0

  # 与原始 BF16 对比基线（可选，加载 1.5TB 耗时 60~90 分钟）
  python3 eval_ppl.py --model-path /media/llm/ZhipuAI/GLM-5.2 --gpus 0,1,2,3,4,5,6,7 --cpu-memory 900GiB

精度参考（wikitext-2，越低越好）：
  BF16 原始模型 : ~2.5~3.5
  AWQ 量化（好）: BF16 + 0.1~0.3
  AWQ 量化（差）: BF16 + 1.0+（说明专家覆盖不足）
"""

import argparse
import math
import os
import sys

import torch


def _pre_select_gpus():
    for i, arg in enumerate(sys.argv):
        if arg == "--gpus" and i + 1 < len(sys.argv):
            os.environ["CUDA_VISIBLE_DEVICES"] = sys.argv[i + 1]
            break

_pre_select_gpus()


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model-path", required=True)
    p.add_argument("--gpus", type=str, default=None)
    p.add_argument("--samples", type=int, default=64,
                   help="用于评估的 wikitext-2 样本数（越多越准，越慢）")
    p.add_argument("--seq-len", type=int, default=512)
    p.add_argument(
        "--cpu-memory", type=str, default=None,
        help="device_map 时 CPU offload 容量，默认自动计算（总 GPU 显存的 8 倍）",
    )
    p.add_argument(
        "--proxy", type=str, default="http://172.31.0.55:20171",
        help="下载 wikitext-2 数据集所用代理（留空则不设代理）",
    )
    return p.parse_args()


def compute_perplexity(model, tokenizer, texts, seq_len):
    """
    计算 perplexity，兼容 device_map 多卡模型。
    input_ids 放到 embed_tokens 所在设备（通常 cuda:0），
    accelerate 会自动处理跨设备的层间传输。
    """
    model.eval()

    # 找到 embed_tokens 所在设备作为输入设备
    try:
        input_device = model.model.embed_tokens.weight.device
    except AttributeError:
        input_device = next(model.parameters()).device

    total_nll, total_tokens = 0.0, 0
    with torch.no_grad():
        for text in texts:
            enc = tokenizer(
                text, return_tensors="pt",
                truncation=True, max_length=seq_len,
            )
            input_ids = enc["input_ids"].to(input_device)
            if input_ids.shape[1] < 2:
                continue
            labels = input_ids.clone()
            out = model(input_ids, labels=labels)
            nll  = out.loss.item()
            ntok = input_ids.shape[1] - 1
            total_nll    += nll * ntok
            total_tokens += ntok

    return math.exp(total_nll / total_tokens) if total_tokens > 0 else float("inf")


def main():
    args = parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("未检测到 GPU")

    gpu_count = torch.cuda.device_count()
    total_vram = sum(
        torch.cuda.get_device_properties(i).total_memory / 1024**3
        for i in range(gpu_count)
    )
    print(f"[GPU] 可用 {gpu_count} 张，合计显存 {total_vram:.0f} GB")

    from transformers import AutoTokenizer, AutoModelForCausalLM

    # ── 代理（用于下载 wikitext-2）──────────────────────────────────
    if args.proxy:
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ[k] = args.proxy
        os.environ["NO_PROXY"] = "localhost,127.0.0.1,172.31.0.0/16,model.vnet.com"
        os.environ["no_proxy"] = os.environ["NO_PROXY"]
        print(f"[代理] {args.proxy}")

    print(f"\n加载 Tokenizer: {args.model_path}")
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)

    # ── 动态 max_memory ──────────────────────────────────────────────
    per_gpu = int(torch.cuda.get_device_properties(0).total_memory * 0.85 / 1024**3)
    max_memory = {i: f"{per_gpu}GiB" for i in range(gpu_count)}
    if args.cpu_memory:
        # 明确指定 CPU 容量（BF16 基线评估时需要）
        max_memory["cpu"] = args.cpu_memory
        print(f"加载模型（device_map=auto，每卡 {per_gpu} GiB，CPU offload {args.cpu_memory}）...")
    else:
        # 不预分配 CPU 配额：量化模型 ~400 GB 完全装入 640 GB 显存，无需 offload
        # 如超出显存（如评估 BF16 原始模型），accelerate 会自动 fallback 到 CPU
        print(f"加载模型（device_map=auto，每卡 {per_gpu} GiB，CPU 按需 offload）...")

    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        device_map="auto",
        max_memory=max_memory,
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
    )
    model.eval()

    # ── 加载评估数据集 ────────────────────────────────────────────────
    from datasets import load_dataset
    print(f"\n加载 wikitext-2 评估数据（{args.samples} 条）...")
    ds = load_dataset("wikitext", "wikitext-2-raw-v1", split="test")
    texts = [t for t in ds["text"] if len(t.strip()) > 100][:args.samples]
    print(f"实际使用 {len(texts)} 条样本")

    # ── 计算 PPL ─────────────────────────────────────────────────────
    print(f"\n计算 Perplexity（seq_len={args.seq_len}）...")
    ppl = compute_perplexity(model, tokenizer, texts, args.seq_len)

    print(f"\n{'='*50}")
    print(f"模型路径  : {args.model_path}")
    print(f"Perplexity: {ppl:.4f}")
    print(f"{'='*50}")
    print(f"\n精度参考（wikitext-2）：")
    print(f"  BF16 原始    : ~2.5~3.5")
    print(f"  AWQ 量化优秀 : BF16 + 0.1~0.3")
    print(f"  AWQ 量化差   : BF16 + 1.0+（专家覆盖不足）")


if __name__ == "__main__":
    main()
