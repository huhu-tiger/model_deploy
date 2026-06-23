#!/usr/bin/env python3
"""
GLM-5.2 AWQ-INT4 量化脚本 —— llmcompressor 方案
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
算法: AWQ (Activation-aware Weight Quantization),带校准数据。

两种加载模式（--multi-gpu 开关控制）:

  模式 A: sequential offload（默认,单卡）
    --gpus 0
    - oneshot(model=路径字符串) + sequential_offload_device="cpu"
    - 逐层 CPU RAM → GPU → CPU,仅用 1 张卡,瓶颈在 PCIe I/O

  模式 B: device_map multi-GPU + CPU offload（--multi-gpu）
    --gpus 0,1,2,3,4,5,6,7  --multi-gpu
    - accelerate device_map="auto" 将模型分布到所有可见 GPU + CPU RAM
    - 校准前向传播同时利用所有 GPU

通用逻辑全部委托给 llmcompressor_common 公共库。

依赖（镜像 model.vnet.com/sjhl/vllm-openai:v0.23.0-llmcompressor 已内置）:
  llmcompressor==0.12.0 / datasets==5.0.0 / accelerate==1.13.0
"""

import argparse
import gc
import logging
import os
import sys
from pathlib import Path


# ── 关键步骤 1: 注入公共库到 sys.path ─────────────────────────────
_COMMON_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_COMMON_DIR))


# ── 关键步骤 2: GPU 预选（必须在 import torch 之前）──────────────
from llmcompressor_common.gpu_select import pre_select_gpus, get_gpu_info
pre_select_gpus()

# GLM-5.2 MoE 权重合并时会产生较大的临时张量,expandable_segments
# 可减少保留显存碎片导致的 OOM。必须在 import torch 前设置。
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import torch  # 必须在 pre_select_gpus 之后


# ── 公共库其余 API ────────────────────────────────────────────────
from llmcompressor_common.calib_dataset import (
    parse_dataset_specs,
    prepare_calib_dataset,
    format_specs_summary,
)
from llmcompressor_common.recipe import build_awq_recipe, MODEL_IGNORE_PRESETS
from llmcompressor_common.memory import resolve_cpu_memory_str
from llmcompressor_common.resource_check import check_resources
from llmcompressor_common.logging_utils import setup_logging


_SEP = "═" * 66


# ══════════════════════════════════════════════════════════════════
# GLM-5.2 特定: transformers 兼容补丁
# ══════════════════════════════════════════════════════════════════

def _patch_loading_report() -> bool:
    """
    transformers 5.10.1 兼容性补丁:
    `log_state_dict_report` 对 CONVERSION 状态抛 RuntimeError,
    但 GLM-5.2（GlmMoeDsaForCausalLM）的 DSA indexer 权重是按设计
    新初始化的（非真正错误）。补丁将 CONVERSION RuntimeError 降级为 WARNING,
    真正的加载失败（error_msg）仍会正常抛出。
    """
    try:
        from transformers.utils import loading_report as _lr
        _orig = _lr.log_state_dict_report

        def _patched(model, pretrained_model_name_or_path,
                     ignore_mismatched_sizes, loading_info, logger=None):
            try:
                return _orig(model, pretrained_model_name_or_path,
                             ignore_mismatched_sizes, loading_info, logger)
            except RuntimeError as exc:
                msg = str(exc)
                if "CONVERSION" in msg:
                    logging.getLogger(__name__).warning(
                        "[GLM-5.2 兼容补丁] 权重 CONVERSION 检测到但已忽略"
                        "（DSA indexer 新初始化为预期行为）: %s", msg
                    )
                else:
                    raise

        _lr.log_state_dict_report = _patched
        print("[补丁] transformers loading_report CONVERSION 检查已降级为 WARNING", flush=True)
        return True
    except Exception as e:
        print(f"[警告] loading_report 补丁应用失败,继续加载: {e}", flush=True)
        return False


# ══════════════════════════════════════════════════════════════════
# 模型加载（模式 B 专用）
# ══════════════════════════════════════════════════════════════════

