"""
GPU 预选与信息打印工具。

CRITICAL: pre_select_gpus() 必须在 `import torch` **之前**调用，
否则 CUDA allocator 已初始化，CUDA_VISIBLE_DEVICES 的修改不再生效。

用法（在脚本入口处）:
    import sys, os
    from llmcompressor_common.gpu_select import pre_select_gpus
    pre_select_gpus()              # 解析 sys.argv 中的 --gpus 参数

    import torch                    # 必须在 pre_select_gpus 之后
"""

from __future__ import annotations

import os
import sys


def pre_select_gpus(argv: list[str] | None = None) -> str | None:
    """
    在 CUDA 初始化前解析 `--gpus / -gpus` 参数并设置 CUDA_VISIBLE_DEVICES。

    解析优先级:
      1. argv 中显式传入的 --gpus <ids>
      2. 已有的环境变量 CUDA_VISIBLE_DEVICES
      3. 未指定 → 使用所有可用 GPU

    返回最终生效的 CUDA_VISIBLE_DEVICES 值（None 表示未设置）。
    """
    argv = argv if argv is not None else sys.argv
    for i, arg in enumerate(argv):
        if arg in ("--gpus", "-gpus") and i + 1 < len(argv):
            gpus = argv[i + 1]
            os.environ["CUDA_VISIBLE_DEVICES"] = gpus
            print(f"[GPU 预选] CUDA_VISIBLE_DEVICES={gpus}", flush=True)
            return gpus

    existing = os.environ.get("CUDA_VISIBLE_DEVICES")
    if existing is not None:
        print(f"[GPU 预选] 沿用 CUDA_VISIBLE_DEVICES={existing}", flush=True)
        return existing

    print("[GPU 预选] 未指定 --gpus，将使用所有可用 GPU", flush=True)
    return None


def get_gpu_info(gpu_count: int, phys_ids: list[str] | None = None) -> tuple[float, list[float]]:
    """
    打印 GPU 列表与显存信息。
    返回 (total_vram_gib, per_gpu_vram_gib)。

    phys_ids: 物理 GPU 编号列表（来自 --gpus 参数）。仅用于打印对照，
              告诉用户「容器内 GPU 0」对应「物理卡几」。
    """
    import torch  # 延迟 import,确保调用方已经做完 GPU 预选

    print(f"\n[GPU] 实际可用 {gpu_count} 张 GPU:")
    total_vram = 0.0
    per_gpu: list[float] = []
    for i in range(gpu_count):
        name = torch.cuda.get_device_name(i)
        mem = torch.cuda.get_device_properties(i).total_memory / 2**30
        total_vram += mem
        per_gpu.append(mem)
        phys = f" (物理卡 {phys_ids[i]})" if phys_ids and i < len(phys_ids) else ""
        print(f"  GPU {i}{phys}: {name}  显存: {mem:.1f} GiB")
    print(f"  合计显存: {total_vram:.1f} GiB")
    return total_vram, per_gpu
