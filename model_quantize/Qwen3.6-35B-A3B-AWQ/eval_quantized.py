#!/usr/bin/env python3
"""
量化模型质量评测脚本
功能：
  1. 困惑度（Perplexity）评测 —— 衡量量化精度损失
  2. 快速问答对比     —— 直观感受量化前后输出差异
  3. 支持对比 BF16 原始模型与量化模型

评测数据集（--dataset 可选值）:
  wikitext       WikiText-2（英文通用，学术标准）
  c4             C4 英文语料（大规模通用）
  ceval          C-Eval 中文考试题（中文理解能力）
  cmmlu          CMMLU 中文多科知识（中文知识密度高）
  belle          BELLE 中文指令（中文对话/指令）
  custom         自定义文本文件（--custom-file 指定路径）

用法:
  # 仅评测量化模型困惑度
  python eval_quantized.py --quant-path /media/llm/Qwen/Qwen3.6-35B-A3B-AWQ-4bit --gpus 0,1

  # 对比量化模型 vs 原始 BF16
  python eval_quantized.py \\
      --quant-path /media/llm/Qwen/Qwen3.6-35B-A3B-AWQ-4bit \\
      --orig-path  /media/llm/Qwen/Qwen3.6-35B-A3B \\
      --dataset ceval --gpus 0,1,2,3

  # 多数据集联合评测
  python eval_quantized.py \\
      --quant-path /media/llm/Qwen/Qwen3.6-35B-A3B-AWQ-4bit \\
      --dataset wikitext,ceval,belle --gpus 0,1,2,3
"""

import argparse
import os
import sys
import json
import math
import time
from pathlib import Path


# ── GPU 预选（必须在 import torch 之前）────────────────────────────
def _pre_select_gpus():
    for i, arg in enumerate(sys.argv):
        if arg in ("--gpus", "-gpus") and i + 1 < len(sys.argv):
            gpus = sys.argv[i + 1]
            os.environ["CUDA_VISIBLE_DEVICES"] = gpus
            print(f"[GPU 预选] CUDA_VISIBLE_DEVICES={gpus}", flush=True)
            return
    if "CUDA_VISIBLE_DEVICES" in os.environ:
        print(f"[GPU 预选] 沿用环境变量 CUDA_VISIBLE_DEVICES={os.environ['CUDA_VISIBLE_DEVICES']}", flush=True)

_pre_select_gpus()
# ──────────────────────────────────────────────────────────────────

import torch
import numpy as np
from tqdm import tqdm


# ══════════════════════════════════════════════════════════════════
#  数据集加载
# ══════════════════════════════════════════════════════════════════

DATASET_REGISTRY = {
    "wikitext": {
        "desc": "WikiText-2（英文通用，学术标准）",
        "hf_id": "wikitext",
        "hf_config": "wikitext-2-raw-v1",
        "split": "test",
        "text_field": "text",
        "lang": "en",
    },
    "c4": {
        "desc": "C4（英文大规模通用）",
        "hf_id": "allenai/c4",
        "hf_config": "en",
        "split": "validation",
        "text_field": "text",
        "lang": "en",
    },
    "ceval": {
        "desc": "C-Eval（中文考试题，五选一）",
        "hf_id": "ceval/ceval-exam",
        "hf_config": "all",
        "split": "val",
        "text_field": None,
        "lang": "zh",
        "is_qa": True,
    },
    "cmmlu": {
        "desc": "CMMLU（中文多科知识问答）",
        "hf_id": "haonan-li/cmmlu",
        "hf_config": "all",
        "split": "test",
        "text_field": None,
        "lang": "zh",
        "is_qa": True,
    },
    "belle": {
        "desc": "BELLE（中文指令对话）",
        "hf_id": "BelleGroup/train_2M_CN",
        "hf_config": None,
        "split": "train",
        "text_field": "instruction",
        "lang": "zh",
    },
    "custom": {
        "desc": "自定义文本文件（--custom-file 指定路径）",
        "hf_id": None,
        "lang": "custom",
    },
}

