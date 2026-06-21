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
    - 8 × H100 80GB = 640 GB 常驻 GPU，剩余 offload 到 CPU
    - 校准前向传播同时利用所有 GPU，减少 PCIe 传输次数
    - 理论加速 30~50%（相比模式 A）

依赖：
  镜像 model.vnet.com/sjhl/vllm-openai:v0.23.0-llmcompressor 已内置

用法：
  # 模式 A（单卡）
  python3 quantize_llmcompressor.py --gpus 0

  # 模式 B（8 卡）
  python3 quantize_llmcompressor.py --gpus 0,1,2,3,4,5,6,7 --multi-gpu
"""

import argparse
import datetime
import gc
import json
import logging
import os
import shutil
import sys


# ══════════════════════════════════════════════════════════════════
# 日志：Tee（stdout/stderr → 终端 + 文件）
# ══════════════════════════════════════════════════════════════════

class _Tee:
    """
    将 stdout / stderr 同时写入终端和日志文件，不依赖 fileno()。
    捕获所有 print()、transformers logger.warning()（含 CONVERSION 报告）。
    """
    def __init__(self, stream, logfile):
        self._stream  = stream
        self._logfile = logfile

    def write(self, data: str) -> int:
        self._stream.write(data)
        self._stream.flush()
        self._logfile.write(data)
        self._logfile.flush()
        return len(data)

    def flush(self):
        self._stream.flush()
        self._logfile.flush()

    def isatty(self) -> bool:
        return False

    @property
    def encoding(self):
        return getattr(self._stream, "encoding", "utf-8")

    @property
    def errors(self):
        return getattr(self._stream, "errors", "replace")


_tee_log_fh: "open | None" = None  # 全局引用，防止 GC 关闭文件句柄


def _sanitize_filename_part(value: str) -> str:
    """将模型名等文本转换为适合文件名的片段。"""
    safe = []
    for ch in value:
        if ch.isalnum() or ch in ("-", "_", "."):
            safe.append(ch)
        else:
            safe.append("-")
    return "".join(safe).strip("-") or "model"


def default_log_dir() -> str:
    """默认日志目录：当前脚本所在目录下的 logs/。"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


def setup_logging(log_dir: str | None, mode_tag: str = "quant", model_path: str = "model") -> str:
    """
    初始化日志系统。

    做法：
      1. 将 sys.stdout / sys.stderr 替换为 _Tee，同时写入终端和日志文件。
         → 捕获所有 print() 输出
      2. 为 root logger 添加 FileHandler（WARNING 级别）。
         → 捕获 transformers 通过 logging.warning() 输出的 CONVERSION 报告
         → 输出带时间戳的格式，与 print() 原始行交叉排列，便于对照

    参数:
      log_dir   : 日志目录；未指定时使用当前脚本所在目录的 logs/
      mode_tag  : 日志文件名前缀标签（如 mode_a / mode_b）
      model_path: 模型路径，用其目录名生成日志文件名

    返回: 日志文件绝对路径
    """
    global _tee_log_fh
    if not log_dir:
        log_dir = default_log_dir()
    os.makedirs(log_dir, exist_ok=True)

    ts         = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    model_name = _sanitize_filename_part(os.path.basename(os.path.abspath(model_path.rstrip("/"))))
    log_path   = os.path.join(log_dir, f"{ts}_{model_name}_{mode_tag}.log")

    # ── 打开日志文件（行缓冲，实时刷新）─────────────────────────────
    _tee_log_fh = open(log_path, "w", encoding="utf-8", buffering=1)

    # ── Tee stdout + stderr ──────────────────────────────────────
    sys.stdout = _Tee(sys.__stdout__, _tee_log_fh)
    sys.stderr = _Tee(sys.__stderr__, _tee_log_fh)

    # ── logging FileHandler（WARNING+，带时间戳）──────────────────
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    fh.setLevel(logging.WARNING)
    fh.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.addHandler(fh)

    # transformers 默认向 stderr 输出（已被 Tee 捕获），确保级别不低于 WARNING
    try:
        import transformers as _tf
        _tf.logging.set_verbosity_warning()
    except Exception:
        pass

    print(f"[日志] 写入路径: {log_path}", flush=True)
    return log_path


# ── GPU 预选（必须在 import torch 之前执行）────────────────────────
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

# 必须在 import torch 前设置，否则 CUDA allocator 可能已经初始化。
# GLM-5.2 MoE 权重合并时会产生较大的临时张量，expandable_segments
# 可减少保留显存碎片导致的 OOM。
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import torch


# ══════════════════════════════════════════════════════════════════
# 公共工具函数
# ══════════════════════════════════════════════════════════════════

