#!/usr/bin/env python3
"""
validate_pipeline.py  ——  GLM-5.2 量化流程最小验证脚本
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
在正式量化（4~6 小时）前运行，总耗时 < 5 分钟（不加载大模型）。

Stages:
  Stage 1  依赖 & 版本          ≈ 10 秒
  Stage 2  GPU / CPU / 磁盘     ≈ 10 秒
  Stage 3  模型文件完整性        ≈ 30 秒（仅读 inode，不加载权重）
  Stage 4  GLM-5.2 Tokenizer    ≈ 30 秒（本地文件，无需网络）
  Stage 5  校准数据集            ≈ 30 秒（缓存命中则即时）
  Stage 6  量化 dry-run          ≈ 2 分钟（微型随机模型走完完整 AWQ 流程）

运行命令：
  # 在量化容器内执行（推荐）
  docker compose -f docker-compose-quantize.yml run --rm quant-llmcompressor-multi \\
    python3 validate_pipeline.py [--multi-gpu] [--skip-dryrun]

  # 本地直接运行（已安装依赖）
  python3 validate_pipeline.py --model-path /media/llm/ZhipuAI/GLM-5.2
"""

import argparse
import os
import shutil
import sys
import time
import traceback

# ── 全局格式常量 ─────────────────────────────────────────────────
SEP  = "═" * 66
LINE = "─" * 66

def _p(icon, msg):
    print(f"  {icon}  {msg}")

def ok(msg):   _p("✅", msg)
def fail(msg): _p("❌", msg)
def warn(msg): _p("⚠️ ", msg)
def info(msg): _p("ℹ️ ", msg)

def section(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")


# ══════════════════════════════════════════════════════════════════
# Stage 1：依赖 & 版本
# ══════════════════════════════════════════════════════════════════

def stage1_dependencies():
    import torch
    cuda_ok = torch.cuda.is_available()
    if not cuda_ok:
        raise RuntimeError("torch.cuda.is_available() = False，请确认 GPU 环境")
    ok(f"torch {torch.__version__}  CUDA {torch.version.cuda}  ✓")

    import transformers
    ok(f"transformers {transformers.__version__}  ✓")

    import llmcompressor
    ok(f"llmcompressor {llmcompressor.__version__}  ✓")

    import datasets
    ok(f"datasets {datasets.__version__}  ✓")

    # 验证关键导入路径
    from llmcompressor.modifiers.transform.awq import AWQModifier
    from llmcompressor.modifiers.quantization import QuantizationModifier
    from llmcompressor import oneshot
    ok("llmcompressor 关键模块导入正常（transform.awq / quantization / oneshot）✓")


# ══════════════════════════════════════════════════════════════════
# Stage 2：GPU / CPU / 磁盘资源
# ══════════════════════════════════════════════════════════════════

def stage2_resources(model_path, output_path, multi_gpu):
    import torch

    gpu_count = torch.cuda.device_count()
    if gpu_count == 0:
        raise RuntimeError("未检测到任何 GPU")

    total_vram = 0.0
    for i in range(gpu_count):
        name = torch.cuda.get_device_name(i)
        mem  = torch.cuda.get_device_properties(i).total_memory / 2**30
        total_vram += mem
        info(f"GPU {i}: {name}  {mem:.1f} GiB")
    ok(f"合计显存 {total_vram:.1f} GiB（{gpu_count} 张）")

    if multi_gpu and gpu_count < 2:
        warn(f"--multi-gpu 但只有 {gpu_count} 张卡，将回退到模式 A")

    # CPU 可用内存
    with open("/proc/meminfo") as f:
        meminfo = {}
        for line in f:
            parts = line.split()
            if len(parts) >= 2:
                meminfo[parts[0].rstrip(":")] = int(parts[1])
    avail_gib = meminfo.get("MemAvailable", 0) / 2**20
    ok(f"CPU 可用内存 {avail_gib:.0f} GiB  ✓")

    # 磁盘
    check_path = output_path
    while check_path and not os.path.exists(check_path):
        check_path = os.path.dirname(check_path)
    if not check_path:
        check_path = "/"
    free_gib = shutil.disk_usage(check_path).free / 2**30
    ok(f"输出磁盘可用 {free_gib:.0f} GiB  ✓")


# ══════════════════════════════════════════════════════════════════
# Stage 3：模型文件完整性
# ══════════════════════════════════════════════════════════════════

def stage3_model_files(model_path):
    if not os.path.isdir(model_path):
        raise FileNotFoundError(f"模型目录不存在: {model_path!r}")

    # 统计权重文件
    total_bytes = 0
    file_count  = 0
    for root, _, files in os.walk(model_path):
        for fname in files:
            if fname.endswith((".safetensors", ".bin")):
                total_bytes += os.path.getsize(os.path.join(root, fname))
                file_count  += 1

    if file_count == 0:
        raise FileNotFoundError(f"未找到 .safetensors / .bin 权重文件，模型可能未完整下载")

    size_gib = total_bytes / 2**30
    ok(f"权重文件 {file_count} 个，合计 {size_gib:.1f} GiB  ✓")

    # 验证 config.json 存在
    cfg_path = os.path.join(model_path, "config.json")
    if not os.path.exists(cfg_path):
        raise FileNotFoundError(f"config.json 不存在: {cfg_path}")

    import json
    with open(cfg_path) as f:
        cfg = json.load(f)
    arch     = cfg.get("architectures", ["unknown"])[0]
    n_layers = cfg.get("num_hidden_layers", "?")
    ok(f"config.json：架构 {arch}，层数 {n_layers}  ✓")

    # 验证 model.safetensors.index.json（分片模型）
    idx_path = os.path.join(model_path, "model.safetensors.index.json")
    if os.path.exists(idx_path):
        with open(idx_path) as f:
            idx = json.load(f)
        shards = set(idx.get("weight_map", {}).values())
        ok(f"safetensors index：引用 {len(shards)} 个 shard，实际有 {file_count} 个  ✓")
        if len(shards) != file_count:
            warn(f"shard 数量不一致：index 引用 {len(shards)}，实际 {file_count}，可能未完整下载")


# ══════════════════════════════════════════════════════════════════
# Stage 4：GLM-5.2 Tokenizer 加载
# ══════════════════════════════════════════════════════════════════

def stage4_tokenizer(model_path):
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        trust_remote_code=True,
    )
    vocab_size = tokenizer.vocab_size
    ok(f"Tokenizer 加载成功，vocab_size={vocab_size}  ✓")

    # 简单编码测试
    sample = "量化验证：The quick brown fox."
    ids = tokenizer.encode(sample)
    if not ids:
        raise ValueError("tokenizer.encode() 返回空列表")
    ok(f"encode 测试 OK：{len(ids)} 个 token，max_id={max(ids)}  ✓")

    return tokenizer   # 供 Stage 6 复用