# 内置多语言评测文本（网络不通时的降级方案）
BUILTIN_EVAL_TEXTS = {
    "en": [
        "The quick brown fox jumps over the lazy dog. This sentence contains every letter of the English alphabet at least once.",
        "Artificial intelligence and machine learning are transforming industries ranging from healthcare to finance, enabling new capabilities that were previously impossible.",
        "The attention mechanism in transformer models allows each token to attend to all other tokens in the sequence, capturing long-range dependencies effectively.",
        "Quantization reduces the precision of neural network weights from 32-bit or 16-bit floating point to lower bit representations such as 8-bit or 4-bit integers.",
        "Large language models are pre-trained on massive datasets containing trillions of tokens, enabling them to learn rich representations of human language.",
        "The mixture of experts architecture allows different subsets of model parameters to be activated for different inputs, improving efficiency and scalability.",
        "Post-training quantization is a technique that quantizes a model after it has been fully trained, without requiring any modifications to the training process.",
        "Chain-of-thought prompting encourages language models to generate intermediate reasoning steps before producing a final answer to complex questions.",
        "Retrieval-augmented generation combines parametric and non-parametric knowledge by retrieving relevant documents and conditioning generation on them.",
        "The Qwen series of large language models has been developed by Alibaba Cloud and demonstrates strong multilingual performance across diverse benchmarks.",
    ],
    "zh": [
        "大型语言模型通过在海量文本数据上进行预训练，获得了强大的自然语言理解和生成能力，能够执行翻译、摘要、问答、代码生成等多种任务。",
        "混合专家架构通过稀疏激活机制，每次推理只激活少数专家网络，实现了参数规模与计算量的解耦，大幅提升了模型的扩展效率和推理速度。",
        "量化技术将模型权重从高精度浮点数压缩为低比特整数表示，在几乎不损失精度的前提下显著降低了模型的存储需求和推理延迟。",
        "AWQ（激活感知权化量化）通过分析激活值的统计特性来保护对精度最敏感的权重，相比传统均匀量化方法具有更小的精度损失。",
        "检索增强生成技术将外部知识库与大语言模型的参数化知识相结合，有效缓解了模型幻觉问题并提高了答案的时效性。",
        "注意力机制是 Transformer 架构的核心组件，通过计算查询向量与键向量的点积相似度，使模型能够动态关注序列中最相关的位置。",
        "思维链提示技术引导模型在给出最终答案之前先展示逐步推理过程，显著提升了大语言模型在复杂数学和逻辑推理任务上的准确率。",
        "知识蒸馏技术通过让小型学生模型模仿大型教师模型的软标签输出，在保持较小模型规模的同时传递了教师模型的泛化知识。",
        "强化学习从人类反馈（RLHF）技术通过收集人类对模型输出的偏好数据，训练奖励模型来引导语言模型生成更符合人类价值观的内容。",
        "视觉语言模型将图像编码器与文本解码器相结合，通过多模态对齐训练使模型能够理解图像内容并生成相关描述或回答关于图像的问题。",
    ],
}


def load_eval_dataset(dataset_name: str, tokenizer, max_samples: int, seq_len: int,
                      custom_file: str = None):
    """加载评测数据集，返回 token 列表（用于 PPL 计算）和 QA 样本列表。"""
    from datasets import load_dataset

    cfg = DATASET_REGISTRY.get(dataset_name)
    if cfg is None:
        raise ValueError(f"未知数据集: {dataset_name}。可选: {list(DATASET_REGISTRY.keys())}")

    print(f"  [{dataset_name}] {cfg['desc']}")

    # 自定义文件
    if dataset_name == "custom":
        if not custom_file or not Path(custom_file).exists():
            raise FileNotFoundError(f"--custom-file 路径不存在: {custom_file}")
        texts = Path(custom_file).read_text(encoding="utf-8").split("\n\n")
        texts = [t.strip() for t in texts if len(t.strip()) > 50]
        return _texts_to_token_chunks(texts[:max_samples], tokenizer, seq_len), []

    # QA 格式（C-Eval / CMMLU）→ 直接做问答评测，不计算 PPL
    if cfg.get("is_qa"):
        try:
            if cfg.get("hf_config"):
                ds = load_dataset(cfg["hf_id"], cfg["hf_config"],
                                  split=cfg["split"], trust_remote_code=True)
            else:
                ds = load_dataset(cfg["hf_id"], split=cfg["split"], trust_remote_code=True)
            return [], list(ds.select(range(min(max_samples, len(ds)))))
        except Exception as e:
            print(f"    [警告] 数据集加载失败 ({e})，跳过该数据集")
            return [], []

    # 纯文本格式 → 计算 PPL
    try:
        load_kwargs = {"split": cfg["split"], "trust_remote_code": True}
        if cfg.get("hf_config"):
            ds = load_dataset(cfg["hf_id"], cfg["hf_config"], **load_kwargs)
        else:
            ds = load_dataset(cfg["hf_id"], **load_kwargs)

        field = cfg["text_field"]
        texts = [item[field] for item in ds if item.get(field, "").strip()]
        texts = texts[:max_samples * 3]
    except Exception as e:
        print(f"    [警告] 在线数据集加载失败 ({e})，使用内置降级文本")
        lang = cfg.get("lang", "zh")
        texts = BUILTIN_EVAL_TEXTS.get(lang, BUILTIN_EVAL_TEXTS["zh"]) * 10

    chunks = _texts_to_token_chunks(texts, tokenizer, seq_len)
    return chunks[:max_samples], []


