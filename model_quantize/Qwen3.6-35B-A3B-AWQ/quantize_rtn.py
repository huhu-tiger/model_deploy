#!/usr/bin/env python3
"""
Qwen3.6-35B-A3B  无校准数据 RTN AWQ-INT4 量化脚本（复现 QuantTrio 方案）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
参考：
  - QuantTrio/Qwen3.6-35B-A3B-AWQ（HuggingFace）—— data-free RTN
  - FeanorsCodeSL/dgx-spark-quantization  awq_gemm.py（Apache-2.0 公开复现）
    https://github.com/FeanorsCodeSL/dgx-spark-quantization

技术规格（与 QuantTrio 精确一致）：
  - 算法        : RTN（Round-to-Nearest），无需校准数据集
  - 位宽        : W4A16，4-bit 整数权重 + fp16 激活
  - 组大小      : 128
  - 对称性      : 非对称（zero_point=True，按组 min/max 量化）
  - 打包格式    : AWQ GEMM，pack_order=[0,4,1,5,2,6,3,7]
  - 不量化层    : visual / linear_attn / self_attn / shared_expert /
                  mlp.gate / model.layers.0 / mtp / norms / embed / lm_head

多卡并行：
  - 26 个 shard 按 GPU 数量均分，每张卡独立处理自己的 shard 子集
  - 各 worker 进程独占一张 GPU（CUDA_VISIBLE_DEVICES 隔离）
  - 单卡 ~30 分钟；4 卡 ~8 分钟（瓶颈在磁盘 I/O）

用法：
  # 单卡
  python quantize_rtn.py --gpus 0

  # 多卡并行（推荐，速度提升约 N 倍，受磁盘 I/O 限制）
  python quantize_rtn.py --gpus 0,1,2,3

  # 纯 CPU（无 GPU 也可运行，速度较慢）
  python quantize_rtn.py --device cpu
"""

import argparse
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path


# ── 主进程 GPU 预选（import torch 之前）──────────────────────────
def _pre_select_gpus():
    for i, arg in enumerate(sys.argv):
        if arg in ("--gpus", "-gpus") and i + 1 < len(sys.argv):
            gpus = sys.argv[i + 1]
            os.environ["CUDA_VISIBLE_DEVICES"] = gpus
            print(f"[GPU] CUDA_VISIBLE_DEVICES={gpus}", flush=True)
            return
    if "CUDA_VISIBLE_DEVICES" in os.environ:
        print(f"[GPU] 沿用 CUDA_VISIBLE_DEVICES={os.environ['CUDA_VISIBLE_DEVICES']}", flush=True)

_pre_select_gpus()
# ──────────────────────────────────────────────────────────────────

import torch
from safetensors import safe_open
from safetensors.torch import save_file
from tqdm import tqdm


# ══════════════════════════════════════════════════════════════════
#  量化配置（精确复现 QuantTrio/Qwen3.6-35B-A3B-AWQ）
# ══════════════════════════════════════════════════════════════════

QUANTIZATION_CONFIG = {
    "quant_method": "awq",
    "bits": 4,
    "group_size": 128,
    "version": "gemm",
    "zero_point": True,
    "modules_to_not_convert": [
        "visual",
        "linear_attn",
        "self_attn",
        "shared_expert",
        "mlp.gate",
        "layers.0.",        # 跳过第 0 层（紧接嵌入层，量化不稳定）
                            # 适配多模态路径 model.language_model.layers.0.*
        "mtp",
    ],
}

AWQ_PACK_ORDER  = [0, 4, 1, 5, 2, 6, 3, 7]
GROUP_SIZE      = QUANTIZATION_CONFIG["group_size"]
BITS            = QUANTIZATION_CONFIG["bits"]
ELEMS_PER_I32   = 32 // BITS


# ══════════════════════════════════════════════════════════════════
#  核心量化函数
# ══════════════════════════════════════════════════════════════════