# ══════════════════════════════════════════════════════════════════
# Stage 5：校准数据集
# ══════════════════════════════════════════════════════════════════

_NETWORK_KEYWORDS = (
    "connection", "timeout", "proxy", "cannot connect",
    "network", "ssl", "certificate", "handshake", "refused",
)

def stage5_dataset(dataset_name, num_samples):
    from datasets import load_dataset

    cache_dir = os.environ.get("HF_DATASETS_CACHE", "（默认）")
    info(f"缓存路径: {cache_dir}")

    # HF_HUB_OFFLINE 是两处模块级常量（导入时固定，改环境变量无效）：
    #   - huggingface_hub.constants.HF_HUB_OFFLINE（控制 Hub HTTP 层）
    #   - datasets.config.HF_HUB_OFFLINE（datasets 内部检查点，独立缓存）
    # TRANSFORMERS_OFFLINE=1 容器环境下必须同时 patch 两处，才能让数据集下载成功。
    import huggingface_hub.constants as _hc
    import datasets.config as _dc
    _orig_hc, _orig_dc = _hc.HF_HUB_OFFLINE, _dc.HF_HUB_OFFLINE
    _hc.HF_HUB_OFFLINE = False
    _dc.HF_HUB_OFFLINE = False
    _dc.HF_DATASETS_OFFLINE = False
    try:
        ds = load_dataset(dataset_name, split="train", trust_remote_code=True)
    except Exception as e:
        err_lower = str(e).lower()
        if any(kw in err_lower for kw in _NETWORK_KEYWORDS):
            raise RuntimeError(
                f"网络错误，数据集下载失败: {e}\n请检查 HTTP_PROXY/HTTPS_PROXY"
            ) from e
        raise RuntimeError(
            f"数据集加载失败: {e}\n"
            f"若数据集名称含子集（如 wikitext），请检查格式"
        ) from e
    finally:
        _hc.HF_HUB_OFFLINE = _orig_hc
        _dc.HF_HUB_OFFLINE = _orig_dc
        _dc.HF_DATASETS_OFFLINE = _orig_dc

    total = len(ds)
    if total < num_samples:
        raise RuntimeError(
            f"数据集只有 {total} 条，少于 --calib-samples={num_samples}"
        )
    ok(f"数据集 {dataset_name!r} 就绪，共 {total} 条，需 {num_samples} 条  ✓")
    return ds


