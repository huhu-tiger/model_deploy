"""
量化执行前资源预检。

支持两种模式（GLM-5.2 / DeepSeek-V3 等大模型场景使用）:
    A. 单卡 sequential offload  —— 整模型常驻 CPU RAM,逐层 → GPU → CPU
    B. 多卡 device_map + offload —— 模型分布到所有 GPU + CPU RAM

通用检查:
    - GPU 显存 / CPU 内存 / 磁盘空间
    - 输出磁盘可用 ≥ 模型大小 × 0.35
"""

from __future__ import annotations

from .memory import (
    parse_memory_gib,
    get_cpu_available_gib,
    get_model_size_gib,
    get_model_layer_count,
    get_output_disk_free_gib,
)


_SEP = "═" * 66
_LINE = "─" * 66


def _check_row(label: str, required: str, actual: str, ok: bool) -> bool:
    flag = "✅" if ok else "❌"
    print(f"  {flag}  {label:<26} 需 {required:<16} 实 {actual}")
    return ok


def _warn_row(label: str, note: str):
    print(f"  ⚠️  {label:<26} {note}")


def check_resources(
    mode: str,
    model_path: str,
    output_path: str,
    gpu_count: int,
    total_vram_gib: float,
    per_gpu_vram_gib: list[float],
    cpu_memory_str: str = "1000GiB",
    gpu_memory_utilization: float = 0.70,
    default_layers: int = 40,
) -> bool:
    """
    返回 True 表示全部通过,False 表示存在不足项。

    模式 A: 单卡 sequential offload
      ① 单卡显存 ≥ 最大层估算（模型大小 / 层数 × 3，保守估算 MoE 大层）
      ② CPU 可用内存 ≥ 模型大小 × 1.2

    模式 B: 多卡 device_map
      ① GPU 数量 ≥ 2
      ② GPU(util) + cpu_memory ≥ 模型大小 × 1.1
      ③ CPU 实际可用 ≥ cpu_memory + 50 GiB

    公共: 输出磁盘 ≥ 模型大小 × 0.35
    """
    print(f"\n{_SEP}")
    mode_label = (
        "A（单卡 sequential offload）"
        if mode == "A"
        else "B（多卡 device_map + CPU offload）"
    )
    print(f"  资源预检 —— 模式 {mode_label}")
    print(_SEP)

    try:
        model_size_gib, file_count = get_model_size_gib(model_path)
    except FileNotFoundError as e:
        print(f"  ❌  {e}")
        print(_SEP)
        return False

    print(f"  ℹ️  模型大小（BF16）: {model_size_gib:.0f} GiB（{file_count} 个权重文件）")
    print(_LINE)

    all_pass = True

    if mode == "A":
        num_layers = get_model_layer_count(model_path, default=default_layers)
        max_layer_gib = model_size_gib / num_layers * 3
        single_gpu_gib = per_gpu_vram_gib[0] if per_gpu_vram_gib else 0.0

        ok = single_gpu_gib >= max_layer_gib
        all_pass &= _check_row(
            "单卡显存（GPU 0）",
            f"≥ {max_layer_gib:.0f} GiB",
            f"{single_gpu_gib:.1f} GiB",
            ok,
        )
        if not ok:
            _warn_row(
                "  提示",
                f"模型共 {num_layers} 层,估算最大单层 {max_layer_gib:.0f} GiB"
                "（MoE 层含大量专家）,当前显存不足以顺序加载单层",
            )

        cpu_avail_gib = get_cpu_available_gib()
        required_cpu = model_size_gib * 1.2
        ok = cpu_avail_gib >= required_cpu
        all_pass &= _check_row(
            "CPU 可用内存",
            f"≥ {required_cpu:.0f} GiB",
            f"{cpu_avail_gib:.0f} GiB",
            ok,
        )
        if not ok:
            _warn_row(
                "  提示",
                f"模式 A 整个模型常驻 CPU RAM,"
                f"当前可用 {cpu_avail_gib:.0f} GiB < 所需 {required_cpu:.0f} GiB",
            )

    else:
        cpu_memory_gib = parse_memory_gib(cpu_memory_str)
        cpu_avail_gib = get_cpu_available_gib()
        gpu_alloc_gib = total_vram_gib * gpu_memory_utilization
        per_gpu_alloc = gpu_alloc_gib / gpu_count if gpu_count else 0
        total_cap_gib = gpu_alloc_gib + cpu_memory_gib
        required_cap = model_size_gib * 1.1

        ok = gpu_count >= 2
        all_pass &= _check_row("GPU 数量", "≥ 2 张", f"{gpu_count} 张", ok)

        print(
            f"  ℹ️  GPU 显存分配({gpu_memory_utilization:.0%}): {gpu_count} × "
            f"{per_gpu_alloc:.0f} GiB = {gpu_alloc_gib:.0f} GiB"
        )

        surplus = total_cap_gib - required_cap
        ok = total_cap_gib >= required_cap
        all_pass &= _check_row(
            "GPU+CPU 总容量",
            f"≥ {required_cap:.0f} GiB",
            f"{total_cap_gib:.0f} GiB（余 {surplus:+.0f} GiB）",
            ok,
        )
        if not ok:
            _warn_row(
                "  提示",
                f"GPU({gpu_alloc_gib:.0f}) + CPU({cpu_memory_gib:.0f}) = "
                f"{total_cap_gib:.0f} GiB < 模型 {model_size_gib:.0f} × 1.1 = "
                f"{required_cap:.0f} GiB,请增大 --cpu-memory",
            )

        required_avail = cpu_memory_gib + 50
        ok = cpu_avail_gib >= required_avail
        all_pass &= _check_row(
            "CPU 可用内存",
            f"≥ {required_avail:.0f} GiB",
            f"{cpu_avail_gib:.0f} GiB",
            ok,
        )
        if not ok:
            _warn_row(
                "  提示",
                f"--cpu-memory={cpu_memory_str} 请求 {cpu_memory_gib:.0f} GiB,"
                f"当前可用 {cpu_avail_gib:.0f} GiB 不足",
            )

    # 公共: 输出磁盘
    disk_free_gib = get_output_disk_free_gib(output_path)
    required_disk_gib = model_size_gib * 0.35
    ok = disk_free_gib >= required_disk_gib
    all_pass &= _check_row(
        "输出磁盘可用",
        f"≥ {required_disk_gib:.0f} GiB",
        f"{disk_free_gib:.0f} GiB",
        ok,
    )
    if not ok:
        _warn_row(
            "  提示",
            f"输出路径 {output_path!r} 磁盘剩余 {disk_free_gib:.0f} GiB"
            f" < 预估量化产物 {required_disk_gib:.0f} GiB",
        )

    print(_LINE)
    if all_pass:
        print("  ✅  预检通过,资源充足,开始量化")
    else:
        print("  ❌  预检未通过,存在资源不足项（详见上方提示）,请确认后再运行")
    print(_SEP)

    return all_pass
