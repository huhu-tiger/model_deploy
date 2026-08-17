#!/usr/bin/env python3
"""按配置生成长上下文 prompt：shared=缓存命中，unique=缓存不命中。"""

from __future__ import annotations

import argparse
import hashlib
import time
from pathlib import Path

try:
    from .config import enabled_modes, load_content_config
except ImportError:
    from config import enabled_modes, load_content_config

_STAMP = "壹贰叁肆伍陆柒捌玖零甲乙丙丁戊己庚辛"


def _unique_head(index: int, n_chars: int, salt: str = "") -> str:
    """每条开头一段不同的汉字，打断 prefix cache，且保持约 1 字 ≈ 1 token。"""
    digest = hashlib.sha1(f"ctx-bench-{salt}-{index}".encode("utf-8")).hexdigest()
    chars: list[str] = []
    seed = digest
    while len(chars) < n_chars:
        for ch in seed:
            chars.append(_STAMP[int(ch, 16) % len(_STAMP)])
            if len(chars) >= n_chars:
                break
        seed = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return "".join(chars[:n_chars])


def _unique_tail(index: int, n_chars: int) -> str:
    raw = f"尾{index:06d}{hashlib.sha1(str(index).encode()).hexdigest()}"
    raw = raw.replace("\n", " ")
    if len(raw) < n_chars:
        raw = raw + "尾" * n_chars
    return raw[:n_chars]


def _repeat_to(text: str, n: int) -> str:
    text = (text or "测").replace("\n", " ").replace("\r", " ")
    if not text:
        text = "测"
    return (text * ((n + len(text) - 1) // len(text)))[:n]


def _fill_body(n_chars: int, cfg: dict) -> str:
    """循环铺满正文，不含打戳。prefix_file / fill_text 只读一次。"""
    if n_chars <= 0:
        return ""
    config_dir = Path(cfg.get("_config_dir") or ".")
    prefix_file = str(cfg.get("prefix_file") or "").strip()
    if prefix_file:
        path = Path(prefix_file)
        if not path.is_absolute():
            path = config_dir / path
        return _repeat_to(path.read_text(encoding="utf-8"), n_chars)
    fill_text = str(cfg.get("fill_text") or "").strip()
    if fill_text:
        return _repeat_to(fill_text, n_chars)
    fill_char = (str(cfg.get("fill_char") or "测")[:1] or "测")
    return fill_char * n_chars


def _stamp_body(body: str, index: int, interval: int) -> str:
    if not body:
        return body
    chars = list(body)
    step = max(interval, 1)
    n_stamp = len(_STAMP)
    for pos in range(0, len(chars), step):
        chars[pos] = _STAMP[(index + pos) % n_stamp]
    return "".join(chars)


def write_filler_prompts(
    path: str | Path,
    n_chars: int,
    n_req: int,
    config: str | Path | None = None,
    mode: str = "cache_miss",
) -> Path:
    """兼容入口：按配置生成 prompt，默认 cache_miss（不命中）。"""
    cfg = load_content_config(config)
    modes = {m["id"]: m for m in enabled_modes(cfg)}
    spec = modes.get(mode) or {"id": mode, "prefix": "unique", "warmup": 0}
    return write_prompts(path, n_chars, n_req, spec, cfg)


def write_prompts(
    path: str | Path,
    n_chars: int,
    n_req: int,
    mode: dict,
    cfg: dict,
) -> Path:
    """line_by_line：每行一条、无行内换行。

    prefix=unique：每条开头不同，预期 prefix cache 不命中。
    prefix=shared：长前缀相同、仅尾部少量不同，预期命中（建议 warmup>=1）。
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    suffix = str(
        cfg.get("suffix")
        or "【任务】从1开始连续输出整数，每个数字单独一行，不要解释，不要停，一直输出到上限。"
    ).replace("\n", " ").strip()
    instruction = f" {suffix} "
    policy = str(mode.get("prefix") or "unique")
    tail_n = max(8, int(cfg.get("unique_tail_chars") or 24))
    head_n = max(32, int(cfg.get("unique_head_chars") or 256))
    run_salt = f"{n_chars}-{time.time_ns()}"

    with out.open("w", encoding="utf-8") as fh:
        if policy == "shared":
            body_len = max(16, n_chars - len(instruction) * 2 - tail_n)
            shared = _fill_body(body_len, cfg)
            for i in range(n_req):
                fh.write(f"{instruction}{shared}{_unique_tail(i, tail_n)}{instruction}\n")
        else:
            body_len = max(16, n_chars - head_n - len(instruction) * 2)
            base = _fill_body(body_len, cfg)
            interval = int(cfg.get("stamp_interval") or 256)
            for i in range(n_req):
                fh.write(
                    f"{_unique_head(i, head_n, run_salt)}"
                    f"{instruction}"
                    f"{_stamp_body(base, i, interval)}"
                    f"{instruction}\n"
                )
    return out


def _default_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "content.json"


def _main() -> int:
    parser = argparse.ArgumentParser(description="按 content.json 生成 prompt")
    parser.add_argument("--path", required=True)
    parser.add_argument("--n-chars", type=int, required=True)
    parser.add_argument("--n-req", type=int, required=True)
    parser.add_argument("--config", default="", help="默认 config/content.json")
    parser.add_argument("--mode", default="cache_miss", help="cache_miss / cache_hit")
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    cfg_path = Path(args.config) if args.config else _default_config_path()
    cfg = load_content_config(cfg_path if cfg_path.exists() else None)
    modes = {m["id"]: m for m in enabled_modes(cfg, args.only)}
    if args.mode not in modes:
        raise SystemExit(f"未知或未启用模式: {args.mode}")
    path = write_prompts(args.path, args.n_chars, args.n_req, modes[args.mode], cfg)
    print(f"wrote {args.n_req} prompts mode={args.mode} prefix={modes[args.mode].get('prefix')} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
