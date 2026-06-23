#!/usr/bin/env python3
"""
Qwen3.6-35B-A3B AWQ-4bit 量化脚本 —— llmcompressor 方案

参考:
  - cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit（校准集 + AWQ）
  - https://github.com/vllm-project/llm-compressor

特点:
  - Qwen3_5MoeForConditionalGeneration（256 专家 + 线性注意力混合）
  - W4A16_ASYM AWQ + duo_scaling="both"
  - 校准集支持单集 / 多集混合（cyankiwi + ultrachat 推荐）
  - 通用逻辑全部委托给 llmcompressor_common 公共库

依赖（镜像 model.vnet.com/sjhl/vllm-openai:v0.23.0-llmcompressor 已内置）:
  llmcompressor==0.12.0 / datasets==5.0.0 / accelerate==1.13.0

输出可被 vLLM `--quantization awq_marlin` 加载。
"""

import argparse
import os
import sys
from pathlib import Path


# ── 关键步骤 1: 注入公共库到 sys.path ─────────────────────────────
# 公共库目录在父目录下:  model_quantize/llmcompressor_common/
_COMMON_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_COMMON_DIR))


# ── 关键步骤 2: GPU 预选（必须在 import torch 之前）──────────────
from llmcompressor_common.gpu_select import pre_select_gpus, get_gpu_info
pre_select_gpus()

import torch  # 必须在 pre_select_gpus 之后


# ── 公共库其余 API ────────────────────────────────────────────────
from llmcompressor_common.calib_dataset import (
    parse_dataset_specs,
    prepare_calib_dataset,
    format_specs_summary,
)
from llmcompressor_common.recipe import build_awq_recipe, MODEL_IGNORE_PRESETS
from llmcompressor_common.logging_utils import setup_logging