def _texts_to_token_chunks(texts, tokenizer, seq_len: int):
    """将文本列表 tokenize 并切分为固定长度的 chunk。"""
    all_ids = []
    for text in texts:
        if not text.strip():
            continue
        ids = tokenizer.encode(text, add_special_tokens=False)
        all_ids.extend(ids)
    chunks = []
    for i in range(0, len(all_ids) - seq_len, seq_len):
        chunks.append(all_ids[i: i + seq_len])
    return chunks


# ══════════════════════════════════════════════════════════════════
#  困惑度（Perplexity）计算
# ══════════════════════════════════════════════════════════════════

@torch.no_grad()
def compute_perplexity(model, tokenizer, token_chunks: list, batch_size: int = 1,
                       desc: str = "PPL") -> float:
    """在给定 token chunks 上计算困惑度。"""
    if not token_chunks:
        return float("nan")

    model.eval()
    device = next(model.parameters()).device
    total_nll = 0.0
    total_tokens = 0

    for i in tqdm(range(0, len(token_chunks), batch_size), desc=desc, ncols=80):
        batch = token_chunks[i: i + batch_size]
        input_ids = torch.tensor(batch, dtype=torch.long, device=device)
        labels = input_ids.clone()

        outputs = model(input_ids=input_ids, labels=labels)
        nll = outputs.loss.item()

        n_tokens = input_ids.numel()
        total_nll += nll * n_tokens
        total_tokens += n_tokens

    ppl = math.exp(total_nll / total_tokens)
    return ppl


# ══════════════════════════════════════════════════════════════════
#  多选题（C-Eval / CMMLU）准确率评测
# ══════════════════════════════════════════════════════════════════

CHOICE_LABELS = ["A", "B", "C", "D"]

def _format_ceval_prompt(item: dict) -> tuple[str, str]:
    """将 C-Eval 样本格式化为选择题 prompt，返回 (prompt, answer)。"""
    q = item.get("question", "")
    choices = [item.get(f"option_{c}", item.get(c, "")) for c in ["A", "B", "C", "D"]]
    answer = item.get("answer", "A")
    prompt = f"以下是单项选择题，请选出正确答案。\n\n题目：{q}\n"
    for label, choice in zip(CHOICE_LABELS, choices):
        if choice:
            prompt += f"{label}. {choice}\n"
    prompt += "\n答案是："
    return prompt, str(answer).strip().upper()


@torch.no_grad()
def compute_mcq_accuracy(model, tokenizer, qa_samples: list, dataset_name: str,
                          desc: str = "MCQ") -> float:
    """计算多选题准确率（以下一个 token 的 log-likelihood 判断）。"""
    if not qa_samples:
        return float("nan")

    model.eval()
    device = next(model.parameters()).device
    correct = 0
    total = 0

    choice_ids = [tokenizer.encode(c, add_special_tokens=False)[0] for c in CHOICE_LABELS]

    for item in tqdm(qa_samples, desc=desc, ncols=80):
        try:
            prompt, answer = _format_ceval_prompt(item)
        except Exception:
            continue

        enc = tokenizer(prompt, return_tensors="pt").to(device)
        logits = model(**enc).logits[0, -1, :]  # 最后一个 token 的 logit
        choice_logits = torch.tensor([logits[cid].item() for cid in choice_ids])
        pred = CHOICE_LABELS[choice_logits.argmax().item()]

        if pred == answer:
            correct += 1
        total += 1

    return correct / total if total > 0 else float("nan")


# ══════════════════════════════════════════════════════════════════
#  生成质量对比
# ══════════════════════════════════════════════════════════════════

