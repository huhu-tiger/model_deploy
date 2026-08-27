#!/usr/bin/env python3
"""过滤 evalscope 终端里的表格/图表提示；可选打印一行指标摘要。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_BOX = re.compile(r"[\u2500-\u257F]")
_DROP = (
    "benchmarking summary",
    "percentile results",
    "performance test summary",
    "workload throughput",
    "html report generated",
    "swanlab:",
    "basic information",
    "performance overview",
    "per-request metrics",
    "performance summary saved",
    "metric                     ",
    "visualizer swanlab",
)


def keep_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    lower = stripped.lower()
    if any(token in lower for token in _DROP):
        return False
    if _BOX.search(stripped):
        return False
    return True


def filter_stream() -> int:
    for line in sys.stdin:
        if keep_line(line):
            sys.stdout.write(line)
            sys.stdout.flush()
    return 0


def _first_summary(run_dir: Path) -> dict | None:
    matches = sorted(run_dir.rglob("benchmark_summary.json"))
    if not matches:
        return None
    try:
        return json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _pick(data: dict, *keys: str) -> str:
    for key in keys:
        if key in data and data[key] is not None:
            return str(data[key])
    return "-"


def print_compact_summary(run_dir: str) -> int:
    data = _first_summary(Path(run_dir))
    if not data:
        return 0
    ttft = _pick(data, "TTFT (ms)", "Average time to first token (s)")
    latency = _pick(data, "Avg Latency (s)", "Average latency (s)")
    out_tps = _pick(data, "Output Throughput (tok/s)", "Output token throughput (tok/s)")
    success = _pick(data, "Success Requests", "Succeed requests")
    failed = _pick(data, "Failed Requests")
    print(
        f"metrics  latency={latency}s  ttft={ttft}ms  out_tok/s={out_tps}  succ/fail={success}/{failed}",
        flush=True,
    )
    return 0


def _main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "summary":
        return print_compact_summary(sys.argv[2])
    return filter_stream()


if __name__ == "__main__":
    raise SystemExit(_main())