def parse_args():
    parser = argparse.ArgumentParser(
        description="Qwen3.6-35B-A3B llmcompressor W4A16_ASYM AWQ 量化"
    )
    parser.add_argument(
        "--model-path", type=str,
        default="/media/llm/Qwen/Qwen3.6-35B-A3B",
        help="原始 BF16 权重目录",
    )
    parser.add_argument(
        "--output-path", type=str,
        default="/media/llm/Qwen/Qwen3.6-35B-A3B-AWQ-4bit",
        help="量化后权重保存目录",
    )
    parser.add_argument(
        "--gpus", type=str, default=None,
        help="GPU 卡号（逗号分隔）,如 '2,3,4,5'。默认沿用 CUDA_VISIBLE_DEVICES",
    )
    parser.add_argument(
        "--calib-dataset", type=str,
        default="cyankiwi/calibration,HuggingFaceH4/ultrachat_200k",
        help=(
            "校准数据集,支持单集或逗号分隔多集混合。\n"
            "  单集: 'cyankiwi/calibration' 或别名 'cyankiwi'\n"
            "  多集（默认）: 'cyankiwi/calibration,HuggingFaceH4/ultrachat_200k'\n"
            "              中英双语 + 英文对话混合（GLM-5.2 同款推荐配方）\n"
            "完整别名/选型见 llmcompressor_common.DATASET_ALIASES 或 ../docs/dataset.md"
        ),
    )
    parser.add_argument(
        "--calib-samples", type=str, default="256,256",
        help=(
            "校准样本数,支持:\n"
            "  总数（平均分配到各数据集）: '512'\n"
            "  逐集指定（与 --calib-dataset 一一对应,默认）: '256,256'\n"
            "256 专家 MoE 建议 ≥ 256 条/集,确保所有专家被激活"
        ),
    )
    parser.add_argument(
        "--max-seq-length", type=int, default=2048,
    )
    parser.add_argument(
        "--scheme", type=str, default="W4A16_ASYM",
        choices=["W4A16_ASYM", "W4A16", "W8A8_ASYM"],
    )
    parser.add_argument(
        "--skip-prefetch", action="store_true",
        help="跳过校准数据集预下载（不推荐,失败发现会推迟到模型加载后）",
    )
    parser.add_argument(
        "--multi-gpu", action="store_true",
        help=(
            "多卡模式: 用 accelerate device_map='auto' 把模型分布到所有可见 GPU,"
            "充分利用多卡算力。适用于模型可完整装入 GPU 显存的场景。\n"
            "默认 (不传)行为: oneshot 内部 sequential offload(MoE 默认 CPU offload),"
            "只用 cuda:0,适合大模型。"
        ),
    )
    parser.add_argument(
        "--log-dir", type=str, default=None,
        help="日志目录。默认: 当前脚本所在目录下的 logs/",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # ── 初始化日志（先于其他逻辑,从此 stdout/stderr 全部落盘）─────
    # 注意: pre_select_gpus / sys.path 注入在 import 阶段已执行,
    # 其打印输出不会被 Tee 捕获;但 args 解析后所有阶段（cuda 检查 /
    # GPU 信息 / 数据集准备 / 量化）都会被完整记录。
    log_path = setup_logging(
        log_dir=args.log_dir,
        mode_tag="awq",
        model_path=args.model_path,
        caller_file=__file__,
    )
    # 把 import 阶段已经发生的 GPU 预选结果再写一遍,使日志自洽
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if visible is not None:
        print(f"[日志] CUDA_VISIBLE_DEVICES={visible}（import 阶段已设置）", flush=True)
    print(f"[日志] 文件: {log_path}", flush=True)

    if not torch.cuda.is_available():
        raise RuntimeError("未检测到 CUDA GPU,量化需要 GPU 环境")

    # ── 显示运行配置 ──────────────────────────────────────────────
    print("=" * 60)
    print("  Qwen3.6-35B-A3B  llmcompressor W4A16_ASYM AWQ 量化")
    print("=" * 60)
    print(f"  源模型路径  : {args.model_path}")
    print(f"  输出路径    : {args.output_path}")
    print(f"  量化方案    : {args.scheme}")
    print(f"  校准数据集  : {args.calib_dataset}")
    print(f"  校准样本数  : {args.calib_samples}")
    print(f"  最大序列长  : {args.max_seq_length}")
    print(f"  GPU 卡号    : {args.gpus or os.environ.get('CUDA_VISIBLE_DEVICES', '全部')}")
    print("=" * 60)

    # ── GPU 信息 ──────────────────────────────────────────────────
    gpu_count = torch.cuda.device_count()
    phys_ids = args.gpus.split(",") if args.gpus else None
    get_gpu_info(gpu_count, phys_ids)

    os.makedirs(args.output_path, exist_ok=True)

    # ── 解析数据集规格 ────────────────────────────────────────────
    specs = parse_dataset_specs(args.calib_dataset, args.calib_samples)

    # ── 加载 Tokenizer ────────────────────────────────────────────
    from transformers import AutoTokenizer
    from llmcompressor import oneshot

    print(f"\n[1/3] 加载 Tokenizer ...")
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_path,
        trust_remote_code=True,
        local_files_only=True,
    )

    # ── 构造 recipe ───────────────────────────────────────────────
    #
    # Qwen3.6-35B-A3B 不量化的层（仅 QuantizationModifier 接受 ignore）:
    #   lm_head                   词表输出层
    #   re:.*mlp\.gate$           MoE 路由门控
    #   re:.*shared_expert.*      共享专家
    #   re:.*linear_attn.*        线性注意力层（Mamba-like）
    #   re:.*self_attn.*          全注意力层
    #   re:.*layers\.0\..*        第 0 层（紧接嵌入层,量化不稳定）
    #   re:.*mtp.*                Multi-Token Prediction 头部
    #   re:model\.visual.*        视觉编码器（若有）
    recipe = build_awq_recipe(
        ignore=MODEL_IGNORE_PRESETS["qwen3_5_moe"],
        scheme=args.scheme,
        duo_scaling="both",
    )

    # ── 一站式校准集准备: 打印配方 → 预下载 → 取消代理 → 加载混合 ─
    dataset, total_samples = prepare_calib_dataset(
        specs, tokenizer,
        skip_prefetch=args.skip_prefetch,
        unset_proxy_after_prefetch=True,
    )

    # ── 执行量化 ──────────────────────────────────────────────────
    print(f"\n[2/3] 开始 AWQ 量化（耗时约 1~4 小时）...")
    print(f"  scheme   : {args.scheme}")
    print(f"  校准数据 : {format_specs_summary(specs)}（max_seq={args.max_seq_length}）")

    if args.multi_gpu and gpu_count > 1:
        # 多卡模式: device_map='auto' 分布模型到所有 GPU,无 CPU offload,
        # pipeline='independent' 让 AWQ 校准前向充分利用所有卡。
        # 适合 Qwen3.6-35B(~70GB) on 4×80GB,模型完整装入 GPU。
        print(f"  模型加载 : device_map='auto' 多卡分布({gpu_count} 卡并行)")
        from transformers import AutoModelForCausalLM

        # ⚠️ 关键:必须用 max_memory 限制每卡显存,给 AWQ activation cache 留空间。
        # 不限制时 device_map='auto' 会用 90%+ 显存装模型,
        # AWQ SequentialPipeline + MoE 校准累积 `_parent_args_cache` 时必 OOM。
        # 50% 上限: 模型每卡 ~17.5GB + activation cache 余量 ~40GB,加 cpu offload 兜底。
        per_gpu_total_gib = torch.cuda.get_device_properties(0).total_memory / 2**30
        model_gib_per_gpu = int(per_gpu_total_gib * 0.50)
        max_memory = {i: f"{model_gib_per_gpu}GiB" for i in range(gpu_count)}
        max_memory["cpu"] = "500GiB"   # 主机 1TB RAM,500GB 兜底足够
        print(f"  显存预算 : 每卡 ≤ {model_gib_per_gpu} GiB 装模型,剩余给 activation cache")
        print(f"  CPU 兜底 : 500 GiB(activation offload 用)")

        # local_files_only=True: 因为 prepare_calib_dataset 已 unset 代理,
        # transformers 默认会先连 HF Hub 做版本检查,内网会超时。
        # 模型在本地完整存在,强制走本地避免不必要的 Hub 请求。
        model = AutoModelForCausalLM.from_pretrained(
            args.model_path,
            device_map="auto",
            max_memory=max_memory,
            dtype=torch.bfloat16,
            trust_remote_code=True,
            local_files_only=True,
        )
        # 打印实际分布
        device_counts = {}
        for _, param in model.named_parameters():
            d = str(param.device)
            device_counts[d] = device_counts.get(d, 0) + 1
        print("  层分布   :", end=" ")
        for dev, cnt in sorted(device_counts.items()):
            print(f"{dev}:{cnt}", end=" ")
        print()

        oneshot(
            model=model,                       # 传已加载模型对象
            tokenizer=tokenizer,
            recipe=recipe,
            dataset=dataset,
            num_calibration_samples=total_samples,
            max_seq_length=args.max_seq_length,
            pipeline="independent",            # 多卡并行前向
            moe_calibrate_all_experts=True,
            output_dir=args.output_path,
            save_compressed=True,
        )
    else:
        # 单卡模式: oneshot 接受字符串路径,内部 sequential offload
        # llmcompressor 0.12.0 推荐用于大 MoE 量化(256 expert 经过特殊优化):
        #   - 整模型常驻 CPU RAM,逐层/逐 expert 流式加载到 cuda:0
        #   - 每个 expert 处理完立刻释放,activation cache 不会爆显存
        #   - 慢但稳定,GLM-5.2 / DeepSeek-R1 等大 MoE 都用这条路径
        # 关键: sequential_offload_device="cpu" 必须显式传,否则可能整模型加载到
        # cuda:0(70GB > 80GB 临界,激活缓冲后 OOM)。GLM-5.2 mode_a 也是这样传的。
        print(f"  模型加载 : oneshot 内部 sequential offload(模型常驻 CPU,逐层搬到 cuda:0)")
        oneshot(
            model=args.model_path,             # 传路径字符串
            tokenizer=tokenizer,
            recipe=recipe,
            dataset=dataset,
            num_calibration_samples=total_samples,
            max_seq_length=args.max_seq_length,
            trust_remote_code_model=True,
            sequential_offload_device="cpu",   # 关键:强制 CPU offload,避免 cuda:0 OOM
            moe_calibrate_all_experts=True,
            output_dir=args.output_path,
            save_compressed=True,
        )

    print(f"\n[3/3] 量化完成,已保存到: {args.output_path}")

    print("\n✅ 量化完成!")
    print(f"   输出目录: {args.output_path}")
    print("   vLLM 加载: --quantization awq_marlin")
    print(f"   vllm serve {args.output_path} --quantization awq_marlin")


if __name__ == "__main__":
    main()