QA_PROMPTS = [
    "请简述 AWQ 量化的核心原理是什么？",
    "Qwen3.6-35B-A3B 是什么类型的模型？它的混合专家架构有什么特点？",
    "如何在 Python 中使用多线程并发请求 API？请给出代码示例。",
    "Explain the key difference between MoE and dense transformer architectures.",
    "What is perplexity in the context of language model evaluation?",
]

@torch.no_grad()
def run_generation_comparison(models_dict: dict, tokenizer, max_new_tokens: int = 200):
    """对比多个模型的生成输出。"""
    print("\n" + "═" * 70)
    print("  生成质量对比")
    print("═" * 70)

    for prompt in QA_PROMPTS:
        messages = [{"role": "user", "content": prompt}]
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        print(f"\n{'─' * 70}")
        print(f"【问】{prompt}")

        for name, model in models_dict.items():
            device = next(model.parameters()).device
            enc = tokenizer(text, return_tensors="pt").to(device)
            t0 = time.time()
            out = model.generate(
                **enc,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                temperature=None,
                top_p=None,
            )
            elapsed = time.time() - t0
            new_ids = out[0][enc["input_ids"].shape[1]:]
            response = tokenizer.decode(new_ids, skip_special_tokens=True)
            tps = len(new_ids) / elapsed

            print(f"\n  [{name}] ({tps:.1f} tok/s)")
            print(f"  {response[:500]}{'...' if len(response) > 500 else ''}")


# ══════════════════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="量化模型质量评测：困惑度 + 多选题准确率 + 生成对比"
    )
    parser.add_argument(
        "--quant-path",
        type=str,
        default="/media/llm/Qwen/Qwen3.6-35B-A3B-AWQ-4bit",
        help="量化模型路径",
    )
    parser.add_argument(
        "--orig-path",
        type=str,
        default=None,
        help="原始 BF16 模型路径（可选，用于对比）",
    )
    parser.add_argument(
        "--gpus",
        type=str,
        default=None,
        help="GPU 卡号，逗号分隔，例如 '0,1' 或 '4,5,6,7'",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="wikitext,ceval",
        help=(
            "评测数据集，逗号分隔，可选: "
            + ", ".join(f"{k}({v['desc']})" for k, v in DATASET_REGISTRY.items())
        ),
    )
    parser.add_argument(
        "--custom-file",
        type=str,
        default=None,
        help="自定义评测文本路径（--dataset custom 时使用，段落以空行分隔）",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=200,
        help="每个数据集最多取多少样本/chunk 用于评测",
    )
    parser.add_argument(
        "--seq-len",
        type=int,
        default=512,
        help="PPL 评测的序列长度",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=200,
        help="生成对比时每条回复最多生成的 token 数",
    )
    parser.add_argument(
        "--skip-ppl",
        action="store_true",
        help="跳过困惑度评测（仅做生成对比）",
    )
    parser.add_argument(
        "--skip-gen",
        action="store_true",
        help="跳过生成质量对比（仅做困惑度评测）",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="将评测结果保存为 JSON 文件（可选）",
    )
    return parser.parse_args()


def load_model(path: str, label: str):
    """加载模型（自动识别量化格式）。"""
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"\n  加载 [{label}]: {path}")
    tokenizer = AutoTokenizer.from_pretrained(path, trust_remote_code=True)

    # 判断是否为量化模型
    config_path = Path(path) / "config.json"
    is_quantized = False
    if config_path.exists():
        with open(config_path) as f:
            cfg = json.load(f)
        quant_cfg = cfg.get("quantization_config", {})
        is_quantized = bool(quant_cfg)
        if is_quantized:
            print(f"    量化格式: {quant_cfg.get('quant_type', quant_cfg.get('format', '未知'))}")

    model = AutoModelForCausalLM.from_pretrained(
        path,
        trust_remote_code=True,
        device_map="auto",
        torch_dtype=torch.bfloat16 if not is_quantized else "auto",
    )
    model.eval()
    print(f"    参数量: {sum(p.numel() for p in model.parameters()) / 1e9:.2f}B")
    return model, tokenizer


