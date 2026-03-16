#!/usr/bin/env python3
"""
对已有压测结果目录生成 HTML 可视化报告，支持 SLA 模式和普通模式。
SLA 模式下，同一并发的多个 run 取平均值后再生成报告。

用法:
    python gen_report.py                          # 自动找最新结果
    python gen_report.py outputs/20260316_110205/deepseek-v3.2
"""

import os
import sys
import re
import json
import glob
import shutil
import sqlite3
import tempfile
from collections import defaultdict
from typing import Dict, List


def find_latest_output():
    dirs = sorted(glob.glob("./outputs/*/*"), key=os.path.getmtime, reverse=True)
    for d in dirs:
        if os.path.isdir(d) and os.listdir(d):
            return d
    return None


def avg_dict(dicts: List[dict]) -> dict:
    """对一组 dict 的数值字段取平均，非数值字段取第一个。"""
    result = {}
    for key in dicts[0]:
        vals = [d[key] for d in dicts if key in d]
        if all(isinstance(v, (int, float)) for v in vals):
            result[key] = sum(vals) / len(vals)
        else:
            result[key] = vals[0]
    return result


def avg_percentiles(pct_list: List[List[dict]]) -> List[dict]:
    """
    对多个 benchmark_percentile.json 取平均。
    格式: [{"Percentiles": "10%", "TTFT (s)": 0.17, ...}, ...]
    """
    if not pct_list:
        return []
    n_rows = len(pct_list[0])
    result = []
    for i in range(n_rows):
        rows = [p[i] for p in pct_list]
        row = {}
        for key in rows[0]:
            vals = [r[key] for r in rows]
            if all(isinstance(v, (int, float)) for v in vals):
                row[key] = sum(vals) / len(vals)
            else:
                row[key] = vals[0]  # Percentiles 标签等非数值字段
        result.append(row)
    return result


def merge_runs_for_parallel(run_dirs: List[str]) -> dict:
    """读取多个 run 目录，返回平均后的 summary 和 percentiles。"""
    summaries, percentiles = [], []
    for d in run_dirs:
        s_path = os.path.join(d, "benchmark_summary.json")
        p_path = os.path.join(d, "benchmark_percentile.json")
        if os.path.exists(s_path):
            with open(s_path) as f:
                summaries.append(json.load(f))
        if os.path.exists(p_path):
            with open(p_path) as f:
                percentiles.append(json.load(f))

    return {
        "summary": avg_dict(summaries) if summaries else {},
        "percentiles": avg_percentiles(percentiles) if percentiles else {},
        "args": json.load(open(os.path.join(run_dirs[0], "benchmark_args.json")))
                if os.path.exists(os.path.join(run_dirs[0], "benchmark_args.json")) else {},
    }


def prepare_staging(output_dir: str) -> str:
    """
    普通模式直接返回 output_dir。
    SLA 模式：按并发分组，对所有 run 取平均，写入 staging 目录。
    """
    # 普通模式
    has_parallel = any(
        e.startswith("parallel_") and os.path.isdir(os.path.join(output_dir, e))
        for e in os.listdir(output_dir)
    )
    if has_parallel:
        return output_dir

    sla_dir = os.path.join(output_dir, "sla_tuning")
    if not os.path.isdir(sla_dir):
        return output_dir

    staging = os.path.join(output_dir, "_report_staging")
    if os.path.exists(staging):
        shutil.rmtree(staging)
    os.makedirs(staging)

    # 按并发分组
    groups: Dict[int, List[str]] = defaultdict(list)
    pattern = re.compile(r"sla_parallel_(\d+)_run_(\d+)")
    for entry in sorted(os.listdir(sla_dir)):
        m = pattern.match(entry)
        if m:
            parallel = int(m.group(1))
            groups[parallel].append(os.path.join(sla_dir, entry))

    real_args = {}
    for parallel, run_dirs in sorted(groups.items()):
        print(f"  parallel={parallel}: 合并 {len(run_dirs)} 个 run 取平均")
        merged = merge_runs_for_parallel(run_dirs)

        if not real_args and merged["args"]:
            real_args = merged["args"]

        number = int(merged["summary"].get("Total requests", 0))
        dst_name = f"parallel_{parallel}_number_{number}"
        dst = os.path.join(staging, dst_name)
        os.makedirs(dst)

        with open(os.path.join(dst, "benchmark_summary.json"), "w") as f:
            json.dump(merged["summary"], f, indent=2)
        with open(os.path.join(dst, "benchmark_percentile.json"), "w") as f:
            json.dump(merged["percentiles"], f, indent=2)
        with open(os.path.join(dst, "benchmark_args.json"), "w") as f:
            json.dump(merged["args"], f, indent=2)

    # 保存 real_args 供外部读取
    if real_args:
        with open(os.path.join(staging, "_args.json"), "w") as f:
            json.dump(real_args, f)

    return staging


# ── 主流程 ────────────────────────────────────────────────────────────────────
output_dir = sys.argv[1] if len(sys.argv) > 1 else find_latest_output()

if not output_dir:
    print("未找到压测结果目录，请指定路径")
    sys.exit(1)

output_dir = os.path.abspath(output_dir)
print(f"输出目录: {output_dir}")

staging_dir = prepare_staging(output_dir)
print(f"数据目录: {staging_dir}")

from evalscope.perf.utils.report.generate_report import gen_perf_html_report
from evalscope.perf.arguments import Arguments

# 读取真实参数
args_files = (
    glob.glob(os.path.join(staging_dir, "_args.json")) +
    glob.glob(os.path.join(staging_dir, "**/benchmark_args.json"), recursive=True)
)
real_args = {}
if args_files:
    with open(args_files[0]) as f:
        real_args = json.load(f)

dummy_args = Arguments(
    model=real_args.get("model", "unknown"),
    url=real_args.get("url", "http://localhost"),
    api=real_args.get("api", "openai"),
)

report_path = gen_perf_html_report(
    output_dir=staging_dir,
    results={},
    args=dummy_args,
    output_html_name="perf_report.html",
)

# 复制报告到原始目录
if report_path and staging_dir != output_dir:
    final_path = os.path.join(output_dir, "perf_report.html")
    shutil.copy2(report_path, final_path)
    print(f"\nHTML 报告: {final_path}")
elif report_path:
    print(f"\nHTML 报告: {report_path}")
else:
    print("生成失败")
