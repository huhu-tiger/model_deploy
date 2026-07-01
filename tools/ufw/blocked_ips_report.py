#!/usr/bin/env python3
"""Format DOCKER-USER DROP log lines as summary tables."""

from __future__ import annotations

import re
import sys
import unicodedata
from collections import Counter

SRC_RE = re.compile(r"SRC=([0-9a-fA-F:.]+)")
DPT_RE = re.compile(r"DPT=(\d+)")


def display_width(text: str) -> int:
    width = 0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ("F", "W"):
            width += 2
        else:
            width += 1
    return width


def pad_cell(text: str, width: int) -> str:
    return text + " " * max(0, width - display_width(text))


def print_table(title: str, headers: list[str], rows: list[list[str]]) -> None:
    widths = [display_width(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], display_width(cell))

    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"

    def fmt_row(cells: list[str]) -> str:
        return "| " + " | ".join(pad_cell(c, widths[i]) for i, c in enumerate(cells)) + " |"

    print(title)
    print(sep)
    print(fmt_row(headers))
    print(sep)
    for row in rows:
        print(fmt_row(row))
    print(sep)
    print()


def pct(count: int, total: int) -> str:
    if total <= 0:
        return "0.0%"
    return f"{100.0 * count / total:.1f}%"


def main() -> int:
    logs = [line for line in sys.stdin.read().splitlines() if line.strip()]
    total = len(logs)
    if total == 0:
        print("（无拦截记录）")
        return 0

    ip_counts = Counter()
    port_counts = Counter()
    for line in logs:
        src = SRC_RE.search(line)
        dpt = DPT_RE.search(line)
        if src:
            ip_counts[src.group(1)] += 1
        if dpt:
            port_counts[dpt.group(1)] += 1

    ip_rows: list[list[str]] = []
    for rank, (ip, count) in enumerate(ip_counts.most_common(), start=1):
        ip_rows.append([str(rank), ip, str(count), pct(count, total)])

    port_rows: list[list[str]] = []
    for port, count in port_counts.most_common():
        port_rows.append([port, str(count), pct(count, total)])

    summary_rows = [
        ["拦截条数", str(total)],
        ["独立 IP 数", str(len(ip_counts))],
        ["独立端口数", str(len(port_counts))],
    ]

    print_table(
        "=== DOCKER-USER 拦截 IP 统计（按次数降序）===",
        ["排名", "IP", "次数", "占比"],
        ip_rows,
    )
    print_table(
        "=== 按目标端口统计 ===",
        ["端口", "次数", "占比"],
        port_rows,
    )
    print_table("=== 拦截总计 ===", ["项目", "数值"], summary_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