def main():
    args = parse_args()
    datasets = [d.strip() for d in args.dataset.split(",") if d.strip()]

    print("═" * 70)
    print("  Qwen3.6-35B-A3B 量化模型质量评测")
    print("═" * 70)
    print(f"  量化模型    : {args.quant_path}")
    print(f"  原始模型    : {args.orig_path or '不加载（仅评测量化版）'}")
    print(f"  评测数据集  : {', '.join(datasets)}")
    print(f"  样本上限    : {args.max_samples}  序列长度: {args.seq_len}")
    print(f"  GPU 卡号    : {args.gpus or os.environ.get('CUDA_VISIBLE_DEVICES', '全部')}")
    print("═" * 70)

    # ── 加载模型 ──────────────────────────────────────────────────
    print("\n[1] 加载模型...")
    quant_model, tokenizer = load_model(args.quant_path, "量化模型")
    models = {"量化 AWQ-4bit": quant_model}

    orig_model = None
    if args.orig_path:
        orig_model, _ = load_model(args.orig_path, "原始 BF16")
        models["原始 BF16"] = orig_model

    # ── 加载评测数据集 ────────────────────────────────────────────
    print(f"\n[2] 加载评测数据集...")
    dataset_chunks = {}   # dataset_name -> (token_chunks, qa_samples)
    for ds_name in datasets:
        chunks, qa = load_eval_dataset(
            ds_name, tokenizer, args.max_samples, args.seq_len, args.custom_file
        )
        dataset_chunks[ds_name] = (chunks, qa)

    # ── 困惑度评测 ────────────────────────────────────────────────
    results = {}
    if not args.skip_ppl:
        print(f"\n[3] 困惑度（PPL）评测...")
        for ds_name, (chunks, qa) in dataset_chunks.items():
            if not chunks:
                print(f"  [{ds_name}] 无可用 PPL 样本，跳过")
                continue
            print(f"\n  数据集: {ds_name}（{len(chunks)} chunks，每段 {args.seq_len} tokens）")
            results.setdefault(ds_name, {})
            for model_name, model in models.items():
                ppl = compute_perplexity(
                    model, tokenizer, chunks,
                    desc=f"  {model_name[:12]:12s}"
                )
                results[ds_name][f"ppl_{model_name}"] = round(ppl, 4)
                print(f"    {model_name:20s}  PPL = {ppl:.4f}")

            # 计算精度保留率
            if orig_model is not None and "量化 AWQ-4bit" in models and "原始 BF16" in models:
                quant_ppl = results[ds_name].get("ppl_量化 AWQ-4bit", float("nan"))
                orig_ppl  = results[ds_name].get("ppl_原始 BF16",  float("nan"))
                if not math.isnan(quant_ppl) and not math.isnan(orig_ppl) and orig_ppl > 0:
                    degradation = (quant_ppl - orig_ppl) / orig_ppl * 100
                    results[ds_name]["ppl_degradation_%"] = round(degradation, 2)
                    print(f"    PPL 退化率: {degradation:+.2f}%  {'✅ 良好' if degradation < 5 else '⚠️ 偏高'}")

        # ── 多选题准确率 ──────────────────────────────────────────
        for ds_name, (chunks, qa) in dataset_chunks.items():
            if not qa:
                continue
            print(f"\n  数据集: {ds_name}（{len(qa)} 道选择题）")
            results.setdefault(ds_name, {})
            for model_name, model in models.items():
                acc = compute_mcq_accuracy(model, tokenizer, qa, ds_name,
                                           desc=f"  {model_name[:12]:12s}")
                results[ds_name][f"acc_{model_name}"] = round(acc, 4)
                print(f"    {model_name:20s}  Acc = {acc:.2%}")

    # ── 生成质量对比 ──────────────────────────────────────────────
    if not args.skip_gen:
        print(f"\n[4] 生成质量对比...")
        run_generation_comparison(models, tokenizer, args.max_new_tokens)

    # ── 汇总输出 ──────────────────────────────────────────────────
    print("\n" + "═" * 70)
    print("  评测结果汇总")
    print("═" * 70)
    for ds_name, metrics in results.items():
        print(f"\n  [{ds_name}]")
        for k, v in metrics.items():
            unit = "%" if "acc" in k else ("%" if "degradation" in k else "")
            val_str = f"{v:.2%}" if "acc" in k else str(v)
            print(f"    {k:35s}: {val_str}")

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        summary = {
            "quant_path": args.quant_path,
            "orig_path": args.orig_path,
            "datasets": datasets,
            "max_samples": args.max_samples,
            "seq_len": args.seq_len,
            "results": results,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"\n  评测结果已保存: {out_path}")

    print("\n✅ 评测完成！")


if __name__ == "__main__":
    main()