def quantize_tensor_rtn(weight: torch.Tensor) -> tuple:
    """
    RTN 非对称分组量化。
    输入  weight : [out_features, in_features]  bf16/fp16
    输出  (qweight, qzeros, scales) —— AWQ GEMM 格式
    """
    w = weight.to(torch.float32)
    out_features, in_features = w.shape
    assert in_features % GROUP_SIZE == 0

    n_groups  = in_features // GROUP_SIZE
    w_grouped = w.reshape(out_features, n_groups, GROUP_SIZE)
    w_min     = w_grouped.amin(dim=-1)
    w_max     = w_grouped.amax(dim=-1)

    max_int = 2 ** BITS - 1
    scales  = (w_max - w_min) / max_int
    scales  = scales.clamp(min=1e-8)
    zeros   = (-w_min / scales).round().clamp(0, max_int)

    w_q = ((w_grouped - w_min.unsqueeze(-1)) / scales.unsqueeze(-1))
    w_q = w_q.round().clamp(0, max_int).to(torch.int32)
    w_q = w_q.reshape(out_features, in_features).T.contiguous()   # [I, O]

    qweight  = _pack_int4_to_int32(w_q)
    scales_t = scales.T.to(torch.float16).contiguous()
    zeros_t  = zeros.T.to(torch.int32).contiguous()
    qzeros   = _pack_int4_to_int32(zeros_t)

    return qweight.cpu(), qzeros.cpu(), scales_t.cpu()


def _pack_int4_to_int32(x: torch.Tensor) -> torch.Tensor:
    """将 int4 张量按 AWQ pack_order 打包为 int32（在原设备上计算，避免大矩阵 CPU 传输）。"""
    assert x.shape[-1] % ELEMS_PER_I32 == 0
    shape  = x.shape[:-1]
    n      = x.shape[-1]
    device = x.device
    n_i32  = n // ELEMS_PER_I32
    x_flat = x.reshape(-1, n).int()                         # 留在原设备（GPU）
    out    = torch.zeros(x_flat.shape[0], n_i32,
                         dtype=torch.int32, device=device)
    for i, src in enumerate(AWQ_PACK_ORDER):
        col_group = torch.arange(src, n, ELEMS_PER_I32, device=device)
        out |= ((x_flat[:, col_group] & 0xF) << (i * BITS))
    return out.reshape(*shape, n_i32)                       # 调用方负责 .cpu()


def should_skip(name: str, skip_patterns: list) -> bool:
    return any(pat in name for pat in skip_patterns)


def is_2d_linear_weight(name: str, tensor: torch.Tensor) -> bool:
    return (
        name.endswith(".weight")
        and tensor.ndim == 2
        and tensor.dtype in (torch.float16, torch.bfloat16, torch.float32)
        and tensor.shape[0] >= 64
        and tensor.shape[1] % GROUP_SIZE == 0
    )


def is_3d_expert_weight(name: str, tensor: torch.Tensor) -> bool:
    """
    判断是否为 MoE 融合专家权重（3D 张量）。
    形如 mlp.experts.gate_up_proj / mlp.experts.down_proj
    shape: [num_experts, out_features, in_features]
    """
    return (
        tensor.ndim == 3
        and tensor.dtype in (torch.float16, torch.bfloat16, torch.float32)
        and "experts" in name
        and any(k in name for k in ("gate_up_proj", "down_proj", "gate_proj", "up_proj"))
        and tensor.shape[2] % GROUP_SIZE == 0  # in_features 能整除 group_size
    )