def parse_memory_gib(mem_str: str) -> float:
    """
    将内存字符串解析为 GiB 浮点数。
    支持格式：'1000GiB' / '960GB' / '1000G' / '860000MiB' / '900000MB'
    """
    s = mem_str.strip()
    su = s.upper()
    if su.endswith("GIB"):
        return float(s[:-3])
    if su.endswith("GB"):
        return float(s[:-2]) * 1e9 / 2**30   # 1 GB = 10^9 B → GiB
    if su.endswith("G"):
        return float(s[:-1])
    if su.endswith("MIB"):
        return float(s[:-3]) / 1024
    if su.endswith("MB"):
        return float(s[:-2]) * 1e6 / 2**30
    raise ValueError(
        f"无法解析内存字符串 {mem_str!r}，支持格式：GiB / GB / G / MiB / MB"
    )


def get_model_size_gib(model_path: str) -> tuple:
    """
    扫描模型目录中 .safetensors / .bin 权重文件大小。
    返回 (model_size_gib: float, file_count: int)。
    仅读取 inode 元数据，速度快（282 个文件约 <1 秒）。
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


def get_model_layer_count(model_path: str) -> int:
    """从 config.json 读取 num_hidden_layers，找不到时返回默认值 78。"""
    config_path = os.path.join(model_path, "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                cfg = json.load(f)
            return int(cfg.get("num_hidden_layers", 78))
        except Exception:
            pass
    return 78


def get_cpu_available_gib() -> float:
    """
    返回系统当前可用物理内存（GiB）。
    读取 /proc/meminfo MemAvailable（含可释放 buff/cache），无需 psutil。
    """
    meminfo: dict = {}
    with open("/proc/meminfo") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2:
                meminfo[parts[0].rstrip(":")] = int(parts[1])   # 单位 kB
    avail_kb = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
    return avail_kb / 2**20   # kB → GiB


def resolve_cpu_memory_str(cpu_memory_str: str) -> str:
    """
    解析 --cpu-memory 参数，返回实际使用的 GiB 字符串。

    "auto"（默认）：取系统当前可用内存的 80%，避免硬编码值随环境变化失效。
    固定值（如 "1100GiB"）：直接使用，不做换算。
    """
    if cpu_memory_str.strip().lower() == "auto":
        avail_gib = get_cpu_available_gib()
        alloc_gib = avail_gib * 0.80
        resolved  = f"{alloc_gib:.0f}GiB"
        print(
            f"[CPU 自动配置] 当前可用 {avail_gib:.0f} GiB × 80% = {alloc_gib:.0f} GiB"
            f" → --cpu-memory={resolved}"
        )
        return resolved
    return cpu_memory_str


def get_output_disk_free_gib(output_path: str) -> float:
    """返回输出路径所在分区的可用磁盘空间（GiB）。"""
    # 若目录不存在，向上找到存在的父目录
    check_path = output_path
    while check_path and not os.path.exists(check_path):
        check_path = os.path.dirname(check_path)
    if not check_path:
        check_path = "/"
    total, used, free = shutil.disk_usage(check_path)
    return free / 2**30


def get_gpu_info(gpu_count: int, phys_ids: list) -> tuple:
    """
    打印 GPU 信息。
    返回 (total_vram_gib: float, per_gpu_vram_gib: list[float])。
    """
    print(f"\n[GPU] 实际可用 {gpu_count} 张 GPU:")
    total_vram = 0.0
    per_gpu = []
    for i in range(gpu_count):
        name = torch.cuda.get_device_name(i)
        mem  = torch.cuda.get_device_properties(i).total_memory / 2**30
        total_vram += mem
        per_gpu.append(mem)
        phys = f" (物理卡 {phys_ids[i]})" if phys_ids and i < len(phys_ids) else ""
        print(f"  GPU {i}{phys}: {name}  显存: {mem:.1f} GiB")
    print(f"  合计显存: {total_vram:.1f} GiB")
    return total_vram, per_gpu


# ══════════════════════════════════════════════════════════════════
# 资源预检（公共入口）
# ══════════════════════════════════════════════════════════════════

_SEP  = "═" * 66
_LINE = "─" * 66

def _check_row(label: str, required: str, actual: str, ok: bool) -> bool:
    """打印一行预检结果，返回 ok 本身（方便链式调用 all_pass &= ...）。"""
    flag = "✅" if ok else "❌"
    print(f"  {flag}  {label:<26} 需 {required:<16} 实 {actual}")
    return ok


def _warn_row(label: str, note: str):
    """打印一行警告信息（不影响通过/失败判定）。"""
    print(f"  ⚠️  {label:<26} {note}")


def check_resources(
    mode: str,
    model_path: str,
    output_path: str,
    gpu_count: int,
    total_vram_gib: float,
    per_gpu_vram_gib: list,
    cpu_memory_str: str = "1000GiB",
    gpu_memory_utilization: float = 0.70,
) -> bool:
    """
    量化执行前资源预检，根据模式自动选择检查逻辑。

    模式 A（sequential offload，单卡）：
      ① 单卡显存 ≥ 最大层估算（模型大小 / 层数 × 3，保守估算 MoE 大层）
      ② CPU 可用内存 ≥ 模型大小 × 1.2（整模型常驻 CPU + 激活缓冲）

    模式 B（multi-GPU device_map）：
      ① GPU 数量 ≥ 2
      ② GPU(gpu_memory_utilization) + cpu_memory_gib ≥ 模型大小 × 1.1（10% 激活余量）
      ③ CPU 实际可用 ≥ cpu_memory_gib + 50 GiB（OS / 进程余量）

    公共检查：
      ④ 输出磁盘剩余 ≥ 模型大小 × 0.35（AWQ INT4 约原始 BF16 的 30%）

    返回 True 表示全部通过，False 表示存在不足项（已打印详细警告）。
    """
    print(f"\n{_SEP}")
    mode_label = "A（单卡 sequential offload）" if mode == "A" else "B（多卡 device_map + CPU offload）"
    print(f"  资源预检 —— 模式 {mode_label}")
    print(_SEP)

    # ── 获取模型尺寸 ────────────────────────────────────────────
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
        # ── 模式 A 检查 ──────────────────────────────────────────
        num_layers = get_model_layer_count(model_path)
        # MoE 大层约为均值 3 倍（256 expert FFN vs dense attention）
        max_layer_gib = model_size_gib / num_layers * 3
        single_gpu_gib = per_gpu_vram_gib[0] if per_gpu_vram_gib else 0.0

        # ① 单卡显存
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
                f"模型共 {num_layers} 层，估算最大单层 {max_layer_gib:.0f} GiB"
                "（MoE 层含 256 专家），当前显存不足以顺序加载单层",
            )

        # ② CPU 可用内存（须能容纳整个模型 + 激活缓冲）
        cpu_avail_gib = get_cpu_available_gib()
        required_cpu  = model_size_gib * 1.2
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
                f"模式 A 整个模型常驻 CPU RAM，"
                f"当前可用 {cpu_avail_gib:.0f} GiB < 所需 {required_cpu:.0f} GiB",
            )

    else:
        # ── 模式 B 检查 ──────────────────────────────────────────
        cpu_memory_gib = parse_memory_gib(cpu_memory_str)
        cpu_avail_gib  = get_cpu_available_gib()
        gpu_alloc_gib  = total_vram_gib * gpu_memory_utilization
        per_gpu_alloc  = gpu_alloc_gib / gpu_count if gpu_count else 0
        total_cap_gib  = gpu_alloc_gib + cpu_memory_gib
        required_cap   = model_size_gib * 1.1   # 10% 激活余量

        # ① GPU 数量 ≥ 2
        ok = gpu_count >= 2
        all_pass &= _check_row("GPU 数量", "≥ 2 张", f"{gpu_count} 张", ok)

        # ② GPU 显存分配情况（信息行，不作 pass/fail）
        print(
            f"  ℹ️  GPU 显存分配({gpu_memory_utilization:.0%}): {gpu_count} × {per_gpu_alloc:.0f} GiB"
            f" = {gpu_alloc_gib:.0f} GiB"
        )

        # ③ GPU + CPU 总容量 ≥ 模型大小 × 1.1
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
                f"{total_cap_gib:.0f} GiB < 模型 {model_size_gib:.0f} × 1.1 = {required_cap:.0f} GiB，"
                f"请增大 --cpu-memory",
            )

        # ④ CPU 实际可用 ≥ cpu_memory_gib + 50 GiB（OS 余量）
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
                f"--cpu-memory={cpu_memory_str} 请求 {cpu_memory_gib:.0f} GiB，"
                f"当前系统可用 {cpu_avail_gib:.0f} GiB 不足，"
                f"请减小 --cpu-memory 或释放内存",
            )

    # ── 公共：输出磁盘空间 ────────────────────────────────────────
    disk_free_gib     = get_output_disk_free_gib(output_path)
    required_disk_gib = model_size_gib * 0.35   # AWQ INT4 约 BF16 的 30%，留 35% 余量
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

    # ── 总结 ─────────────────────────────────────────────────────
    print(_LINE)
    if all_pass:
        print("  ✅  预检通过，资源充足，开始量化")
    else:
        print("  ❌  预检未通过，存在资源不足项（详见上方提示），请确认后再运行")
    print(_SEP)

    return all_pass


# ══════════════════════════════════════════════════════════════════
# 校准数据集：解析 / 下载 / 混合
# ══════════════════════════════════════════════════════════════════

_NETWORK_ERR_KEYWORDS = (
    "connection", "timeout", "proxy", "cannot connect",
    "network", "ssl", "certificate", "handshake", "refused",
)


def _offline_patch():
    """
    返回 (hc, dc) 并关闭 HuggingFace 离线锁。

    huggingface_hub / datasets 各自在模块导入时将 TRANSFORMERS_OFFLINE=1
    固化为模块级常量，改环境变量已无效，必须直接 patch：
      - huggingface_hub.constants.HF_HUB_OFFLINE
      - datasets.config.HF_HUB_OFFLINE / HF_DATASETS_OFFLINE
    模型从本地路径加载，不受这两处变量影响。
    """
    import huggingface_hub.constants as _hc
    import datasets.config as _dc
    _orig_hc = _hc.HF_HUB_OFFLINE
    _orig_dc = _dc.HF_HUB_OFFLINE
    _hc.HF_HUB_OFFLINE = False
    _dc.HF_HUB_OFFLINE = False
    _dc.HF_DATASETS_OFFLINE = False
    return _hc, _dc, _orig_hc, _orig_dc


def _offline_restore(hc, dc, orig_hc, orig_dc):
    """恢复 HuggingFace 离线锁。"""
    hc.HF_HUB_OFFLINE = orig_hc
    dc.HF_HUB_OFFLINE = orig_dc
    dc.HF_DATASETS_OFFLINE = orig_dc


def parse_dataset_specs(dataset_str: str, samples_str: str) -> list[tuple[str, int]]:
    """
    将 --calib-dataset / --calib-samples 解析为 [(dataset_id, n_samples), ...] 列表。

    支持格式：
      单集：  dataset_str="cyankiwi/calibration"                    samples_str="384"
              → [("cyankiwi/calibration", 384)]

      多集（逗号分隔，样本数平均分配）：
              dataset_str="cyankiwi/calibration,HuggingFaceH4/ultrachat_200k"
              samples_str="512"
              → [("cyankiwi/calibration", 256), ("HuggingFaceH4/ultrachat_200k", 256)]

      多集（逗号分隔，样本数分别指定）：
              dataset_str="cyankiwi/calibration,HuggingFaceH4/ultrachat_200k"
              samples_str="256,256"
              → [("cyankiwi/calibration", 256), ("HuggingFaceH4/ultrachat_200k", 256)]
    """
    ids     = [s.strip() for s in dataset_str.split(",") if s.strip()]
    samples = [s.strip() for s in samples_str.split(",") if s.strip()]
    if not ids:
        raise ValueError("--calib-dataset 不能为空")

    if len(samples) == 1:
        total = int(samples[0])
        if total <= 0:
            raise ValueError("--calib-samples 必须为正整数")
        per   = total // len(ids)
        # 最后一个数据集补上余数，确保总数精确
        counts = [per] * (len(ids) - 1) + [total - per * (len(ids) - 1)]
    else:
        if len(samples) != len(ids):
            raise ValueError(
                f"--calib-samples 指定了 {len(samples)} 个值，"
                f"但 --calib-dataset 有 {len(ids)} 个数据集，数量不匹配"
            )
        counts = [int(s) for s in samples]
        if any(n <= 0 for n in counts):
            raise ValueError("--calib-samples 中每个样本数都必须为正整数")

    return list(zip(ids, counts))


def _resolve_split(ds_id: str) -> str:
    """
    自动探测数据集的训练集 split 名称。

    优先尝试 "train"；若不存在则从可用 split 中选取第一个含 "train" 的（如
    "train_sft"、"train_gen"），再不行取第一个可用 split。

    示例：
      "train"                → "train"          （多数数据集）
      "train_sft"            → "train_sft"       （HuggingFaceH4/ultrachat_200k）
    """
    try:
        from datasets import get_dataset_split_names
        splits = get_dataset_split_names(ds_id)
    except Exception:
        return "train"   # 探测失败则保持默认

    if "train" in splits:
        return "train"
    # 优先找包含 "train" 的 split
    for s in splits:
        if "train" in s:
            return s
    # 兜底：第一个可用 split
    return splits[0] if splits else "train"


def _to_text_column(ds, ds_id: str, tokenizer) -> "datasets.Dataset":
    """
    将数据集统一转换为只含 'text' 列的格式，供 oneshot 消费。

    处理规则：
      1. 若已有 'text' 列 → 直接保留
      2. 若有 'messages' 列（多轮对话格式）→ 应用 chat template 生成 'text'
      3. 其他：取第一个字符串列重命名为 'text'
    """
    cols = ds.column_names

    if "text" in cols:
        return ds.select_columns(["text"])

    if "messages" in cols:
        def _apply_template(example):
            try:
                text = tokenizer.apply_chat_template(
                    example["messages"],
                    tokenize=False,
                    add_generation_prompt=False,
                )
            except Exception:
                # 部分样本格式异常时降级为字符串拼接
                text = " ".join(
                    m.get("content", "") for m in example["messages"]
                )
            return {"text": text}
        ds = ds.map(_apply_template, remove_columns=cols)
        return ds

    def _stringify(value) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, dict):
                    parts.append(str(item.get("content") or item.get("text") or item))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        if isinstance(value, dict):
            return str(value.get("content") or value.get("text") or value)
        return str(value)

    # 兜底：不能依赖 features[c].dtype，部分数据集列是 List/Sequence 类型。
    # 直接基于样本值挑选最像文本的列，并统一序列化为 text。
    sample = ds[0] if len(ds) else {}
    preferred_cols = [
        c for c in (
            "system", "instruction", "prompt", "question", "input",
            "response", "answer", "output", "completion", "content",
        )
        if c in cols
    ]
    candidate_cols = [
        c for c in cols if isinstance(sample.get(c), (str, list, dict))
    ]
    selected_cols = preferred_cols or candidate_cols or [cols[0]]

    def _convert(example):
        parts = []
        for col in selected_cols:
            text = _stringify(example.get(col)).strip()
            if text:
                parts.append(text)
        return {"text": "\n\n".join(parts)}

    return ds.map(_convert, remove_columns=cols)


def prefetch_calib_datasets(specs: list[tuple[str, int]]) -> None:
    """
    在模型加载前预先下载并缓存所有校准数据集（快速失败策略）。

    目的：
      - 快速失败：网络 / 代理异常时立即报错，避免模型加载后才发现下载失败
      - 复用缓存：oneshot / build_calib_dataset 后续命中 HF_DATASETS_CACHE，不重复下载
      - 验证样本数：确认各数据集实际条数 ≥ 所需条数，提前发现配置问题

    specs: [(dataset_id, n_samples), ...]
    """
    from datasets import load_dataset

    cache_dir = os.environ.get("HF_DATASETS_CACHE")
    print(f"\n[校准数据集] 预下载（共 {len(specs)} 个数据集）")
    print(f"  缓存路径 : {cache_dir or '默认（容器内）'}")

    hc, dc, orig_hc, orig_dc = _offline_patch()
    try:
        for ds_id, n in specs:
            print(f"  → {ds_id!r}（需要 {n} 条）", end=" ", flush=True)
            try:
                split = _resolve_split(ds_id)
                ds = load_dataset(ds_id, split=split)
                total = len(ds)
                if total < n:
                    raise RuntimeError(
                        f"数据集 {ds_id!r} 实际只有 {total} 条，"
                        f"少于所需 {n} 条，请减小样本数"
                    )
                print(f"✅ ({total} 条，split={split!r})")
            except Exception as e:
                err_lower = str(e).lower()
                if any(kw in err_lower for kw in _NETWORK_ERR_KEYWORDS):
                    raise RuntimeError(
                        f"数据集 {ds_id!r} 下载失败（网络错误）: {e}\n"
                        "请检查：① 代理 HTTP_PROXY/HTTPS_PROXY 是否正确；"
                        "② 网络是否可达 HuggingFace Hub"
                    ) from e
                raise RuntimeError(
                    f"数据集 {ds_id!r} 预下载/校验失败: {type(e).__name__}: {e}"
                ) from e
    finally:
        _offline_restore(hc, dc, orig_hc, orig_dc)


def build_calib_dataset(specs: list[tuple[str, int]], tokenizer):
    """
    加载、采样、统一格式后混合多个校准数据集，返回单一 Dataset 对象。

    返回的 Dataset 只含 'text' 列，已打乱顺序，可直接传入 oneshot(dataset=...)。

    specs: [(dataset_id, n_samples), ...]
    """
    from datasets import load_dataset, concatenate_datasets

    print(f"\n[校准数据集] 加载并统一格式（{len(specs)} 个数据集）")

    hc, dc, orig_hc, orig_dc = _offline_patch()
    try:
        parts = []
        for ds_id, n in specs:
            split = _resolve_split(ds_id)
            print(f"  加载 {ds_id!r} (split={split!r})，取 {n} 条 ...", flush=True)
            ds = load_dataset(ds_id, split=split)
            ds = ds.shuffle(seed=42).select(range(min(n, len(ds))))
            ds = _to_text_column(ds, ds_id, tokenizer)
            ds = ds.filter(lambda x: isinstance(x.get("text"), str) and len(x["text"].strip()) > 0)
            if len(ds) == 0:
                raise RuntimeError(f"数据集 {ds_id!r} 转换为 text 后没有可用样本")
            parts.append(ds)
            print(f"    → {len(ds)} 条 ✅")
    finally:
        _offline_restore(hc, dc, orig_hc, orig_dc)

    total = sum(len(p) for p in parts)
    mixed = concatenate_datasets(parts).shuffle(seed=42) if len(parts) > 1 else parts[0]
    print(f"  数据集准备完成：{total} 条（{' + '.join(str(len(p)) for p in parts)}）")
    return mixed, total


# ══════════════════════════════════════════════════════════════════
# 模型加载
# ══════════════════════════════════════════════════════════════════

def _patch_loading_report() -> bool:
    """
    transformers 5.10.1 兼容性补丁：
    `log_state_dict_report` 对 CONVERSION 状态抛 RuntimeError，
    但 GLM-5.2（GlmMoeDsaForCausalLM）的 DSA indexer 权重是按设计
    新初始化的（非真正错误）。补丁将 CONVERSION RuntimeError 降级为 WARNING，
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
                    import logging as _log
                    _log.getLogger(__name__).warning(
                        "[GLM-5.2 兼容补丁] 权重 CONVERSION 检测到但已忽略"
                        "（DSA indexer 新初始化为预期行为）: %s", msg
                    )
                else:
                    raise

        _lr.log_state_dict_report = _patched
        print("[补丁] transformers loading_report CONVERSION 检查已降级为 WARNING", flush=True)
        return True
    except Exception as e:
        print(f"[警告] loading_report 补丁应用失败，继续加载（可能遇到 CONVERSION 错误）: {e}", flush=True)
        return False