def load_model_multi_gpu(model_path, gpu_count, total_vram_gib,
                         cpu_memory_str, gpu_memory_utilization):
    """
    accelerate device_map="auto" 多卡加载:
      - 每张 GPU 预留指定显存比例（避免量化过程 OOM）
      - 剩余层 offload 到 CPU RAM
    """
    from transformers import AutoModelForCausalLM

    _patch_loading_report()

    # GLM-5.2 MoE gate_up_proj 在 _finalize_model_loading 时需要合并 2 个分片
    # （MergeModulelist）,每层临时峰值约 12 GiB;保留 70% 使每卡留 ~24 GiB 余量。
    reserved_gib = total_vram_gib * gpu_memory_utilization
    per_gpu_gib = reserved_gib / gpu_count
    max_memory = {i: f"{per_gpu_gib:.0f}GiB" for i in range(gpu_count)}
    max_memory["cpu"] = cpu_memory_str

    print(f"\n[1/3] 用 device_map='auto' 加载模型（多卡模式）")
    print(
        f"  GPU 分配 : {gpu_count} × {per_gpu_gib:.0f} GiB = {reserved_gib:.0f} GiB"
        f"  ({gpu_memory_utilization:.0%},留余量给 MoE 收尾)"
    )
    print(f"  CPU 分配 : {cpu_memory_str}")
    print(f"  PYTORCH_CUDA_ALLOC_CONF: {os.environ.get('PYTORCH_CUDA_ALLOC_CONF')}")
    print(f"  max_memory: {max_memory}")

    try:
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            device_map="auto",
            max_memory=max_memory,
            dtype=torch.bfloat16,
            trust_remote_code=True,
        )
    except torch.OutOfMemoryError as e:
        raise RuntimeError(
            "模式 B 多卡加载阶段 CUDA OOM。建议将 --gpu-memory-utilization "
            "降到 0.60 或 0.55 后重试;若仍失败,请使用模式 A sequential offload。"
        ) from e

    device_counts = {}
    for _, param in model.named_parameters():
        d = str(param.device)
        device_counts[d] = device_counts.get(d, 0) + 1
    print("  层分布（参数张量数量）:")
    for dev, cnt in sorted(device_counts.items()):
        print(f"    {dev}: {cnt} 个")
    if device_counts.get("meta", 0) > 0:
        raise RuntimeError(
            f"模型加载后仍有 {device_counts['meta']} 个 meta 参数。"
            "这通常表示 transformers 多卡转换/合并未完整 materialize 权重,"
            "继续 AWQ 会在前向阶段失败。请降低 --gpu-memory-utilization 后重试,"
            "或使用模式 A sequential offload。"
        )

    return model


# ══════════════════════════════════════════════════════════════════
# 模式 A / B 量化执行
# ══════════════════════════════════════════════════════════════════

def run_mode_a(args, tokenizer, recipe, dataset, total_samples, dataset_specs):
    """模式 A: 单卡 sequential offload。"""
    print(f"\n[模式 A] 单卡 sequential offload")
    print(f"  offload  : {args.offload_device}")
    print(f"  scheme   : {args.scheme}")
    print(f"  校准数据 : {format_specs_summary(dataset_specs)}（max_seq={args.max_seq_length}）")
    print(f"  预计耗时 : ~4~12 小时（逐层 PCIe 传输,瓶颈在 I/O）")

    from llmcompressor import oneshot

    offload = args.offload_device if args.offload_device != "none" else None

    oneshot(
        model=args.model_path,             # 字符串路径,内部按序加载各层
        tokenizer=tokenizer,
        recipe=recipe,
        dataset=dataset,
        num_calibration_samples=total_samples,
        max_seq_length=args.max_seq_length,
        trust_remote_code_model=True,
        sequential_offload_device=offload,
        moe_calibrate_all_experts=True,
        output_dir=args.output_path,
        save_compressed=True,
    )


def run_mode_b(args, gpu_count, total_vram_gib, tokenizer, recipe,
               dataset, total_samples, dataset_specs):
    """模式 B: 多卡 device_map + CPU offload。"""
    print(f"\n[模式 B] 多卡 device_map + CPU offload")
    print(f"  scheme   : {args.scheme}")
    print(f"  校准数据 : {format_specs_summary(dataset_specs)}（max_seq={args.max_seq_length}）")
    print(f"  预计耗时 : ~2~6 小时（{gpu_count} 卡并行校准）")

    from llmcompressor import oneshot

    model = load_model_multi_gpu(
        args.model_path, gpu_count, total_vram_gib, args.cpu_memory,
        args.gpu_memory_utilization,
    )

    print(f"\n[2/3] 开始 AWQ 量化（pipeline=independent,多卡前向）...")
    oneshot(
        model=model,                       # 已加载的模型对象
        tokenizer=tokenizer,
        recipe=recipe,
        dataset=dataset,
        num_calibration_samples=total_samples,
        max_seq_length=args.max_seq_length,
        pipeline="independent",
        moe_calibrate_all_experts=True,
        output_dir=args.output_path,
        save_compressed=True,
    )
    print(f"[3/3] 量化完成,结果已保存至 {args.output_path}")