# ══════════════════════════════════════════════════════════════════
# Stage 6：量化 dry-run（微型模型，端到端验证）
# ══════════════════════════════════════════════════════════════════

def stage6_dryrun(tokenizer, dataset_name):
    """
    用随机初始化的微型 GPT-2 模型（~60 MB）端到端走完：
      AWQModifier → QuantizationModifier → oneshot → save_compressed
    不加载 GLM-5.2 权重，约 2 分钟，验证完整流程无报错。
    """
    import torch
    from transformers import LlamaConfig, LlamaForCausalLM
    from llmcompressor.modifiers.transform.awq import AWQModifier
    from llmcompressor.modifiers.quantization import QuantizationModifier
    from llmcompressor import oneshot
    from datasets import Dataset

    VOCAB    = tokenizer.vocab_size
    DRY_DIR  = "/tmp/glm52_quant_dryrun"

    # ── 构建微型 LLaMA（随机权重，无需下载）──────────────────────
    # 使用 LLaMA 架构：层名（q_proj/k_proj/v_proj/gate_proj 等）与 AWQ
    # 默认 mapping 完全一致，能真实验证 AWQModifier 的 smooth/scale 流程。
    cfg = LlamaConfig(
        vocab_size           = VOCAB,
        hidden_size          = 128,
        num_hidden_layers    = 2,
        num_attention_heads  = 4,
        num_key_value_heads  = 4,
        intermediate_size    = 512,
        max_position_embeddings = 128,
        bos_token_id = tokenizer.bos_token_id or 1,
        eos_token_id = tokenizer.eos_token_id or 2,
    )
    info(f"构建微型 LLaMA：vocab={VOCAB}, hidden=128, layers=2, pos=128")
    model = LlamaForCausalLM(cfg)
    model = model.cuda()
    param_m = sum(p.numel() for p in model.parameters()) / 1e6
    info(f"模型参数量 {param_m:.1f}M，已加载到 GPU  ✓")

    # ── recipe（与正式量化完全相同）─────────────────────────────
    recipe = [
        AWQModifier(duo_scaling="both"),
        QuantizationModifier(
            ignore  = ["lm_head", "embed_tokens"],
            scheme  = "W4A16_ASYM",
            targets = ["Linear"],
        ),
    ]
    info("recipe 构建：[AWQModifier, QuantizationModifier]  ✓")

    # ── 最小校准数据（内存构造，不依赖网络）────────────────────
    texts = ["The quick brown fox jumps over the lazy dog. " * 8] * 4
    fake_ds = Dataset.from_dict({"text": texts})
    info(f"校准数据集：内存构造 {len(fake_ds)} 条（dry-run 专用）")

    # ── 清理输出目录 ────────────────────────────────────────────
    if os.path.exists(DRY_DIR):
        shutil.rmtree(DRY_DIR)
    os.makedirs(DRY_DIR, exist_ok=True)

    # ── 执行 oneshot ─────────────────────────────────────────────
    info("执行 oneshot（AWQ + W4A16_ASYM）...")
    oneshot(
        model                   = model,
        tokenizer               = tokenizer,
        recipe                  = recipe,
        dataset                 = fake_ds,
        num_calibration_samples = 4,
        max_seq_length          = 64,
        moe_calibrate_all_experts = False,
        output_dir              = DRY_DIR,
        save_compressed         = True,
    )

    # ── 验证输出 ─────────────────────────────────────────────────
    out_files = os.listdir(DRY_DIR)
    if not out_files:
        raise RuntimeError(f"oneshot 未产生任何输出文件: {DRY_DIR}")

    has_weights = any(
        f.endswith((".safetensors", ".bin")) for f in out_files
    )
    if not has_weights:
        raise RuntimeError(
            f"输出目录 {DRY_DIR} 无权重文件，输出: {out_files}"
        )

    ok(f"oneshot 完成，输出文件: {out_files}  ✓")
    shutil.rmtree(DRY_DIR, ignore_errors=True)
    ok("dry-run 输出目录已清理  ✓")


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="GLM-5.2 量化流程最小验证（< 5 分钟，不加载大模型）"
    )
    parser.add_argument("--model-path",     default="/media/llm/ZhipuAI/GLM-5.2")
    parser.add_argument("--output-path",    default="/media/llm/ZhipuAI/GLM-5.2-AWQ-4bit-LC")
    parser.add_argument("--calib-dataset",  default="cyankiwi/calibration")
    parser.add_argument("--calib-samples",  type=int, default=384)
    parser.add_argument("--multi-gpu",      action="store_true",
                        help="验证模式 B（8 卡）资源要求")
    parser.add_argument("--skip-dryrun",    action="store_true",
                        help="跳过 Stage 6 端到端 dry-run（无 GPU 时使用）")
    return parser.parse_args()


