#!/usr/bin/env python3
"""读取测试上下文配置（正文、前缀策略、命中/不命中模式）。"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "fill_char": "测",
    "fill_text": "",
    "prefix_file": "",
    "suffix": "【任务】从1开始连续输出整数，每个数字单独一行，不要解释，不要停，一直输出到上限。",
    "unique_head_chars": 256,
    "unique_tail_chars": 24,
    "stamp_interval": 256,
    "max_tokens": 256,
    "reserve_tokens": 512,
    "min_context_k": 8,
    "context_fractions": [1.0, 0.75, 0.5, 0.25, 0.125],
    "context_levels": "",
    "parallel": 2,
    "parallel_max": 16,
    "number_mult": 2,
    "number_max": 16,
    "chart_colors": {
        "cold_ttft": "#1d4ed8",
        "cold_latency": "#93c5fd",
        "hot_ttft": "#15803d",
        "hot_latency": "#86efac"
    },
    "modes": [
        {"id": "cache_miss", "label": "不命中", "prefix": "unique", "warmup": 0, "enabled": True},
        {"id": "cache_hit", "label": "命中", "prefix": "shared", "warmup": 1, "enabled": False},
    ],
}


def load_content_config(path: str | Path | None) -> dict[str, Any]:
    cfg = deepcopy(DEFAULTS)
    if not path:
        return cfg
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"找不到内容配置: {src}")
    loaded = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("配置文件必须是 JSON object")
    cfg.update({k: v for k, v in loaded.items() if k != "modes"})
    if isinstance(loaded.get("modes"), list) and loaded["modes"]:
        cfg["modes"] = loaded["modes"]
    cfg["_config_dir"] = str(src.parent.resolve())
    cfg["_config_path"] = str(src.resolve())
    return cfg


def enabled_modes(cfg: dict[str, Any], only: str = "") -> list[dict[str, Any]]:
    wanted = {x.strip() for x in only.split(",") if x.strip()}
    out: list[dict[str, Any]] = []
    for mode in cfg.get("modes") or []:
        mid = str(mode.get("id") or "").strip()
        if not mid:
            continue
        prefix = str(mode.get("prefix") or "").strip()
        if prefix not in ("unique", "shared"):
            raise ValueError(f"模式 {mid} 的 prefix 必须是 unique 或 shared，当前: {prefix!r}")
        if not mode.get("enabled", True):
            continue
        if wanted and mid not in wanted:
            continue
        out.append(mode)
    if wanted:
        found = {str(m.get("id")) for m in out}
        missing = wanted - found
        if missing:
            raise ValueError(f"未知或未启用的前缀模式: {','.join(sorted(missing))}")
    if not out:
        if wanted:
            raise ValueError(f"没有匹配的前缀模式: {','.join(sorted(wanted))}")
        raise ValueError("没有启用的前缀模式（检查 config/content.json 的 modes）")
    return out


def format_config_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ",".join(str(x) for x in value)
    return str(value)


def mode_warmup(mode: dict[str, Any]) -> int:
    try:
        return max(0, int(mode.get("warmup") or 0))
    except (TypeError, ValueError):
        return 0


def _main() -> int:
    parser = argparse.ArgumentParser(description="读取 content.json")
    parser.add_argument("--config", required=True)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_m = sub.add_parser("modes")
    p_m.add_argument("--only", default="")
    p_w = sub.add_parser("warmup")
    p_w.add_argument("--mode", required=True)
    p_w.add_argument("--only", default="")
    p_g = sub.add_parser("get")
    p_g.add_argument("key")
    args = parser.parse_args()
    cfg = load_content_config(args.config)
    if args.cmd == "get":
        if args.key not in cfg:
            raise SystemExit(f"未知配置项: {args.key}")
        print(format_config_value(cfg[args.key]))
        return 0
    modes = enabled_modes(cfg, getattr(args, "only", "") or "")
    if args.cmd == "modes":
        print(",".join(str(m["id"]) for m in modes))
        return 0
    for mode in modes:
        if mode["id"] == args.mode:
            print(mode_warmup(mode))
            return 0
    raise SystemExit(f"未知模式: {args.mode}")


if __name__ == "__main__":
    raise SystemExit(_main())
