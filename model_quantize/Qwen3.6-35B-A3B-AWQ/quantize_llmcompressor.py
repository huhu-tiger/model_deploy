#!/usr/bin/env python3
"""
Qwen3.6-35B-A3B AWQ-4bit 量化脚本 —— llmcompressor 方案
参考:
  - https://github.com/InternLM/lmdeploy/blob/main/examples/lite/qwen3_30b_a3b_awq.py
  - https://github.com/vllm-project/llm-compressor

该方案由 InternLM/lmdeploy 团队推荐，对 Qwen3 MoE 架构支持更完善，
使用 W4A16_ASYM AWQ 配方 + duo_scaling=both，适合 qwen3_5_moe 混合架构。

依赖安装（建议在 Docker 内执行，见 run_docker.sh）:
  pip install llmcompressor datasets transformers accelerate

量化产物与 AutoAWQ 格式兼容，可直接被 vLLM --quantization awq_marlin 加载。
"""

import argparse
import os
import sys

# ── GPU 预选：在 import torch（触发 CUDA 初始化）之前设置 CUDA_VISIBLE_DEVICES ──
# 支持两种方式:
#   1. 命令行参数 --gpus 0,1,2,3
#   2. 环境变量 CUDA_VISIBLE_DEVICES=0,1,2,3（已设置则沿用）
def _pre_select_gpus():
    """在 CUDA 初始化前解析 --gpus 参数并设置 CUDA_VISIBLE_DEVICES。"""
    for i, arg in enumerate(sys.argv):
        if arg in ("--gpus", "-gpus") and i + 1 < len(sys.argv):
            gpus = sys.argv[i + 1]
            os.environ["CUDA_VISIBLE_DEVICES"] = gpus
            print(f"[GPU 预选] CUDA_VISIBLE_DEVICES={gpus}", flush=True)
            return
    if "CUDA_VISIBLE_DEVICES" in os.environ:
        print(f"[GPU 预选] 沿用环境变量 CUDA_VISIBLE_DEVICES={os.environ['CUDA_VISIBLE_DEVICES']}", flush=True)
    else:
        print("[GPU 预选] 未指定 --gpus，将使用所有可用 GPU", flush=True)

_pre_select_gpus()

import torch
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="使用 llmcompressor 对 Qwen3.6-35B-A3B 进行 W4A16 AWQ 量化"
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default="/media/llm/Qwen/Qwen3.6-35B-A3B",
        help="原始 BF16 权重目录",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default="/media/llm/Qwen/Qwen3.6-35B-A3B-AWQ-4bit",
        help="量化后权重保存目录",
    )
    parser.add_argument(
        "--gpus",
        type=str,
        default=None,
        help="指定使用的 GPU 卡号（逗号分隔），例如: '0,1,2,3' 或 '4,5,6,7'。"
             "默认使用 CUDA_VISIBLE_DEVICES 环境变量或所有可用 GPU",
    )
    parser.add_argument(
        "--calib-dataset",
        type=str,
        default="cyankiwi/calibration",
        help=(
            "校准数据集，支持以下预设名称或任意 HuggingFace dataset ID:\n"
            "  cyankiwi     cyankiwi/calibration（原版校准集，16MB，推荐）\n"
            "  ultrachat    HuggingFaceH4/ultrachat_200k（英文指令对话）\n"
            "  pile         mit-han-lab/pile-val-backup（英文通用语料）\n"
            "  wikitext     wikitext-2-raw-v1（英文百科）\n"
            "  belle        BelleGroup/train_2M_CN（中文指令对话）\n"
            "  alpaca-zh    silk-road/alpaca-data-gpt4-chinese（中文指令）\n"
            "  firefly      YeungNLP/firefly-train-1.1M（中文多任务）\n"
            "  或直接传入 HuggingFace dataset ID"
        ),
    )
    parser.add_argument(
        "--calib-samples",
        type=int,
        default=384,
        help="校准样本数（cyankiwi/calibration 全量 384 条，MoE 256专家建议 ≥256）",
    )
    parser.add_argument(
        "--max-seq-length",
        type=int,
        default=2048,
        help="最大序列长度",
    )
    parser.add_argument(
        "--scheme",
        type=str,
        default="W4A16_ASYM",
        choices=["W4A16_ASYM", "W4A16", "W8A8_ASYM"],
        help="量化方案",
    )
    return parser.parse_args()