def load_model_multi_gpu(
    model_path: str,
    gpu_count: int,
    total_vram_gib: float,
    cpu_memory_str: str,
    gpu_memory_utilization: float,
):
    """
    accelerate device_map="auto" 多卡加载：
      - 每张 GPU 预留 85% 显存（避免量化过程 OOM）
      - 剩余层 offload 到 CPU RAM
    """
    from transformers import AutoModelForCausalLM

    # ── 兼容性补丁（transformers 5.10.1 + GLM-5.2 DSA indexer）──────
    _patch_loading_report()

    # GLM-5.2 MoE gate_up_proj 在 _finalize_model_loading 时需要合并 2 个分片
    # (MergeModulelist)，每层临时峰值约 12 GiB；保留 70% 使每卡留 ~24 GiB 余量。
    # 同时依赖进程启动前设置的 expandable_segments 复用碎片化保留显存。
    reserved_gib  = total_vram_gib * gpu_memory_utilization
    per_gpu_gib   = reserved_gib / gpu_count
    max_memory: dict = {i: f"{per_gpu_gib:.0f}GiB" for i in range(gpu_count)}
    max_memory["cpu"] = cpu_memory_str

    print(f"\n[1/3] 用 device_map='auto' 加载模型（多卡模式）")
    print(
        f"  GPU 分配 : {gpu_count} × {per_gpu_gib:.0f} GiB = {reserved_gib:.0f} GiB"
        f"  ({gpu_memory_utilization:.0%}，留余量给 MoE 收尾)"
    )
    print(f"  CPU 分配 : {cpu_memory_str}")
    print(f"  PYTORCH_CUDA_ALLOC_CONF: {os.environ.get('PYTORCH_CUDA_ALLOC_CONF')}")
    print(f"  max_memory: {max_memory}")

    # torch_dtype 在 transformers 5.10.1 已废弃，使用 dtype
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
            "降到 0.60 或 0.55 后重试；若仍失败，请使用模式 A sequential offload。"
        ) from e

    device_counts: dict = {}
    for _, param in model.named_parameters():
        d = str(param.device)
        device_counts[d] = device_counts.get(d, 0) + 1
    print("  层分布（参数张量数量）:")
    for dev, cnt in sorted(device_counts.items()):
        print(f"    {dev}: {cnt} 个")
    if device_counts.get("meta", 0) > 0:
        raise RuntimeError(
            f"模型加载后仍有 {device_counts['meta']} 个 meta 参数。"
            "这通常表示 transformers 多卡转换/合并未完整 materialize 权重，"
            "继续 AWQ 会在前向阶段失败。请降低 --gpu-memory-utilization 后重试，"
            "或使用模式 A sequential offload。"
        )

    return model


