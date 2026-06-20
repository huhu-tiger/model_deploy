#!/usr/bin/env python3
"""
GLM-5.2 AWQ-INT4 量化脚本 —— llmcompressor 方案
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
算法：AWQ（Activation-aware Weight Quantization），带校准数据，精度优于 RTN。

两种加载模式（--multi-gpu 开关控制）：

  模式 A：sequential offload（默认，单卡）
    --gpus 0
    - oneshot(model=路径字符串) + sequential_offload_device="cpu"
    - 逐层 CPU RAM → GPU → CPU，仅用 1 张卡，瓶颈在 PCIe I/O
    - 适合：只有 1 张卡，或 GPU 总显存 << 模型大小

  模式 B：device_map multi-GPU + CPU offload（--multi-gpu）
    --gpus 0,1,2,3,4,5,6,7  --multi-gpu
    - accelerate device_map="auto" 将模型分布到所有可见 GPU + CPU RAM
    - 8 × H100 80GB = 640 GB 常驻 GPU，剩余 ~860 GB offload 到 CPU
    - 校准前向传播同时利用所有 GPU，减少 PCIe 传输次数
    - 理论加速 30~50%（相比模式 A）

依赖：
  镜像 model.vnet.com/sjhl/vllm-openai:v0.23.0-llmcompressor 已内置

用法：
  # 模式 A（单卡）
  python3 quantize_llmcompressor.py --gpus 0

  # 模式 B（8 卡）
  python3 quantize_llmcompressor.py --gpus 0,1,2,3,4,5,6,7 --multi-gpu --cpu-memory 860GiB
"""

import argparse
import os
import sys

# ── GPU 预选（import torch 之前）──────────────────────────────────
def _pre_select_gpus():
    for i, arg in enumerate(sys.argv):
        if arg in ("--gpus", "-gpus") and i + 1 < len(sys.argv):
            gpus = sys.argv[i + 1]
            os.environ["CUDA_VISIBLE_DEVICES"] = gpus
            print(f"[GPU 预选] CUDA_VISIBLE_DEVICES={gpus}", flush=True)
            return
    if "CUDA_VISIBLE_DEVICES" in os.environ:
        print(f"[GPU 预选] 沿用 CUDA_VISIBLE_DEVICES={os.environ['CUDA_VISIBLE_DEVICES']}", flush=True)
    else:
        print("[GPU 预选] 未指定 --gpus，将使用所有可用 GPU", flush=True)

_pre_select_gpus()
# ──────────────────────────────────────────────────────────────────

import torch


def parse_args():
    parser = argparse.ArgumentParser(
        description="GLM-5.2 AWQ-INT4 量化（llmcompressor，支持单卡 sequential offload 或多卡 device_map）"
    )
    parser.add_argument("--model-path",  default="/media/llm/ZhipuAI/GLM-5.2")
    parser.add_argument("--output-path", default="/media/llm/ZhipuAI/GLM-5.2-AWQ-4bit-LC")
    parser.add_argument(
        "--gpus", type=str, default=None,
        help="GPU 卡号（逗号分隔），如 '2' 或 '0,1,2,3,4,5'",
    )
    parser.add_argument(
        "--multi-gpu", action="store_true",
        help=(
            "启用多卡模式：用 accelerate device_map='auto' 将模型分布到所有可见 GPU + CPU RAM，"
            "校准前向传播可利用所有 GPU（需 GPU 数量 × 显存 + CPU RAM 足够容纳模型）"
        ),
    )
    parser.add_argument(
        "--cpu-memory", type=str, default="800GiB",
        help="多卡模式下分配给 CPU RAM 的 offload 容量（默认 800GiB）",
    )
    parser.add_argument(
        "--calib-dataset", type=str, default="cyankiwi/calibration",
        help=(
            "校准数据集（HuggingFace dataset ID）:\n"
            "  cyankiwi/calibration（16MB，推荐）\n"
            "  wikitext-2-raw-v1"
        ),
    )
    parser.add_argument("--calib-samples",  type=int, default=384,
                        help="校准样本数（cyankiwi/calibration 全量 384）")
    parser.add_argument("--max-seq-length", type=int, default=2048)
    parser.add_argument(
        "--scheme", type=str, default="W4A16_ASYM",
        choices=["W4A16_ASYM", "W4A16", "W8A8_ASYM"],
    )
    parser.add_argument(
        "--offload-device", type=str, default="cpu",
        choices=["cpu", "none"],
        help="单卡模式下 sequential offload 目标设备",
    )
    return parser.parse_args()


def print_gpu_info(gpu_count, phys_ids):
    print(f"\n[GPU] 实际可用 {gpu_count} 张 GPU:")
    total_vram = 0
    for i in range(gpu_count):
        name = torch.cuda.get_device_name(i)
        mem  = torch.cuda.get_device_properties(i).total_memory / 1024**3
        total_vram += mem
        phys = f" (物理卡 {phys_ids[i]})" if phys_ids and i < len(phys_ids) else ""
        print(f"  GPU {i}{phys}: {name}  显存: {mem:.1f} GB")
    print(f"  合计显存: {total_vram:.0f} GB")
    return total_vram