def get_calib_dataset(tokenizer, dataset_id: str, n_samples: int, max_seq_len: int):
    """
    构建校准数据集，兼容 llmcompressor oneshot API。
    支持预设名称别名和任意 HuggingFace dataset ID，降级到内置样本。
    """
    from datasets import load_dataset

    # 预设名称别名映射
    ALIASES = {
        "cyankiwi":  "cyankiwi/calibration",       # cyankiwi 原版校准集（推荐，16MB）
        "ultrachat": "HuggingFaceH4/ultrachat_200k",
        "pile":      "mit-han-lab/pile-val-backup",
        "wikitext":  "wikitext",
        "belle":     "BelleGroup/train_2M_CN",
        "alpaca-zh": "silk-road/alpaca-data-gpt4-chinese",
        "firefly":   "YeungNLP/firefly-train-1.1M",
    }
    dataset_id = ALIASES.get(dataset_id, dataset_id)

    print(f"[校准数据] 加载: {dataset_id}  样本数: {n_samples}  最大序列长: {max_seq_len}")

    DATASET_CONFIGS = {
        # cyankiwi 原版校准集：384 条多轮对话，conversations 字段，OpenAI 格式
        # 与 cyankiwi/Qwen3.6-35B-A3B-AWQ 使用完全相同的校准数据，可完整复现其量化结果
        "cyankiwi/calibration": {
            "split": "train",
            "text_field": None,
            "is_chat": True,
            "chat_field": "conversations",
            "role_key": "role",
            "content_key": "content",
        },
        "HuggingFaceH4/ultrachat_200k": {
            "split": "train_sft",
            "text_field": None,
            "is_chat": True,
            "chat_field": "messages",
        },
        "mit-han-lab/pile-val-backup": {
            "split": "validation",
            "text_field": "text",
            "is_chat": False,
        },
        "wikitext": {
            "split": "train",
            "config": "wikitext-2-raw-v1",
            "text_field": "text",
            "is_chat": False,
        },
        # 中文数据集
        "BelleGroup/train_2M_CN": {
            "split": "train",
            "text_field": "instruction",
            "is_chat": False,
        },
        "silk-road/alpaca-data-gpt4-chinese": {
            "split": "train",
            "text_field": "output",
            "is_chat": False,
        },
        "YeungNLP/firefly-train-1.1M": {
            "split": "train",
            "text_field": "input",
            "is_chat": False,
        },
    }

    cfg = DATASET_CONFIGS.get(dataset_id, {"split": "train", "text_field": "text", "is_chat": False})

    try:
        load_kwargs = {"split": cfg["split"], "trust_remote_code": True}
        if "config" in cfg:
            ds = load_dataset(dataset_id, cfg["config"], **load_kwargs)
        else:
            ds = load_dataset(dataset_id, **load_kwargs)
        ds = ds.shuffle(seed=42)
    except Exception as e:
        print(f"[警告] 数据集加载失败 ({e})，使用内置降级校准数据")
        return _build_fallback_dataset(tokenizer, n_samples, max_seq_len)

    def preprocess(example):
        if cfg.get("is_chat"):
            messages = example.get(cfg["chat_field"], [])
            # 过滤掉只有 system message 的样本
            if len(messages) < 2:
                return {"input_ids": [], "attention_mask": []}
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
                padding=False,
                max_length=max_seq_len,
                truncation=True,
                add_special_tokens=False,
            )
        else:
            text = example.get(cfg.get("text_field", "text"), "")
            if not text or len(text) < 100:
                return {"input_ids": [], "attention_mask": []}

        enc = tokenizer(
            text,
            truncation=True,
            padding=False,
            max_length=max_seq_len,
            add_special_tokens=False,
        )
        return enc

    ds = ds.map(preprocess, remove_columns=ds.column_names)
    ds = ds.filter(lambda x: len(x["input_ids"]) >= 64)
    ds = ds.select(range(min(n_samples, len(ds))))

    print(f"[校准数据] 实际可用样本: {len(ds)}")
    return ds