# ══════════════════════════════════════════════════════════════════
# 量化执行（按模式封装）
# ══════════════════════════════════════════════════════════════════

def run_mode_a(args, tokenizer, recipe, dataset_specs):
    """模式 A：单卡 sequential offload。"""
    print(f"\n[模式 A] 单卡 sequential offload")
    print(f"  offload  : {args.offload_device}")
    print(f"  scheme   : {args.scheme}")
    spec_desc = " + ".join(f"{ds_id}({n}条)" for ds_id, n in dataset_specs)
    print(f"  校准数据 : {spec_desc}（max_seq={args.max_seq_length}）")
    print(f"  预计耗时 : ~4~12 小时（逐层 PCIe 传输，瓶颈在 I/O）")

    from llmcompressor import oneshot

    offload = args.offload_device if args.offload_device != "none" else None

    # 单集：直接传字符串给 oneshot（内部处理更高效）
    # 多集：预先混合为 Dataset 对象再传入
    dataset, total_samples = build_calib_dataset(dataset_specs, tokenizer)

    oneshot(
        model=args.model_path,             # 字符串路径，内部按序加载各层
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


def run_mode_b(args, gpu_count: int, total_vram_gib: float, tokenizer, recipe,
               dataset_specs):
    """模式 B：多卡 device_map + CPU offload。"""
    print(f"\n[模式 B] 多卡 device_map + CPU offload")
    print(f"  scheme   : {args.scheme}")
    spec_desc = " + ".join(f"{ds_id}({n}条)" for ds_id, n in dataset_specs)
    print(f"  校准数据 : {spec_desc}（max_seq={args.max_seq_length}）")
    print(f"  预计耗时 : ~2~6 小时（{gpu_count} 卡并行校准，H100 NVLink 带宽优势）")

    from llmcompressor import oneshot

    model = load_model_multi_gpu(
        args.model_path, gpu_count, total_vram_gib, args.cpu_memory,
        args.gpu_memory_utilization
    )

    # 单集：直接传字符串给 oneshot（内部处理更高效）
    # 多集：预先混合为 Dataset 对象再传入
    dataset, total_samples = build_calib_dataset(dataset_specs, tokenizer)

    print(f"\n[2/3] 开始 AWQ 量化（pipeline=independent，多卡前向）...")
    oneshot(
        model=model,                       # 传已加载的模型对象
        tokenizer=tokenizer,
        recipe=recipe,
        dataset=dataset,
        num_calibration_samples=total_samples,
        max_seq_length=args.max_seq_length,
        pipeline="independent",            # multi-GPU device_map 须用 independent，充分利用多卡并行
        moe_calibrate_all_experts=True,
        output_dir=args.output_path,
        save_compressed=True,
    )
    print(f"[3/3] 量化完成，结果已保存至 {args.output_path}")


# ══════════════════════════════════════════════════════════════════
# 参数解析 & 入口
# ══════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="GLM-5.2 AWQ-INT4 量化（llmcompressor，单卡 sequential offload 或多卡 device_map）"
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
            "启用多卡模式：accelerate device_map='auto' 将模型分布到所有可见 GPU + CPU RAM，"
            "校准前向传播可利用所有 GPU（需 GPU × 显存 + CPU RAM ≥ 模型大小）"
        ),
    )
    parser.add_argument(
        "--cpu-memory", type=str, default="auto",
        help=(
            "多卡模式下分配给 CPU RAM 的 offload 容量。\n"
            "  auto（默认）：自动取系统当前可用内存的 80%%\n"
            "  固定值示例：1100GiB / 960GB"
        ),
    )
    parser.add_argument(
        "--gpu-memory-utilization", type=float, default=0.70,
        help=(
            "多卡模式下每张 GPU 允许给 device_map 使用的显存比例。"
            "默认 0.70，为 GLM-5.2 MoE gate/up 合并和 AWQ 校准预留显存；"
            "如仍 OOM 可降至 0.60 或 0.55。"
        ),
    )
    parser.add_argument(
        "--calib-dataset", type=str,
        default="cyankiwi/calibration,HuggingFaceH4/ultrachat_200k",
        help=(
            "校准数据集，支持单集或逗号分隔多集混合：\n"
            "  单集  : cyankiwi/calibration\n"
            "  多集  : cyankiwi/calibration,HuggingFaceH4/ultrachat_200k\n"
            "默认混合：cyankiwi/calibration(中英代码推理) + ultrachat_200k(英文对话)\n"
            "其他可选：garage-bAInd/Open-Platypus, princeton-nlp/SWE-bench_Verified"
        ),
    )
    parser.add_argument(
        "--calib-samples", type=str, default="256,256",
        help=(
            "各数据集的采样数，支持：\n"
            "  总数（平均分配）: 512\n"
            "  逐集指定（与 --calib-dataset 一一对应）: 256,256\n"
            "默认 256+256=512 条（GLM-5.2 推荐配方）"
        ),
    )
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
    parser.add_argument(
        "--skip-resource-check", action="store_true",
        help="跳过启动前资源预检（不推荐，仅用于调试）",
    )
    parser.add_argument(
        "--log-dir", type=str, default=None,
        help="日志目录。默认: 当前脚本所在目录下的 logs/",
    )
    parser.add_argument(
        "--no-fallback-to-mode-a", action="store_true",
        help="多卡模式 B 失败时不自动回退到模式 A。默认会自动回退，提高长任务完成概率。",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("未检测到 CUDA GPU，量化需要 GPU 环境")

    gpu_count = torch.cuda.device_count()
    phys_ids  = args.gpus.split(",") if args.gpus else None
    total_vram_gib, per_gpu_vram_gib = get_gpu_info(gpu_count, phys_ids)

    # 判断实际运行模式
    use_multi_gpu = args.multi_gpu and gpu_count > 1
    if args.multi_gpu and gpu_count <= 1:
        print(f"[警告] --multi-gpu 已指定但只有 {gpu_count} 张卡，回退到单卡模式 A")
    mode = "B" if use_multi_gpu else "A"
    if use_multi_gpu and not (0.30 <= args.gpu_memory_utilization <= 0.90):
        raise ValueError("--gpu-memory-utilization 建议范围为 0.30~0.90")

    # ── 初始化日志（越早越好，从此之后 stdout/stderr 全部落盘）────────
    mode_tag = f"mode_{'b' if use_multi_gpu else 'a'}"
    log_path = setup_logging(args.log_dir, mode_tag, args.model_path)
    print(f"[日志] 模式: {mode}  日志文件: {log_path}", flush=True)

    # 解析 cpu_memory（"auto" → 可用内存 × 80%），统一后续所有调用
    if use_multi_gpu:
        args.cpu_memory = resolve_cpu_memory_str(args.cpu_memory)

    # ── 解析数据集规格 ──────────────────────────────────────────────
    dataset_specs = parse_dataset_specs(args.calib_dataset, args.calib_samples)
    total_samples = sum(n for _, n in dataset_specs)
    print(f"\n[数据集配方]")
    for ds_id, n in dataset_specs:
        print(f"  {ds_id!r}  {n} 条")
    print(f"  合计 {total_samples} 条，max_seq_length={args.max_seq_length}")

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
        )
        if not ok:
            sys.exit(1)
    else:
        print("[警告] 已跳过资源预检（--skip-resource-check）")

    os.makedirs(args.output_path, exist_ok=True)

    # ── 预下载校准数据集（快速失败，避免模型加载后才发现网络异常）────
    prefetch_calib_datasets(dataset_specs)

    # ── 加载公共依赖 ──────────────────────────────────────────────
    from transformers import AutoTokenizer
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
        print(f"  回退策略 : {fallback_status}（模式 B 失败时切换到模式 A sequential offload）")
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
                       dataset_specs)
        except Exception as e:
            fallback_reason = f"{type(e).__name__}: {e}"
            if args.no_fallback_to_mode_a:
                print(f"\n{_SEP}")
                print("  模式切换")
                print(_SEP)
                print("  模式 B 失败，且 --no-fallback-to-mode-a 已启用")
                print("  结果   : 不回退，直接终止")
                print(f"  原因   : {fallback_reason}")
                print(_SEP)
                raise
            logging.exception("模式 B 失败，准备自动切换到模式 A")
            print(f"\n{_SEP}")
            print("  模式切换")
            print(_SEP)
            print("  源模式 : B（多卡 device_map + CPU offload）")
            print("  目标模式: A（单卡 sequential offload）")
            print(f"  原因   : {fallback_reason}")
            print("  动作   : 退出异常栈、释放 GPU 缓存后继续执行，输出目录保持不变")
            print(f"  输出目录: {args.output_path}")
            print(_SEP, flush=True)
            fallback_to_mode_a = True
        if fallback_to_mode_a:
            print("\n[回退清理] 释放模式 B 残留资源 ...", flush=True)
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
                print("  GPU 缓存已清理，开始模式 A", flush=True)
            completed_mode = "A"
            run_mode_a(args, tokenizer, recipe, dataset_specs)
    else:
        run_mode_a(args, tokenizer, recipe, dataset_specs)

    print(f"\n✅ AWQ 量化完成！")
    print(f"   实际完成模式: {completed_mode}")
    print(f"   输出目录: {args.output_path}")
    print(f"   vllm serve {args.output_path} --quantization awq_marlin --tensor-parallel-size 8")


if __name__ == "__main__":
    main()