def quantize_3d_expert_tensor(base_name: str, tensor: torch.Tensor,
                               shard_name: str) -> tuple[dict, dict, int]:
    """
    将 3D 融合专家张量量化并拆分为 per-expert 格式。
    采用批量向量化处理：将所有专家合并为一个大 2D 矩阵，
    一次 GPU 运算完成量化，避免 Python 层面 256 次循环。

    输入:
      base_name : "...layers.N.mlp.experts.gate_up_proj" 或 "...down_proj"
      tensor    : shape [num_experts, out_features, in_features]

    对 gate_up_proj: 沿 out_features 拆成 gate (前半) 和 up (后半) 两批分别量化
    对 down_proj   : 直接批量量化

    输出:
      tensors_out : {key: tensor}
      weight_map  : {key: shard_name}
      param_count : 量化参数总数
    """
    num_experts, out_features, in_features = tensor.shape
    is_gate_up    = "gate_up_proj" in base_name
    expert_prefix = base_name.rsplit(".", 1)[0]  # "...layers.N.mlp.experts"

    tensors_out = {}
    weight_map  = {}
    param_count = 0

    def _batch_quant_and_split(w_batch: torch.Tensor, proj_name: str):
        """
        w_batch: [num_experts, out, in]
        向量化量化并按专家切片回存。
        """
        n, out, in_f = w_batch.shape
        if in_f % GROUP_SIZE != 0:
            # 不满足对齐要求，全部以 bf16 保存
            for i in range(n):
                key = f"{expert_prefix}.{i}.{proj_name}.weight"
                tensors_out[key] = w_batch[i].to(torch.bfloat16).cpu()
                weight_map[key]  = shard_name
            return 0

        # 合并所有专家 → [n*out, in]，一次完成量化
        w_flat = w_batch.reshape(n * out, in_f)
        qw_flat, qz_flat, sc_flat = quantize_tensor_rtn(w_flat)
        # qw_flat : [in,       n*out // ELEMS_PER_I32]
        # qz_flat : [n_groups, n*out // ELEMS_PER_I32]  n_groups = in // GROUP_SIZE
        # sc_flat : [n_groups, n*out]
        out_packed = out // ELEMS_PER_I32

        total_params = 0
        for i in range(n):
            pfx = f"{expert_prefix}.{i}.{proj_name}"
            tensors_out[f"{pfx}.qweight"] = qw_flat[:, i * out_packed : (i + 1) * out_packed].contiguous()
            tensors_out[f"{pfx}.qzeros"]  = qz_flat[:, i * out_packed : (i + 1) * out_packed].contiguous()
            tensors_out[f"{pfx}.scales"]  = sc_flat[:, i * out        : (i + 1) * out       ].contiguous()
            for s in (".qweight", ".qzeros", ".scales"):
                weight_map[f"{pfx}{s}"] = shard_name
            total_params += out * in_f
        return total_params

    if is_gate_up:
        half = out_features // 2
        param_count += _batch_quant_and_split(tensor[:, :half, :], "gate_proj")
        param_count += _batch_quant_and_split(tensor[:, half:, :], "up_proj")
    else:
        proj_name    = base_name.rsplit(".", 1)[1]   # "down_proj"
        param_count += _batch_quant_and_split(tensor, proj_name)

    return tensors_out, weight_map, param_count


# ══════════════════════════════════════════════════════════════════
#  单 worker：处理分配给自己的 shard 列表
# ══════════════════════════════════════════════════════════════════

def _worker(worker_id: int, gpu_id: int, shard_paths: list,
            src_dir: str, dst_dir: str, skip_patterns: list,
            result_queue: mp.Queue):
    """
    在独立进程中运行，处理 shard_paths 列表中的所有 shard。
    gpu_id: 该 worker 独占的物理 GPU 编号（通过 CUDA_VISIBLE_DEVICES 隔离）。
    返回 weight_map 片段和统计信息到 result_queue。
    """
    # 每个 worker 进程独立设置自己的 GPU
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    device = "cuda:0" if torch.cuda.is_available() else "cpu"

    src_dir = Path(src_dir)
    dst_dir = Path(dst_dir)

    local_weight_map = {}
    stats = {"quantized": 0, "skipped": 0, "params": 0}

    for shard_path in tqdm(
        shard_paths,
        desc=f"  GPU{gpu_id}(worker{worker_id})",
        position=worker_id,
        leave=True,
        ncols=80,
    ):
        shard_path = Path(shard_path)
        tensors_out = {}

        with safe_open(shard_path, framework="pt", device=device) as f:
            for key in f.keys():
                tensor = f.get_tensor(key)

                if not should_skip(key, skip_patterns) and is_3d_expert_weight(key, tensor):
                    # ── 3D 融合专家张量：拆分量化 ──
                    base = key  # 完整 key，如 "...experts.gate_up_proj"
                    t_out, w_map, n_params = quantize_3d_expert_tensor(
                        base, tensor, shard_path.name
                    )
                    tensors_out.update(t_out)
                    local_weight_map.update(w_map)
                    stats["quantized"] += 1
                    stats["params"]    += n_params

                elif not should_skip(key, skip_patterns) and is_2d_linear_weight(key, tensor):
                    # ── 普通 2D Linear 权重 ──
                    base = key[:-len(".weight")]
                    qw, qz, sc = quantize_tensor_rtn(tensor)
                    tensors_out[f"{base}.qweight"] = qw
                    tensors_out[f"{base}.qzeros"]  = qz
                    tensors_out[f"{base}.scales"]  = sc
                    stats["quantized"] += 1
                    stats["params"]    += tensor.numel()
                    for suffix in (".qweight", ".qzeros", ".scales"):
                        local_weight_map[f"{base}{suffix}"] = shard_path.name

                else:
                    # ── 保留原始精度（跳过层、norms、embeds 等）──
                    tensors_out[key] = tensor.to(torch.bfloat16) if tensor.is_floating_point() else tensor
                    local_weight_map[key] = shard_path.name
                    stats["skipped"] += 1

        save_file(tensors_out, dst_dir / shard_path.name, metadata={"format": "pt"})
        del tensors_out
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    result_queue.put((local_weight_map, stats))