def _build_fallback_dataset(tokenizer, n_samples: int, max_seq_len: int):
    """内置多语言通用校准文本（降级方案）。"""
    from datasets import Dataset

    texts = [
        # 英文技术文本
        "Large language models leverage transformer architectures with attention mechanisms to process and generate human-like text across diverse domains.",
        "Mixture of Experts models route each input token to a subset of specialized expert networks, enabling efficient scaling of model capacity.",
        "Quantization compresses neural network weights from high-precision floating point to low-precision integers, trading minimal accuracy for significant speedup.",
        "The AWQ algorithm identifies salient weights through activation statistics and applies channel-wise scaling before quantization to preserve model quality.",
        "Post-training quantization enables deploying large models on resource-constrained hardware without the need for quantization-aware fine-tuning.",
        "Activation-aware weight quantization protects the most important weights by keeping them at higher precision during the quantization process.",
        "The self-attention mechanism computes compatibility scores between all pairs of positions in the input sequence to capture global dependencies.",
        "Knowledge distillation transfers knowledge from large teacher models to compact student models through soft probability distributions.",
        "Gradient checkpointing reduces memory usage during training by recomputing intermediate activations during the backward pass instead of storing them.",
        "LoRA enables efficient fine-tuning of large language models by training only low-rank decomposition matrices added to frozen model weights.",
        # 中文技术文本
        "大语言模型通过在海量文本数据上进行预训练，获得了强大的语言理解和生成能力，能够处理翻译、摘要、问答等多种自然语言处理任务。",
        "混合专家模型通过稀疏激活机制，在推理时只激活部分专家网络，实现了参数规模与计算量的解耦，大幅提升了模型的扩展效率。",
        "量化技术通过降低模型权重的存储精度，显著减少了模型的内存占用和推理延迟，使大模型能够在消费级硬件上流畅运行。",
        "检索增强生成技术将外部知识库与大语言模型相结合，有效缓解了模型知识截止日期的限制，提高了答案的准确性和时效性。",
        "注意力机制使模型能够在生成每个 token 时，动态关注输入序列中最相关的位置，从而捕捉长距离的语义依赖关系。",
        "思维链提示技术通过引导模型逐步展示推理过程，显著提升了大语言模型在复杂数学、逻辑推理任务上的准确率。",
        "模型对齐技术通过人类反馈强化学习等方法，使大语言模型的输出更符合人类价值观，减少有害或不准确内容的生成。",
        "分布式训练框架通过数据并行、模型并行和流水线并行等策略，使训练超大规模语言模型成为可能。",
        "提示词工程是一门通过精心设计输入文本来引导大语言模型产生期望输出的技术，在不修改模型参数的前提下提升性能。",
        "视觉语言模型将图像编码器与文本解码器相结合，实现了对图像内容的理解和描述，推动了多模态人工智能的发展。",
    ]

    calib_texts = (texts * ((n_samples // len(texts)) + 1))[:n_samples]

    data = []
    for text in calib_texts:
        enc = tokenizer(
            text,
            return_tensors=None,
            truncation=True,
            max_length=max_seq_len,
            add_special_tokens=True,
        )
        if len(enc["input_ids"]) >= 32:
            data.append(enc)

    return Dataset.from_list(data)


def main():
    args = parse_args()

    # ── GPU 选择：在 CUDA 初始化前设置 CUDA_VISIBLE_DEVICES ──
    # 最可靠的方式是在脚本入口处（import torch 之前）设置，
    # 但由于顶部已经 import torch，这里通过 os.environ 设置，
    # 对后续加载的模型（device_map="auto"）仍然有效。
    if args.gpus is not None:
        os.environ["CUDA_VISIBLE_DEVICES"] = args.gpus
        print(f"[GPU] 已设置 CUDA_VISIBLE_DEVICES={args.gpus}")
    elif "CUDA_VISIBLE_DEVICES" in os.environ:
        print(f"[GPU] 使用环境变量 CUDA_VISIBLE_DEVICES={os.environ['CUDA_VISIBLE_DEVICES']}")

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

    if not torch.cuda.is_available():
        raise RuntimeError("未检测到 CUDA GPU，量化需要 GPU 环境")

    gpu_count = torch.cuda.device_count()
    phys_ids = args.gpus.split(",") if args.gpus else None
    print(f"\n[GPU] 实际可用 {gpu_count} 张 GPU:")
    for i in range(gpu_count):
        name = torch.cuda.get_device_name(i)
        mem = torch.cuda.get_device_properties(i).total_memory / 1024**3
        phys_label = f" (物理卡 {phys_ids[i]})" if phys_ids and i < len(phys_ids) else ""
        print(f"  GPU {i}{phys_label}: {name}  显存: {mem:.1f} GB")

    os.makedirs(args.output_path, exist_ok=True)

    from transformers import AutoTokenizer
    from llmcompressor import oneshot
    # 新 API（llmcompressor >= 0.12）：AWQ = AWQTransformModifier + QuantizationModifier
    # 旧的 AWQModifier（from llmcompressor.modifiers.awq）已废弃
    from llmcompressor.modifiers.transform.awq import AWQTransformModifier
    from llmcompressor.modifiers.quantization import QuantizationModifier

    # 加载 Tokenizer
    print(f"\n[1/3] 加载 Tokenizer ...")
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_path,
        trust_remote_code=True,
    )

    # AWQ 量化配方（新 API 两步骤）
    # AWQTransformModifier: 计算 per-channel 缩放因子（需要校准数据前向传播）
    # QuantizationModifier: 应用缩放并做 RTN 量化
    #
    # ignore 列表:
    #   lm_head                   : 输出词表层
    #   re:.*mlp\.gate$           : MoE 路由门控
    #   re:.*shared_expert.*      : 共享专家
    #   re:.*linear_attn.*        : Qwen3.6 线性注意力层（Mamba-like）
    #   re:.*self_attn.*          : 全注意力层
    #   re:.*layers\.0\..*        : 第 0 层（紧接嵌入层，量化不稳定）
    #   re:.*mtp.*                : Multi-Token Prediction 头部
    #   re:model\.visual.*        : 视觉编码器
    IGNORE_LIST = [
        "lm_head",
        "re:.*mlp\\.gate$",
        "re:.*shared_expert.*",
        "re:.*linear_attn.*",
        "re:.*self_attn.*",
        "re:.*layers\\.0\\..*",
        "re:.*mtp.*",
        "re:model\\.visual.*",
    ]
    recipe = [
        AWQTransformModifier(
            ignore=IGNORE_LIST,
            duo_scaling="both",
        ),
        QuantizationModifier(
            ignore=IGNORE_LIST,
            scheme=args.scheme,
            targets=["Linear"],
        ),
    ]

    print(f"\n[2/3] 开始 AWQ 量化（耗时约 1~4 小时）...")
    print(f"  scheme: {args.scheme}")
    print(f"  校准数据: {args.calib_dataset}  样本数: {args.calib_samples}")
    print(f"  模型路径传字符串，llmcompressor 内部管理加载（支持 sequential offload）")

    # oneshot 接受字符串路径，内部自动加载模型并按层做 sequential offload
    # 避免手动 AutoModelForCausalLM.from_pretrained 导致 OOM
    oneshot(
        model=args.model_path,           # 传路径字符串，非预加载模型
        tokenizer=tokenizer,
        recipe=recipe,
        dataset=args.calib_dataset,
        num_calibration_samples=args.calib_samples,
        max_seq_length=args.max_seq_length,
        trust_remote_code_model=True,
        output_dir=args.output_path,
        save_compressed=True,
    )

    print(f"\n[3/3] 量化完成，已保存到: {args.output_path}")

    print("\n✅ 量化完成！")
    print(f"   输出目录: {args.output_path}")
    print("   vLLM 加载参数: --quantization awq_marlin")
    print(f"   vllm serve {args.output_path} --quantization awq_marlin")


if __name__ == "__main__":
    main()