def main():
    args = parse_args()

    print(f"\n{SEP}")
    print(f"  GLM-5.2 量化流程验证脚本")
    print(f"  模型路径  : {args.model_path}")
    print(f"  输出路径  : {args.output_path}")
    print(f"  校准数据  : {args.calib_dataset}（{args.calib_samples} 条）")
    print(f"  运行模式  : {'模式 B（多卡）' if args.multi_gpu else '模式 A（单卡）'}")
    print(SEP)

    # 收集 stage 执行结果
    results   = []
    tokenizer = None   # Stage 4 产出，Stage 6 复用

    stages = [
        ("Stage 1  依赖 & 版本",
         lambda: stage1_dependencies()),
        ("Stage 2  GPU / CPU / 磁盘资源",
         lambda: stage2_resources(args.model_path, args.output_path, args.multi_gpu)),
        ("Stage 3  模型文件完整性",
         lambda: stage3_model_files(args.model_path)),
        ("Stage 4  GLM-5.2 Tokenizer",
         None),   # 特殊处理，需要接收返回值
        ("Stage 5  校准数据集",
         lambda: stage5_dataset(args.calib_dataset, args.calib_samples)),
    ]

    if not args.skip_dryrun:
        stages.append((
            "Stage 6  量化 dry-run（微型模型端到端）",
            None   # 特殊处理，依赖 tokenizer
        ))

    for name, fn in stages:
        section(name)
        t0 = time.time()
        try:
            if "Stage 4" in name:
                tokenizer = stage4_tokenizer(args.model_path)
            elif "Stage 6" in name:
                if tokenizer is None:
                    warn("Stage 4 未完成，跳过 dry-run")
                    results.append((name, "SKIP"))
                    continue
                stage6_dryrun(tokenizer, args.calib_dataset)
            else:
                fn()

            elapsed = time.time() - t0
            ok(f"└─ 耗时 {elapsed:.1f}s")
            results.append((name, "PASS"))

        except Exception as e:
            elapsed = time.time() - t0
            fail(f"└─ 耗时 {elapsed:.1f}s")
            fail(f"   错误类型: {type(e).__name__}")
            fail(f"   错误信息: {e}")
            if os.environ.get("VALIDATE_VERBOSE"):
                traceback.print_exc()
            results.append((name, "FAIL"))

    # ── 汇总 ─────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("  验证结果汇总")
    print(SEP)
    passed = sum(1 for _, s in results if s == "PASS")
    failed = sum(1 for _, s in results if s == "FAIL")
    skipped = sum(1 for _, s in results if s == "SKIP")
    for name, status in results:
        icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️ "}.get(status, "?")
        print(f"  {icon}  {name}")
    print(LINE)
    print(f"  通过 {passed}  失败 {failed}  跳过 {skipped}")

    if failed == 0:
        print("  ✅  全部通过，可以执行正式量化")
    else:
        print("  ❌  存在失败项，请修复后再运行量化")
        print(f"     提示：设置 VALIDATE_VERBOSE=1 可查看完整堆栈")
    print(SEP)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