# ══════════════════════════════════════════════════════════════════
#  多卡并行调度
# ══════════════════════════════════════════════════════════════════

def quantize_shards_parallel(src_dir: Path, dst_dir: Path,
                              skip_patterns: list, gpu_ids: list) -> dict:
    """
    将 shard 文件均分到各 GPU，启动 N 个 worker 进程并行量化。
    gpu_ids: 物理 GPU 编号列表，如 [0, 1, 2, 3]
    """
    index_file = src_dir / "model.safetensors.index.json"
    if index_file.exists():
        with open(index_file) as f:
            index = json.load(f)
        all_shards = sorted(set(src_dir / v for v in index["weight_map"].values()))
    else:
        all_shards = sorted(src_dir.glob("model.safetensors"))

    n_gpus   = len(gpu_ids)
    n_shards = len(all_shards)
    print(f"\n  共 {n_shards} 个 shard，分配到 {n_gpus} 张 GPU 并行处理")
    print(f"  GPU 编号: {gpu_ids}")

    # 将 shard 均分（尽量均匀）
    chunks = [[] for _ in range(n_gpus)]
    for i, shard in enumerate(all_shards):
        chunks[i % n_gpus].append(str(shard))
    for i, c in enumerate(chunks):
        print(f"  GPU {gpu_ids[i]}: {len(c)} 个 shard")

    # 启动多进程（spawn 模式，避免 CUDA fork 问题）
    ctx = mp.get_context("spawn")
    result_queue = ctx.Queue()
    processes = []

    for worker_id, (gpu_id, shard_chunk) in enumerate(zip(gpu_ids, chunks)):
        if not shard_chunk:
            continue
        p = ctx.Process(
            target=_worker,
            args=(worker_id, gpu_id, shard_chunk,
                  str(src_dir), str(dst_dir), skip_patterns, result_queue),
            daemon=True,
        )
        p.start()
        processes.append(p)

    # 等待所有进程完成，收集结果
    merged_weight_map = {}
    total_stats = {"quantized": 0, "skipped": 0, "params": 0}

    for _ in processes:
        wmap, stats = result_queue.get()
        merged_weight_map.update(wmap)
        for k in total_stats:
            total_stats[k] += stats[k]

    for p in processes:
        p.join()

    print(f"\n  量化统计: {total_stats['quantized']} 层已量化 / "
          f"{total_stats['skipped']} 层保留原精度 / "
          f"参数量 {total_stats['params'] / 1e9:.2f}B")

    return merged_weight_map