def load_model_multi_gpu(model_path, gpu_count, total_vram_gb, cpu_memory_str):
    """
    accelerate device_map="auto" 多卡加载：
      - 每张 GPU 预留 85% 显存（避免 OOM）
      - 剩余层 offload 到 CPU RAM
    """
    from transformers import AutoModelForCausalLM

    max_memory = {}
    reserved_gb = total_vram_gb * 0.85
    per_gpu_gb  = reserved_gb / gpu_count
    for i in range(gpu_count):
        max_memory[i] = f"{per_gpu_gb:.0f}GiB"
    max_memory["cpu"] = cpu_memory_str

    print(f"\n[1/3] 用 device_map='auto' 加载模型（多卡模式）")
    print(f"  GPU 分配: {gpu_count} × {per_gpu_gb:.0f} GiB = {reserved_gb:.0f} GiB")
    print(f"  CPU 分配: {cpu_memory_str}")
    print(f"  max_memory: {max_memory}")

    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        device_map="auto",
        max_memory=max_memory,
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
    )

    # 打印实际设备分布
    device_counts = {}
    for name, param in model.named_parameters():
        d = str(param.device)
        device_counts[d] = device_counts.get(d, 0) + 1
    print("  层分布（参数数量）:")
    for dev, cnt in sorted(device_counts.items()):
        print(f"    {dev}: {cnt} 个参数张量")

    return model


def main():
    args = parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("未检测到 CUDA GPU，量化需要 GPU 环境")

    gpu_count = torch.cuda.device_count()
    phys_ids  = args.gpus.split(",") if args.gpus else None
    total_vram = print_gpu_info(gpu_count, phys_ids)

    os.makedirs(args.output_path, exist_ok=True)

    from transformers import AutoTokenizer
    from llmcompressor import oneshot
    from llmcompressor.modifiers.transform.awq import AWQModifier
    from llmcompressor.modifiers.quantization import QuantizationModifier

    print(f"\n加载 Tokenizer ...")
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_path,
        trust_remote_code=True,
    )

    IGNORE_LIST = [
        "lm_head",
        "embed_tokens",
        "re:.*indexer.*",
        "re:.*mlp\\.gate$",
        "re:.*shared_expert.*",
        "re:.*layers\\.0\\..*",
    ]

    recipe = [
        AWQModifier(duo_scaling="both"),
        QuantizationModifier(
            ignore=IGNORE_LIST,
            scheme=args.scheme,
            targets=["Linear"],
        ),
    ]

    if args.multi_gpu and gpu_count > 1:
        # ── 模式 B：多卡 device_map + CPU offload ─────────────────────
        print(f"\n[模式 B] 多卡 device_map + CPU offload")
        model = load_model_multi_gpu(
            args.model_path, gpu_count, total_vram, args.cpu_memory
        )
        print(f"\n[2/3] 开始 AWQ 量化（pipeline=independent，多卡前向）...")
        print(f"  scheme   : {args.scheme}")
        print(f"  校准数据 : {args.calib_dataset}（{args.calib_samples} 条）")
        print(f"  预计耗时 : ~2~6 小时（8 卡并行校准，H100 NVLink 带宽优势）")

        oneshot(
            model=model,                       # 传已加载的 model 对象
            tokenizer=tokenizer,
            recipe=recipe,
            dataset=args.calib_dataset,
            num_calibration_samples=args.calib_samples,
            max_seq_length=args.max_seq_length,
            moe_calibrate_all_experts=True,
            output_dir=args.output_path,
            save_compressed=True,
        )

    else:
        # ── 模式 A：单卡 sequential offload ───────────────────────────
        if args.multi_gpu and gpu_count <= 1:
            print(f"[警告] --multi-gpu 已指定但只有 {gpu_count} 张卡，回退到单卡模式")
        print(f"\n[模式 A] 单卡 sequential offload")
        print(f"  offload  : {args.offload_device}")
        print(f"  scheme   : {args.scheme}")
        print(f"  校准数据 : {args.calib_dataset}（{args.calib_samples} 条）")
        print(f"  预计耗时 : ~4~12 小时（逐层 PCIe 传输，瓶颈在 I/O）")

        offload = args.offload_device if args.offload_device != "none" else None
        oneshot(
            model=args.model_path,             # 传字符串路径，内部顺序加载
            tokenizer=tokenizer,
            recipe=recipe,
            dataset=args.calib_dataset,
            num_calibration_samples=args.calib_samples,
            max_seq_length=args.max_seq_length,
            trust_remote_code_model=True,
            sequential_offload_device=offload,
            moe_calibrate_all_experts=True,
            output_dir=args.output_path,
            save_compressed=True,
        )

    print(f"\n✅ AWQ 量化完成！")
    print(f"   输出目录: {args.output_path}")
    print(f"   vllm serve {args.output_path} --quantization awq_marlin --tensor-parallel-size 8")


if __name__ == "__main__":
    main()
