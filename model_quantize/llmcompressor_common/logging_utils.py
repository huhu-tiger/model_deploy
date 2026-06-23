"""
Tee 日志工具: 将 stdout / stderr 同时写入终端和日志文件。

捕获 print() / transformers logging.warning() 等所有输出,便于事后追查。
"""

from __future__ import annotations

import datetime
import logging
import os
import sys


class _Tee:
    """
    将 stdout / stderr 同时写入终端和日志文件,不依赖 fileno()。
    捕获所有 print()、transformers logger.warning() 等输出。
    """
    def __init__(self, stream, logfile):
        self._stream = stream
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


_tee_log_fh = None  # 全局引用,防止 GC 关闭文件句柄


def _sanitize_filename_part(value: str) -> str:
    """将模型名等文本转换为适合文件名的片段。"""
    safe = []
    for ch in value:
        if ch.isalnum() or ch in ("-", "_", "."):
            safe.append(ch)
        else:
            safe.append("-")
    return "".join(safe).strip("-") or "model"


def default_log_dir(caller_file: str | None = None) -> str:
    """默认日志目录: 调用方脚本所在目录下的 logs/。"""
    if caller_file:
        base = os.path.dirname(os.path.abspath(caller_file))
    else:
        base = os.getcwd()
    return os.path.join(base, "logs")


def setup_logging(
    log_dir: str | None = None,
    mode_tag: str = "quant",
    model_path: str = "model",
    caller_file: str | None = None,
) -> str:
    """
    初始化日志系统。

    做法:
      1. 将 sys.stdout / sys.stderr 替换为 _Tee → 捕获所有 print() 输出
      2. 为 root logger 添加 FileHandler（WARNING 级别） → 捕获 transformers 警告
      3. transformers logging 显式设为 WARNING（已被 Tee 捕获）

    参数:
      log_dir    : 日志目录;未指定时用 default_log_dir(caller_file)
      mode_tag   : 日志文件名前缀标签（如 mode_a / mode_b）
      model_path : 模型路径,其目录名用于生成日志文件名
      caller_file: 调用方 __file__,用于推导默认日志目录

    返回: 日志文件绝对路径
    """
    global _tee_log_fh
    if not log_dir:
        log_dir = default_log_dir(caller_file)
    os.makedirs(log_dir, exist_ok=True)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    model_name = _sanitize_filename_part(
        os.path.basename(os.path.abspath(model_path.rstrip("/")))
    )
    log_path = os.path.join(log_dir, f"{ts}_{model_name}_{mode_tag}.log")

    # 行缓冲,实时刷新
    _tee_log_fh = open(log_path, "w", encoding="utf-8", buffering=1)

    sys.stdout = _Tee(sys.__stdout__, _tee_log_fh)
    sys.stderr = _Tee(sys.__stderr__, _tee_log_fh)

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

    try:
        import transformers as _tf
        _tf.logging.set_verbosity_warning()
    except Exception:
        pass

    print(f"[日志] 写入路径: {log_path}", flush=True)
    return log_path