def quantize_shards_single(src_dir: Path, dst_dir: Path,
                            skip_patterns: list, device: str) -> dict:
    """单设备串行量化（单卡或纯 CPU）。"""
    index_file = src_dir / "model.safetensors.index.json"
    if index_file.exists():
        with open(index_file) as f:
            index = json.load(f)
        all_shards = sorted(set(src_dir / v for v in index["weight_map"].values()))
    else:
        all_shards = sorted(src_dir.glob("model.safetensors"))

    print(f"\n  共 {len(all_shards)} 个 shard，单设备串行处理（{device}）")
    weight_map = {}
    stats = {"quantized": 0, "skipped": 0, "params": 0}

    for shard_path in tqdm(all_shards, desc="量化 shard", ncols=80):
        tensors_out = {}
        with safe_open(shard_path, framework="pt", device=device) as f:
            for key in tqdm(f.keys(), desc=f"  {shard_path.name}", leave=False, ncols=80):
                tensor = f.get_tensor(key)

                if not should_skip(key, skip_patterns) and is_3d_expert_weight(key, tensor):
                    t_out, w_map, n_params = quantize_3d_expert_tensor(
                        key, tensor, shard_path.name
                    )
                    tensors_out.update(t_out)
                    weight_map.update(w_map)
                    stats["quantized"] += 1
                    stats["params"]    += n_params

                elif not should_skip(key, skip_patterns) and is_2d_linear_weight(key, tensor):
                    base = key[:-len(".weight")]
                    qw, qz, sc = quantize_tensor_rtn(tensor)
                    tensors_out[f"{base}.qweight"] = qw
                    tensors_out[f"{base}.qzeros"]  = qz
                    tensors_out[f"{base}.scales"]  = sc
                    stats["quantized"] += 1
                    stats["params"]    += tensor.numel()
                    for suffix in (".qweight", ".qzeros", ".scales"):
                        weight_map[f"{base}{suffix}"] = shard_path.name

                else:
                    tensors_out[key] = tensor.to(torch.bfloat16) if tensor.is_floating_point() else tensor
                    weight_map[key]  = shard_path.name
                    stats["skipped"] += 1

        save_file(tensors_out, dst_dir / shard_path.name, metadata={"format": "pt"})
        del tensors_out
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    print(f"\n  量化统计: {stats['quantized']} 层已量化 / "
          f"{stats['skipped']} 层保留原精度 / "
          f"参数量 {stats['params'] / 1e9:.2f}B")
    return weight_map


# ══════════════════════════════════════════════════════════════════
#  辅助：写出 config / index / 非权重文件
# ══════════════════════════════════════════════════════════════════

def write_config(src_dir: Path, dst_dir: Path):
    with open(src_dir / "config.json") as f:
        cfg = json.load(f)
    cfg["quantization_config"] = QUANTIZATION_CONFIG
    cfg["architectures"] = ["Qwen3_5MoeForConditionalGeneration"]
    with open(dst_dir / "config.json", "w") as f:
        json.dump(cfg, f, indent=2, sort_keys=True)


def write_index(src_dir: Path, dst_dir: Path, weight_map: dict):
    src_index = src_dir / "model.safetensors.index.json"
    if src_index.exists():
        with open(src_index) as f:
            meta = json.load(f).get("metadata", {})
    else:
        meta = {}
    with open(dst_dir / "model.safetensors.index.json", "w") as f:
        json.dump({"metadata": meta, "weight_map": weight_map}, f, indent=2)


def copy_non_weights(src_dir: Path, dst_dir: Path):
    import shutil
    skip_ext   = {".safetensors"}
    skip_names = {"config.json", "model.safetensors.index.json"}
    for item in src_dir.iterdir():
        if item.is_file() and item.suffix not in skip_ext and item.name not in skip_names:
            shutil.copy2(item, dst_dir / item.name)


# ══════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="RTN AWQ-INT4 量化（QuantTrio 方案），支持多卡并行"
    )
    parser.add_argument("--model-path",  default="/media/llm/Qwen/Qwen3.6-35B-A3B")
    parser.add_argument("--output-path", default="/media/llm/Qwen/Qwen3.6-35B-A3B-AWQ-4bit-RTN")
    parser.add_argument(
        "--gpus", type=str, default=None,
        help="GPU 卡号（逗号分隔）。"
             "单卡: '0'  多卡并行: '0,1,2,3'  留空则 CPU",
    )
    parser.add_argument(
        "--device", default="auto", choices=["auto", "cpu", "cuda"],
        help="仅单 GPU 时生效。多 GPU 时由 --gpus 自动管理",
    )
    parser.add_argument(
        "--extra-skip", default="",
        help="额外不量化的模块名（逗号分隔）",
    )
    return parser.parse_args()


