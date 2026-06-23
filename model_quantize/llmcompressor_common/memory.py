"""
内存 / 磁盘 / 模型大小工具。

不依赖 psutil 等三方库,仅用 stdlib + /proc/meminfo。
"""

from __future__ import annotations

import json
import os
import shutil


def parse_memory_gib(mem_str: str) -> float:
    """
    将内存字符串解析为 GiB 浮点数。
    支持: '1000GiB' / '960GB' / '1000G' / '860000MiB' / '900000MB'
    """
    s = mem_str.strip()
    su = s.upper()
    if su.endswith("GIB"):
        return float(s[:-3])
    if su.endswith("GB"):
        return float(s[:-2]) * 1e9 / 2**30
    if su.endswith("G"):
        return float(s[:-1])
    if su.endswith("MIB"):
        return float(s[:-3]) / 1024
    if su.endswith("MB"):
        return float(s[:-2]) * 1e6 / 2**30
    raise ValueError(
        f"无法解析内存字符串 {mem_str!r}，支持格式: GiB / GB / G / MiB / MB"
    )


def get_cpu_available_gib() -> float:
    """读取 /proc/meminfo MemAvailable（含可释放 buff/cache），返回 GiB。"""
    meminfo: dict = {}
    with open("/proc/meminfo") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2:
                meminfo[parts[0].rstrip(":")] = int(parts[1])  # kB
    avail_kb = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
    return avail_kb / 2**20


def resolve_cpu_memory_str(cpu_memory_str: str) -> str:
    """
    解析 --cpu-memory 参数。

    "auto" (默认): 取系统当前可用内存的 80%,避免硬编码值随环境变化失效。
    固定值（如 "1100GiB"）: 直接使用。
    """
    if cpu_memory_str.strip().lower() == "auto":
        avail_gib = get_cpu_available_gib()
        alloc_gib = avail_gib * 0.80
        resolved = f"{alloc_gib:.0f}GiB"
        print(
            f"[CPU 自动配置] 当前可用 {avail_gib:.0f} GiB × 80% = {alloc_gib:.0f} GiB"
            f" → --cpu-memory={resolved}"
        )
        return resolved
    return cpu_memory_str


def get_model_size_gib(model_path: str) -> tuple[float, int]:
    """
    扫描模型目录中 .safetensors / .bin 权重文件大小。
    返回 (model_size_gib, file_count)。
    仅读取 inode 元数据,速度快。
    """
    total_bytes = 0
    file_count = 0
    for root, _, files in os.walk(model_path):
        for fname in files:
            if fname.endswith((".safetensors", ".bin")):
                total_bytes += os.path.getsize(os.path.join(root, fname))
                file_count += 1
    if file_count == 0:
        raise FileNotFoundError(
            f"在 {model_path!r} 未找到 .safetensors / .bin 权重文件，"
            "请确认模型已完整下载"
        )
    return total_bytes / 2**30, file_count


def get_model_layer_count(model_path: str, default: int = 40) -> int:
    """从 config.json 读取 num_hidden_layers，找不到时返回 default。"""
    config_path = os.path.join(model_path, "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                cfg = json.load(f)
            return int(cfg.get("num_hidden_layers", default))
        except Exception:
            pass
    return default


def get_output_disk_free_gib(output_path: str) -> float:
    """返回输出路径所在分区的可用磁盘空间（GiB）。目录不存在时向上找父目录。"""
    check_path = output_path
    while check_path and not os.path.exists(check_path):
        check_path = os.path.dirname(check_path)
    if not check_path:
        check_path = "/"
    _, _, free = shutil.disk_usage(check_path)
    return free / 2**30
