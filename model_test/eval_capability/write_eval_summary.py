#!/usr/bin/env python3
"""从 evalscope reports 生成 Markdown 格式总结 eval_summary.md（放在 run 目录根）。"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from datetime import datetime

import pandas as pd
from tabulate import tabulate

from dataset_registry import format_capability_note, lookup_dataset
from evalscope.api.messages.perf_metrics import PerfSummary
from evalscope.report.combinator import get_data_frame, get_report_list


def resolve_outputs_dir(work_dir: str) -> str:
    """解析 evalscope 实际输出目录（支持 parent 目录或直接含 reports/ 的 run 目录）。"""
    work_dir = os.path.abspath(work_dir)
    if os.path.isdir(os.path.join(work_dir, "reports")):
        return work_dir

    candidates = [
        entry
        for entry in glob.glob(os.path.join(work_dir, "*"))
        if os.path.isdir(entry) and os.path.isdir(os.path.join(entry, "reports"))
    ]
    if not candidates:
        raise FileNotFoundError(f"未找到 reports 目录: {work_dir}")

    return max(candidates, key=os.path.getmtime)


def _score_table_md(reports_dir: str) -> str:
    """评测得分表（Markdown pipe 格式），含能力维度和说明列。"""
    report_list = get_report_list([reports_dir])
    if not report_list:
        raise ValueError(f"reports 目录无有效 JSON: {reports_dir}")

    table = get_data_frame(report_list, add_overall_metric=True)
    dimensions: list[str] = []
    notes: list[str] = []
    for _, row in table.iterrows():
        subset = str(row["Subset"]) if "Subset" in table.columns else ""
        dim, note = format_capability_note(str(row["Dataset"]), str(row["Metric"]), subset)
        dimensions.append(dim)
        notes.append(note)

    table["能力维度"] = dimensions
    table["能力说明"] = notes

    # 列排序：Model / Dataset / 能力维度 / 能力说明 / Metric / Subset / Num / Score [/ Cat.0]
    preferred = ["Model", "Dataset", "能力维度", "能力说明", "Metric", "Subset", "Num", "Score"]
    cols = list(table.columns)
    if "Cat.0" in cols:
        preferred.append("Cat.0")
    ordered = [c for c in preferred if c in cols]
    ordered.extend(c for c in cols if c not in ordered)
    table = table[ordered]

    # Score 百分比格式（便于阅读）
    if "Score" in table.columns:
        table = table.copy()
        table["Score"] = table["Score"].apply(
            lambda v: f"{v:.2%}" if isinstance(v, float) and 0 <= v <= 1 else str(v)
        )

    return tabulate(table, headers=table.columns, tablefmt="pipe", showindex=False)


def _perf_table_md(reports_dir: str) -> str | None:
    """推理性能表（Markdown pipe 格式）。"""
    report_list = get_report_list([reports_dir])
    rows = []
    for report in sorted(report_list, key=lambda r: r.dataset_name):
        perf = report.perf_metrics
        if not perf:
            continue
        summary = perf.get("summary", {})
        if not summary:
            continue
        ps = PerfSummary.from_dict(summary)
        rows.append({
            "Model":          report.model_name,
            "Dataset":        report.dataset_name,
            "Num":            ps.n_samples,
            "Avg Lat (s)":    round(ps.avg_latency, 3),
            "Avg TTFT (ms)":  round(ps.avg_ttft * 1000, 1) if ps.avg_ttft is not None else "-",
            "Avg TPOT (ms)":  round(ps.avg_tpot * 1000, 1) if ps.avg_tpot is not None else "-",
            "Avg Thpt (tok/s)": ps.avg_output_tps,
            "Avg In Tok":     ps.avg_input_tokens,
            "Avg Out Tok":    ps.avg_output_tokens,
        })
    if not rows:
        return None
    df = pd.DataFrame(rows)
    return tabulate(df, headers=df.columns, tablefmt="pipe", showindex=False)


def _dataset_overview_md(reports_dir: str) -> list[str]:
    """本次 run 涉及的数据集概览（Markdown 列表）。"""
    report_list = get_report_list([reports_dir])
    seen: set[str] = set()
    rows = []
    for report in sorted(report_list, key=lambda r: r.dataset_name):
        if report.dataset_name in seen:
            continue
        seen.add(report.dataset_name)
        info = lookup_dataset(report.dataset_name)
        rows.append({
            "Dataset":  report.dataset_name,
            "能力维度": info["dimension"],
            "能力说明": info["capability"],
        })
    if not rows:
        return []
    df = pd.DataFrame(rows)
    return [tabulate(df, headers=df.columns, tablefmt="pipe", showindex=False)]


def write_summary(work_dir: str, *, quiet: bool = False) -> str:
    outputs_dir = resolve_outputs_dir(work_dir)
    reports_dir = os.path.join(outputs_dir, "reports")

    # 输出到 run 目录根，不放在 logs/
    summary_path = os.path.join(outputs_dir, "eval_summary.md")

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = [
        f"# EvalScope Summary",
        f"",
        f"- **时间**: {ts}",
        f"- **目录**: `{outputs_dir}`",
        f"",
    ]

    # 数据集概览
    try:
        overview = _dataset_overview_md(reports_dir)
        if overview:
            lines += ["## 数据集概览", ""] + overview + [""]
    except Exception as exc:
        lines += [f"## 数据集概览\n\n> ⚠ 生成失败: {exc}\n"]

    # 评测得分
    try:
        lines += ["## 评测得分", "", _score_table_md(reports_dir), ""]
    except Exception as exc:
        lines += [f"## 评测得分\n\n> ⚠ 生成失败: {exc}\n"]

    # 推理性能
    try:
        perf_md = _perf_table_md(reports_dir)
        if perf_md:
            lines += ["## 推理性能", "", perf_md, ""]
    except Exception as exc:
        lines += [f"## 推理性能\n\n> ⚠ 生成失败: {exc}\n"]

    content = "\n".join(lines).rstrip() + "\n"
    with open(summary_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    if not quiet:
        print(content, end="")
        print(f"Summary written: {summary_path}", file=sys.stderr)

    return summary_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Write Markdown eval summary from evalscope reports.")
    parser.add_argument("work_dir", help="evalscope --work-dir（父目录或实际 run 目录）")
    parser.add_argument("-q", "--quiet", action="store_true", help="不打印内容到 stdout")
    args = parser.parse_args()
    write_summary(args.work_dir, quiet=args.quiet)


if __name__ == "__main__":
    main()