def main():
    args  = parse_args()
    src_dir = Path(args.model_path)
    dst_dir = Path(args.output_path)

    if not src_dir.exists():
        raise FileNotFoundError(f"源模型目录不存在: {src_dir}")
    dst_dir.mkdir(parents=True, exist_ok=True)

    skip_patterns = list(QUANTIZATION_CONFIG["modules_to_not_convert"])
    if args.extra_skip:
        skip_patterns += [s.strip() for s in args.extra_skip.split(",") if s.strip()]

    # 解析 GPU 列表
    gpu_ids = []
    if args.gpus:
        gpu_ids = [int(g.strip()) for g in args.gpus.split(",") if g.strip()]
    elif "CUDA_VISIBLE_DEVICES" in os.environ:
        visible = os.environ["CUDA_VISIBLE_DEVICES"]
        if visible not in ("", "-1", "NoDevFiles"):
            gpu_ids = [int(g.strip()) for g in visible.split(",") if g.strip()]

    use_parallel = len(gpu_ids) > 1

    print("═" * 65)
    print("  Qwen3.6-35B-A3B  RTN AWQ-INT4 量化（QuantTrio 方案）")
    print("═" * 65)
    print(f"  源模型路径  : {src_dir}")
    print(f"  输出路径    : {dst_dir}")
    print(f"  量化算法    : RTN（data-free，无需校准数据）")
    print(f"  量化参数    : W4A16 | group_size=128 | zero_point=True | GEMM")
    if use_parallel:
        print(f"  并行模式    : 多卡并行（{len(gpu_ids)} 张 GPU: {gpu_ids}）")
    elif gpu_ids:
        print(f"  并行模式    : 单卡（GPU {gpu_ids[0]}）")
    else:
        print(f"  并行模式    : CPU（无 GPU）")
    print(f"  跳过层      : {skip_patterns}")
    print("═" * 65)

    t0 = time.time()

    # ── 量化 ──────────────────────────────────────────────────────
    print("\n[1/3] 量化 shard 文件...")
    if use_parallel:
        weight_map = quantize_shards_parallel(src_dir, dst_dir, skip_patterns, gpu_ids)
    else:
        if gpu_ids:
            device = "cuda:0"
        elif args.device == "auto":
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
        else:
            device = args.device
        weight_map = quantize_shards_single(src_dir, dst_dir, skip_patterns, device)

    # ── 写出元数据 ────────────────────────────────────────────────
    print("\n[2/3] 写出 config.json 和 index...")
    write_config(src_dir, dst_dir)
    write_index(src_dir, dst_dir, weight_map)

    print("\n[3/3] 复制 tokenizer 等配置文件...")
    copy_non_weights(src_dir, dst_dir)

    elapsed = time.time() - t0

    # ── 磁盘空间对比 ──────────────────────────────────────────────
    def dir_size_gb(path: Path) -> float:
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1024**3

    src_gb  = dir_size_gb(src_dir)
    dst_gb  = dir_size_gb(dst_dir)
    saved   = src_gb - dst_gb
    ratio   = dst_gb / src_gb * 100 if src_gb > 0 else 0

    print(f"\n{'═' * 65}")
    print(f"✅ 量化完成！耗时 {elapsed / 60:.1f} 分钟")
    print(f"")
    print(f"   {'原始模型':<12}: {src_gb:>7.2f} GB  ({src_dir})")
    print(f"   {'量化模型':<12}: {dst_gb:>7.2f} GB  ({dst_dir})")
    print(f"   {'节省空间':<12}: {saved:>7.2f} GB  (压缩至原始的 {ratio:.1f}%)")
    print(f"")
    print(f"   vLLM 参数: --quantization awq_marlin")
    print("═" * 65)


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)
    main()