# ══════════════════════════════════════════════════════════════════
# 参数解析 & 主入口
# ══════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="GLM-5.2 AWQ-INT4 量化（llmcompressor,单卡或多卡）"
    )
    parser.add_argument("--model-path", default="/media/llm/ZhipuAI/GLM-5.2")
    parser.add_argument(
        "--output-path", default="/media/llm/ZhipuAI/GLM-5.2-AWQ-4bit-LC",
    )
    parser.add_argument(
        "--gpus", type=str, default=None,
        help="GPU 卡号（逗号分隔）,如 '2' 或 '0,1,2,3,4,5'",
    )
    parser.add_argument(
        "--multi-gpu", action="store_true",
        help="启用多卡模式: device_map='auto' 将模型分布到所有可见 GPU + CPU RAM",
    )
    parser.add_argument(
        "--cpu-memory", type=str, default="auto",
        help="多卡模式 CPU offload 容量。auto=可用内存×80%%,或固定值如 '1100GiB'",
    )
    parser.add_argument(
        "--gpu-memory-utilization", type=float, default=0.70,
        help="多卡模式每卡显存利用率（建议 0.30~0.90）",
    )
    parser.add_argument(
        "--calib-dataset", type=str,
        default="cyankiwi/calibration,HuggingFaceH4/ultrachat_200k",
        help=(
            "校准数据集,支持单集或逗号分隔多集混合:\n"
            "  单集: cyankiwi/calibration（或短名 'cyankiwi'）\n"
            "  多集: cyankiwi/calibration,HuggingFaceH4/ultrachat_200k\n"
            "默认混合: cyankiwi(中英) + ultrachat_200k(英文对话)"
        ),
    )
    parser.add_argument(
        "--calib-samples", type=str, default="256,256",
        help=(
            "样本数,支持:\n"
            "  总数（平均分配）: 512\n"
            "  逐集指定（与 --calib-dataset 一一对应）: 256,256"
        ),
    )
    parser.add_argument("--max-seq-length", type=int, default=2048)
    parser.add_argument(
        "--scheme", type=str, default="W4A16_ASYM",
        choices=["W4A16_ASYM", "W4A16", "W8A8_ASYM"],
    )
    parser.add_argument(
        "--offload-device", type=str, default="cpu", choices=["cpu", "none"],
    )
    parser.add_argument(
        "--skip-resource-check", action="store_true",
        help="跳过启动前资源预检（不推荐,仅用于调试）",
    )
    parser.add_argument(
        "--log-dir", type=str, default=None,
        help="日志目录。默认: 当前脚本所在目录下的 logs/",
    )
    parser.add_argument(
        "--no-fallback-to-mode-a", action="store_true",
        help="模式 B 失败时不自动回退到模式 A（默认开启回退）",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("未检测到 CUDA GPU,量化需要 GPU 环境")

    gpu_count = torch.cuda.device_count()
    phys_ids = args.gpus.split(",") if args.gpus else None
    total_vram_gib, per_gpu_vram_gib = get_gpu_info(gpu_count, phys_ids)

    # 判断实际运行模式
    use_multi_gpu = args.multi_gpu and gpu_count > 1
    if args.multi_gpu and gpu_count <= 1:
        print(f"[警告] --multi-gpu 已指定但只有 {gpu_count} 张卡,回退到单卡模式 A")
    mode = "B" if use_multi_gpu else "A"
    if use_multi_gpu and not (0.30 <= args.gpu_memory_utilization <= 0.90):
        raise ValueError("--gpu-memory-utilization 建议范围为 0.30~0.90")

    # ── 初始化日志（越早越好,从此 stdout/stderr 全部落盘）─────────
    mode_tag = f"mode_{'b' if use_multi_gpu else 'a'}"
    log_path = setup_logging(args.log_dir, mode_tag, args.model_path, caller_file=__file__)
    print(f"[日志] 模式: {mode}  日志文件: {log_path}", flush=True)

    # 解析 cpu_memory（"auto" → 可用内存 × 80%）
    if use_multi_gpu:
        args.cpu_memory = resolve_cpu_memory_str(args.cpu_memory)

    # ── 数据集规格 ────────────────────────────────────────────────
    specs = parse_dataset_specs(args.calib_dataset, args.calib_samples)
    print(f"\n[数据集配方]")
    for ds_id, n in specs:
        print(f"  {ds_id!r}  {n} 条")
    print(f"  合计 {sum(n for _, n in specs)} 条,max_seq_length={args.max_seq_length}")

    # ── 资源预检 ──────────────────────────────────────────────────
    if not args.skip_resource_check:
        ok = check_resources(
            mode=mode,
            model_path=args.model_path,
            output_path=args.output_path,
            gpu_count=gpu_count,
            total_vram_gib=total_vram_gib,
            per_gpu_vram_gib=per_gpu_vram_gib,
            cpu_memory_str=args.cpu_memory,
            gpu_memory_utilization=args.gpu_memory_utilization,
            default_layers=78,
        )
        if not ok:
            sys.exit(1)
    else:
        print("[警告] 已跳过资源预检（--skip-resource-check）")

    os.makedirs(args.output_path, exist_ok=True)

    # ── 加载 Tokenizer + 构造 recipe ──────────────────────────────
    from transformers import AutoTokenizer

    print(f"\n加载 Tokenizer ...")
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_path, trust_remote_code=True,
    )

    recipe = build_awq_recipe(
        ignore=MODEL_IGNORE_PRESETS["glm_moe_dsa"],
        scheme=args.scheme,
        duo_scaling="both",
    )

    # ── 一站式校准集准备: 预下载 → 取消代理 → 加载混合 ─────────────
    # print_summary=False:具体配方已在前文打印,避免重复
    dataset, total_samples = prepare_calib_dataset(
        specs, tokenizer,
        skip_prefetch=False,
        unset_proxy_after_prefetch=True,
        print_summary=False,
    )

    # ── 执行量化 ──────────────────────────────────────────────────
    completed_mode = mode
    fallback_to_mode_a = False
    fallback_reason = ""
    if use_multi_gpu:
        fallback_status = "开启" if not args.no_fallback_to_mode_a else "关闭"
        print(f"\n{_SEP}")
        print("  执行计划")
        print(_SEP)
        print("  首选模式 : B（多卡 device_map + CPU offload）")
        print(f"  回退策略 : {fallback_status}（模式 B 失败时切换到模式 A）")
        print(f"  输出目录 : {args.output_path}")
        print(_SEP)
    else:
        print(f"\n{_SEP}")
        print("  执行计划")
        print(_SEP)
        print("  运行模式 : A（单卡 sequential offload）")
        print(f"  输出目录 : {args.output_path}")
        print(_SEP)

    if use_multi_gpu:
        try:
            run_mode_b(args, gpu_count, total_vram_gib, tokenizer, recipe,
                       dataset, total_samples, specs)
        except Exception as e:
            fallback_reason = f"{type(e).__name__}: {e}"
            if args.no_fallback_to_mode_a:
                print(f"\n{_SEP}")
                print("  模式切换")
                print(_SEP)
                print("  模式 B 失败,且 --no-fallback-to-mode-a 已启用")
                print(f"  原因   : {fallback_reason}")
                print(_SEP)
                raise
            logging.exception("模式 B 失败,准备自动切换到模式 A")
            print(f"\n{_SEP}")
            print("  模式切换")
            print(_SEP)
            print("  源模式 : B（多卡 device_map + CPU offload）")
            print("  目标模式: A（单卡 sequential offload）")
            print(f"  原因   : {fallback_reason}")
            print(f"  输出目录: {args.output_path}")
            print(_SEP, flush=True)
            fallback_to_mode_a = True

        if fallback_to_mode_a:
            print("\n[回退清理] 释放模式 B 残留资源 ...", flush=True)
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
                print("  GPU 缓存已清理,开始模式 A", flush=True)
            completed_mode = "A"
            run_mode_a(args, tokenizer, recipe, dataset, total_samples, specs)
    else:
        run_mode_a(args, tokenizer, recipe, dataset, total_samples, specs)

    print(f"\n✅ AWQ 量化完成!")
    print(f"   实际完成模式: {completed_mode}")
    print(f"   输出目录: {args.output_path}")
    print(f"   vllm serve {args.output_path} --quantization awq_marlin --tensor-parallel-size 8")


if __name__ == "__main__":
    main()
