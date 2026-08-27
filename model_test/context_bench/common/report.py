#!/usr/bin/env python3
"""汇总 context_bench 各档结果：终端表格 + Markdown + 带图表的 HTML。"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path
from typing import Any

SUMMARY_KEYS = {
    "concurrency": "Concurrency",
    "duration_s": "Test Duration (s)",
    "total": "Total Requests",
    "success": "Success Requests",
    "failed": "Failed Requests",
    "rps": "Req Throughput (req/s)",
    "latency_s": "Avg Latency (s)",
    "ttft_ms": "TTFT (ms)",
    "tpot_ms": "TPOT (ms)",
    "itl_ms": "ITL (ms)",
    "in_tok": "Avg Input Tokens",
    "out_tok": "Avg Output Tokens",
    "out_tps": "Output Throughput (tok/s)",
    "total_tps": "Total Throughput (tok/s)",
}

DIR_RE = re.compile(r"ctx_(\d+)k(?:_([A-Za-z0-9_]+))?_p(\d+)$")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _p99_ttft(percentiles: Any) -> float | None:
    if not isinstance(percentiles, list):
        return None
    for row in percentiles:
        label = str(row.get("Percentiles") or row.get("percentile") or "")
        if label.startswith("99"):
            val = row.get("TTFT (ms)")
            return _num(val) if val is not None else None
    return None


def _find_summary(run_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    matches = sorted(run_dir.rglob("benchmark_summary.json"))
    if not matches:
        return None, None
    summary = json.loads(matches[0].read_text(encoding="utf-8"))
    pct_path = matches[0].with_name("benchmark_percentile.json")
    percentiles = json.loads(pct_path.read_text(encoding="utf-8")) if pct_path.exists() else None
    return summary, percentiles


def collect_runs(root: Path) -> list[dict[str, Any]]:
    index = root / "runs.jsonl"
    rows: list[dict[str, Any]] = []
    if index.exists():
        for line in index.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        for d in sorted(root.iterdir() if root.exists() else []):
            m = DIR_RE.search(d.name)
            if not m or not d.is_dir():
                continue
            rows.append({
                "ctx_k": int(m.group(1)),
                "prefix_mode": m.group(2) or "",
                "parallel": int(m.group(3)),
                "dir": d.name,
                "status": "ok",
            })

    for row in rows:
        rel = row.get("dir") or (
            f"ctx_{row.get('ctx_k')}k_{row['prefix_mode']}_p{row.get('parallel')}"
            if row.get("prefix_mode")
            else f"ctx_{row.get('ctx_k')}k_p{row.get('parallel')}"
        )
        run_dir = root / rel
        summary, percentiles = _find_summary(run_dir) if run_dir.is_dir() else (None, None)
        row["summary"] = summary
        if summary:
            row.setdefault("status", "ok")
            row["ttft_ms"] = _num(summary.get(SUMMARY_KEYS["ttft_ms"]))
            row["p99_ttft_ms"] = _p99_ttft(percentiles)
            row["latency_s"] = _num(summary.get(SUMMARY_KEYS["latency_s"]))
            row["out_tps"] = _num(summary.get(SUMMARY_KEYS["out_tps"]))
            row["rps"] = _num(summary.get(SUMMARY_KEYS["rps"]))
            row["success"] = int(_num(summary.get(SUMMARY_KEYS["success"])))
            row["failed"] = int(_num(summary.get(SUMMARY_KEYS["failed"])))
            row["total"] = int(_num(summary.get(SUMMARY_KEYS["total"])))
            row["in_tok"] = _num(summary.get(SUMMARY_KEYS["in_tok"]))
            row["out_tok"] = _num(summary.get(SUMMARY_KEYS["out_tok"]))
            row["tpot_ms"] = _num(summary.get(SUMMARY_KEYS["tpot_ms"]))
            ttft = row["ttft_ms"]
            if ttft and ttft > 0 and row["in_tok"]:
                row["prefill_tps"] = row["in_tok"] / (ttft / 1000.0)
            else:
                row["prefill_tps"] = None
            if not row.get("prompt_tokens"):
                row["prompt_tokens"] = int(row["in_tok"] or 0)
        elif row.get("status") not in ("skip", "timeout", "fail"):
            row["status"] = "fail" if run_dir.exists() else "skip"
    rows.sort(key=lambda r: (int(r.get("ctx_k") or 0), str(r.get("prefix_mode") or ""), int(r.get("parallel") or 0)))
    return rows


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None or value == "":
        return "-"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if num != num:  # NaN
        return "-"
    return f"{num:.{digits}f}"


def _mode_label(mode: Any) -> str:
    return {
        "cache_miss": "冷缓存",
        "cache_hit": "热缓存",
        "default": "默认",
        "": "默认",
    }.get(str(mode or ""), str(mode or "默认"))


def table_rows(runs: list[dict[str, Any]]) -> tuple[list[str], list[list[str]]]:
    headers = [
        "ctx_k", "prefix", "parallel", "status", "prompt", "succ/fail",
        "RPS", "out tok/s", "TTFT ms", "P99 TTFT", "latency s",
    ]
    body: list[list[str]] = []
    for r in runs:
        succ = r.get("success")
        fail = r.get("failed")
        ratio = f"{succ}/{fail}" if succ is not None else "-"
        body.append([
            str(r.get("ctx_k", "-")),
            _mode_label(r.get("prefix_mode")),
            str(r.get("parallel", "-")),
            str(r.get("status", "-")),
            str(r.get("prompt_tokens") if r.get("prompt_tokens") is not None else "-"),
            ratio,
            _fmt(r.get("rps")),
            _fmt(r.get("out_tps")),
            _fmt(r.get("ttft_ms")),
            _fmt(r.get("p99_ttft_ms")),
            _fmt(r.get("latency_s")),
        ])
    return headers, body


def render_ascii(headers: list[str], body: list[list[str]]) -> str:
    cols = list(zip(*([headers] + body))) if body else [[h] for h in headers]
    widths = [max(len(str(c)) for c in col) for col in cols]
    def fmt_row(row: list[str]) -> str:
        return " | ".join(str(cell).ljust(w) for cell, w in zip(row, widths))
    line = "-+-".join("-" * w for w in widths)
    parts = [fmt_row(headers), line]
    parts.extend(fmt_row(r) for r in body)
    if not body:
        parts.append("(无结果)")
    return "\n".join(parts)


def render_markdown(headers: list[str], body: list[list[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    rows = ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join([head, sep, *rows]) if body else head + "\n" + sep + "\n| (无结果) |"


def _ok_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in runs if r.get("status") == "ok" and r.get("summary")]


_CJK_FONTS = (
    "Droid Sans Fallback",
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "WenQuanYi Micro Hei",
    "WenQuanYi Zen Hei",
    "Source Han Sans SC",
    "Microsoft YaHei",
    "SimHei",
)


def _require_pandas_mpl():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "报告图表需要 pandas / numpy / matplotlib。"
            "请在 conda 环境 model_test 中安装后重试。"
        ) from exc
    return np, pd, plt


_CJK_FONT_FILES = (
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
)


def _setup_chinese_font(plt) -> str:
    """注册 CJK 字体，并让 ASCII 回退到 DejaVu，避免中文或数字缺字。"""
    from matplotlib import font_manager

    cjk_name = ""
    for path in _CJK_FONT_FILES:
        p = Path(path)
        if not p.is_file():
            continue
        font_manager.fontManager.addfont(str(p))
        cjk_name = font_manager.FontProperties(fname=str(p)).get_name()
        break
    if not cjk_name:
        available = {f.name for f in font_manager.fontManager.ttflist}
        for name in _CJK_FONTS:
            if name in available:
                cjk_name = name
                break
    families = [n for n in (cjk_name, "DejaVu Sans", "sans-serif") if n]
    plt.rcParams["font.family"] = families
    plt.rcParams["font.sans-serif"] = families
    plt.rcParams["axes.unicode_minus"] = False
    return cjk_name


def runs_frame(runs: list[dict[str, Any]]):
    _, pd, _ = _require_pandas_mpl()
    modes = {str(r.get("prefix_mode") or "default") for r in runs}
    multi_mode = len(modes) > 1
    rows = []
    for r in runs:
        mode = str(r.get("prefix_mode") or "default")
        ttft_ms = r.get("ttft_ms")
        ctx_k = int(r.get("ctx_k") or 0)
        parallel = int(r.get("parallel") or 0)
        label = f"{ctx_k}K·并发{parallel}"
        if multi_mode:
            label += f"·{mode}"
        rows.append({
            "ctx_k": ctx_k,
            "parallel": parallel,
            "prefix_mode": mode,
            "status": str(r.get("status") or ""),
            "prompt_tokens": r.get("prompt_tokens"),
            "ttft_ms": ttft_ms,
            "ttft_s": (float(ttft_ms) / 1000.0) if ttft_ms else None,
            "p99_ttft_ms": r.get("p99_ttft_ms"),
            "latency_s": r.get("latency_s"),
            "out_tps": r.get("out_tps"),
            "prefill_tps": r.get("prefill_tps"),
            "rps": r.get("rps"),
            "series": f"{mode} 并发{r.get('parallel')}",
            "label": label,
        })
    return pd.DataFrame(rows)


ECHARTS_JS_HOST = "https://assets.pyecharts.org/assets/v6/"
ECHARTS_JS_URL = ECHARTS_JS_HOST + "echarts.min.js"
DEFAULT_CHART_COLORS = {
    "cold_ttft": "#1d4ed8",
    "cold_latency": "#93c5fd",
    "hot_ttft": "#15803d",
    "hot_latency": "#86efac",
}


def chart_colors(config: dict[str, Any] | None = None) -> dict[str, str]:
    colors = dict(DEFAULT_CHART_COLORS)
    configured = (config or {}).get("chart_colors")
    if isinstance(configured, dict):
        for key in colors:
            value = configured.get(key)
            if isinstance(value, str) and value.strip():
                colors[key] = value.strip()
    return colors


def _use_domestic_echarts_cdn() -> None:
    """强制走 pyecharts 国内 CDN，避免默认 host 被改到 jsdelivr 等境外源。"""
    try:
        from pyecharts.globals import CurrentConfig

        CurrentConfig.ONLINE_HOST = ECHARTS_JS_HOST
    except ImportError:
        pass


def _pyecharts_embed(html: str) -> str:
    """从 pyecharts render_embed() 产出的完整 HTML 中，抠出可内嵌片段，脚本走国内 CDN。"""
    body_match = re.search(r"<body[^>]*>(.*)</body>", html, re.S)
    body_inner = body_match.group(1) if body_match else html
    body_inner = re.sub(r'<script[^>]+src="[^"]+"[^>]*>\s*</script>\s*', "", body_inner)
    return f'<script type="text/javascript" src="{ECHARTS_JS_URL}"></script>\n{body_inner}'


def _chart_matrix(df):
    """按上下文/并发对齐冷、热数据，供静态图和交互图共用。"""
    d = df.sort_values(["ctx_k", "parallel", "prefix_mode"]).drop_duplicates(
        subset=["ctx_k", "parallel", "prefix_mode"], keep="last"
    )
    pairs = sorted({(int(r.ctx_k), int(r.parallel)) for r in d.itertuples()}, key=lambda x: (x[0], x[1]))
    labels = [f"{ctx}K·并发{parallel}" for ctx, parallel in pairs]

    def values(mode: str, metric: str) -> list[float | None]:
        indexed = {
            (int(r.ctx_k), int(r.parallel)): getattr(r, metric)
            for r in d[d["prefix_mode"] == mode].itertuples()
        }
        out: list[float | None] = []
        for pair in pairs:
            value = indexed.get(pair)
            out.append(None if value is None or value != value else float(value))
        return out

    return labels, {
        "cold_ttft": values("cache_miss", "ttft_s"),
        "hot_ttft": values("cache_hit", "ttft_s"),
        "cold_latency": values("cache_miss", "latency_s"),
        "hot_latency": values("cache_hit", "latency_s"),
    }


def _pyecharts_overview(df, colors: dict[str, str]) -> tuple[str, str]:
    """按冷/热缓存分组展示 TTFT 与请求完成时间。"""
    try:
        from pyecharts import options as opts
        from pyecharts.charts import Bar
    except ImportError:
        return "", ""
    if df.empty:
        return "", ""

    labels, series = _chart_matrix(df)
    finite_values = [v for values in series.values() for v in values if v is not None]
    y_max = round(max(finite_values) * 1.18, 2) if finite_values else None
    bar = Bar(init_opts=opts.InitOpts(width="1200px", height="520px", theme="white"))
    bar.add_xaxis(labels)
    for name, key in (
        ("冷缓存 TTFT", "cold_ttft"),
        ("冷缓存完成时间", "cold_latency"),
        ("热缓存 TTFT", "hot_ttft"),
        ("热缓存完成时间", "hot_latency"),
    ):
        values = [None if v is None else round(v, 2) for v in series[key]]
        bar.add_yaxis(
            name, values,
            itemstyle_opts=opts.ItemStyleOpts(color=colors[key]),
            label_opts=opts.LabelOpts(is_show=False),
            category_gap="25%",
        )
    bar.set_global_opts(
        title_opts=opts.TitleOpts(title="长上下文压测：冷缓存 vs 热缓存"),
        tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="shadow"),
        legend_opts=opts.LegendOpts(pos_top="7%", pos_left="center"),
        xaxis_opts=opts.AxisOpts(name="上下文长度 · 并发", axislabel_opts=opts.LabelOpts(interval=0, rotate=15)),
        yaxis_opts=opts.AxisOpts(name="秒", max_=y_max),
    )
    _use_domestic_echarts_cdn()
    full_html = bar.render_embed()
    full_html = re.sub(
        r"(?:\\u[0-9a-fA-F]{4})+",
        lambda match: match.group(0).encode("ascii").decode("unicode_escape"),
        full_html,
    )
    return full_html, _pyecharts_embed(full_html)


def write_charts(
    runs: list[dict[str, Any]],
    out_dir: Path,
    colors: dict[str, str] | None = None,
) -> tuple[list[Path], str]:
    """生成明确区分冷、热缓存的 TTFT 与请求完成时间总览图。"""
    np, _pd, plt = _require_pandas_mpl()
    ok = _ok_runs(runs)
    if not ok:
        return [], ""
    df = runs_frame(ok)
    if df.empty:
        return [], ""
    out_dir.mkdir(parents=True, exist_ok=True)
    _setup_chinese_font(plt)

    labels, series = _chart_matrix(df)
    colors = colors or chart_colors()
    x = np.arange(len(labels))
    width = 0.2
    specs = (
        ("cold_ttft", -1.5, colors["cold_ttft"], "冷缓存 TTFT"),
        ("cold_latency", -0.5, colors["cold_latency"], "冷缓存完成时间"),
        ("hot_ttft", 0.5, colors["hot_ttft"], "热缓存 TTFT"),
        ("hot_latency", 1.5, colors["hot_latency"], "热缓存完成时间"),
    )

    fig, ax = plt.subplots(figsize=(max(9.0, len(labels) * 1.5), 5.8))
    for key, offset, color, label in specs:
        values = np.array([np.nan if v is None else v for v in series[key]], dtype=float)
        bars = ax.bar(x + offset * width, values, width, color=color, label=label)
        ax.bar_label(bars, fmt="%.1f", padding=2, fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel("秒")
    finite_values = [v for values in series.values() for v in values if v is not None]
    if finite_values:
        ax.set_ylim(top=max(finite_values) * 1.18)
    ax.set_title("长上下文压测：冷缓存 vs 热缓存", pad=46)
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 1.02),
        fontsize=9,
        ncol=4,
        frameon=False,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    png = out_dir / "overview.png"
    fig.savefig(png, dpi=140, bbox_inches="tight")
    plt.close(fig)

    full_html, embed_html = _pyecharts_overview(df, colors)
    if full_html:
        (out_dir / "overview.html").write_text(full_html, encoding="utf-8")
    return [png], embed_html


def _png_img_tag(path: Path) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f'<div class="chart"><img src="data:image/png;base64,{b64}" alt="{path.stem}"/></div>'


def cache_compare_rows(runs: list[dict[str, Any]]) -> tuple[list[str], list[list[str]]]:
    """命中 vs 不命中对照：同一 ctx/并发下 TTFT 与吞吐比。"""
    headers = ["ctx_k", "parallel", "miss TTFT", "hit TTFT", "TTFT miss/hit", "miss tok/s", "hit tok/s", "tps hit/miss"]
    ok = _ok_runs(runs)
    if not ok:
        return headers, []
    np, pd, _ = _require_pandas_mpl()
    df = runs_frame(ok)
    miss = df[df["prefix_mode"] == "cache_miss"][["ctx_k", "parallel", "ttft_ms", "out_tps"]].rename(
        columns={"ttft_ms": "miss_ttft", "out_tps": "miss_tps"}
    )
    hit = df[df["prefix_mode"] == "cache_hit"][["ctx_k", "parallel", "ttft_ms", "out_tps"]].rename(
        columns={"ttft_ms": "hit_ttft", "out_tps": "hit_tps"}
    )
    merged = miss.merge(hit, on=["ctx_k", "parallel"], how="inner")
    if merged.empty:
        return headers, []
    merged["ttft_ratio"] = np.where(
        (merged["hit_ttft"].notna()) & (merged["hit_ttft"] > 0),
        merged["miss_ttft"] / merged["hit_ttft"],
        np.nan,
    )
    merged["tps_ratio"] = np.where(
        (merged["miss_tps"].notna()) & (merged["miss_tps"] > 0),
        merged["hit_tps"] / merged["miss_tps"],
        np.nan,
    )
    merged = merged.sort_values(["ctx_k", "parallel"])
    body: list[list[str]] = []
    for row in merged.itertuples(index=False):
        body.append([
            str(int(row.ctx_k)),
            str(int(row.parallel)),
            _fmt(row.miss_ttft),
            _fmt(row.hit_ttft),
            _fmt(None if pd.isna(row.ttft_ratio) else float(row.ttft_ratio)),
            _fmt(row.miss_tps),
            _fmt(row.hit_tps),
            _fmt(None if pd.isna(row.tps_ratio) else float(row.tps_ratio)),
        ])
    return headers, body


def _table_html(headers: list[str], body: list[list[str]]) -> str:
    html = "<table><thead><tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr></thead><tbody>"
    for row in body:
        html += "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
    html += "</tbody></table>"
    return html


def write_html(
    root: Path,
    meta: dict[str, Any],
    headers: list[str],
    body: list[list[str]],
    chart_paths: list[Path],
    compare_headers: list[str] | None = None,
    compare_body: list[list[str]] | None = None,
    chart_embed_html: str = "",
) -> Path:
    table_html = _table_html(headers, body)
    compare_block = ""
    if compare_headers and compare_body:
        compare_block = "<h2>缓存命中 vs 不命中</h2>" + _table_html(compare_headers, compare_body)
    if chart_paths:
        charts_html = "\n".join(_png_img_tag(p) for p in chart_paths)
        if chart_embed_html:
            charts_html += f'\n<div class="echarts">{chart_embed_html}</div>'
    elif chart_embed_html:
        charts_html = f'<div class="echarts">{chart_embed_html}</div>'
    else:
        charts_html = "<p class=\"meta\">无可用图表（成功 run 不足，或未安装 pandas / matplotlib / pyecharts）。</p>"
    title = meta.get("model") or "context sweep"
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8"/>
<title>{title} 长上下文压测</title>
<style>
body {{ font-family: "Droid Sans Fallback", "Noto Sans CJK SC", "Microsoft YaHei", ui-sans-serif, sans-serif; margin: 24px; color: #111; }}
h1 {{ font-size: 20px; margin: 0 0 8px; }}
h2 {{ font-size: 16px; margin: 24px 0 8px; }}
.meta {{ color: #555; margin-bottom: 20px; }}
table {{ border-collapse: collapse; margin: 12px 0 28px; }}
th, td {{ border: 1px solid #e5e5e5; padding: 6px 10px; font-size: 13px; text-align: left; }}
th {{ background: #f5f5f5; }}
.echarts {{ margin: 12px 0 28px; }}
.chart {{ border: 1px solid #eee; padding: 8px; max-width: 1100px; }}
.chart img {{ width: 100%; height: auto; display: block; }}
</style></head>
<body>
<h1>长上下文分档压测</h1>
<div class="meta">模型 {meta.get("model","-")} · {meta.get("url","-")} · max_model_len={meta.get("max_model_len","-")}</div>
{table_html}
{compare_block}
<h2>总览</h2>
{charts_html}
</body></html>
"""
    path = root / "report.html"
    path.write_text(html, encoding="utf-8")
    return path


def record_run(root: Path, payload: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with (root / "runs.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_report(root: Path) -> int:
    root = root.resolve()
    meta = {}
    for name in ("sweep_meta.json", "api_info.json"):
        path = root / name
        if path.exists():
            meta.update(json.loads(path.read_text(encoding="utf-8")))
    if meta.get("id") and not meta.get("model"):
        meta["model"] = meta["id"]
    config: dict[str, Any] = {}
    config_path = root / "content.json"
    if config_path.exists():
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            config = loaded
    colors = chart_colors(config)
    runs = collect_runs(root)
    headers, body = table_rows(runs)
    ascii_table = render_ascii(headers, body)
    md = render_markdown(headers, body)
    cmp_headers: list[str] = []
    cmp_body: list[list[str]] = []
    pngs: list[Path] = []
    chart_embed_html = ""
    try:
        cmp_headers, cmp_body = cache_compare_rows(runs)
        if cmp_body:
            md += "\n\n## 缓存命中 vs 不命中\n\n" + render_markdown(cmp_headers, cmp_body) + "\n"
        pngs, chart_embed_html = write_charts(runs, root / "charts", colors)
    except RuntimeError as exc:
        print(f"[WARN] {exc}", file=sys.stderr)

    (root / "summary.json").write_text(json.dumps(runs, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (root / "summary.md").write_text("# 长上下文分档压测\n\n" + md + "\n", encoding="utf-8")
    html_path = write_html(root, meta, headers, body, pngs, cmp_headers, cmp_body, chart_embed_html)

    print("")
    print("=" * 72)
    print("长上下文压测汇总")
    print("=" * 72)
    print(ascii_table)
    if cmp_body:
        print("")
        print("缓存命中 vs 不命中")
        print(render_ascii(cmp_headers, cmp_body))
    print("")
    print(f"Markdown: {root / 'summary.md'}")
    print(f"HTML:     {html_path}")
    if pngs:
        print("PNG:")
        for p in pngs:
            print(f"  {p}")
    print("=" * 72)
    return 0


def _main() -> int:
    parser = argparse.ArgumentParser(description="context_bench 表格与图表")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("record", help="追加一条 run 记录")
    p_rec.add_argument("--root", required=True)
    p_rec.add_argument("--ctx-k", type=int, required=True)
    p_rec.add_argument("--parallel", type=int, required=True)
    p_rec.add_argument("--status", required=True)
    p_rec.add_argument("--rc", type=int, default=0)
    p_rec.add_argument("--prompt-tokens", type=int, default=0)
    p_rec.add_argument("--n-req", type=int, default=0)
    p_rec.add_argument("--dir", default="")
    p_rec.add_argument("--prefix-mode", default="")

    p_w = sub.add_parser("write", help="生成表格和图表")
    p_w.add_argument("--root", required=True)

    args = parser.parse_args()
    if args.cmd == "record":
        record_run(
            Path(args.root),
            {
                "ctx_k": args.ctx_k,
                "parallel": args.parallel,
                "status": args.status,
                "rc": args.rc,
                "prompt_tokens": args.prompt_tokens,
                "n_req": args.n_req,
                "prefix_mode": args.prefix_mode,
                "dir": args.dir or (
                    f"ctx_{args.ctx_k}k_{args.prefix_mode}_p{args.parallel}"
                    if args.prefix_mode
                    else f"ctx_{args.ctx_k}k_p{args.parallel}"
                ),
            },
        )
        return 0
    return write_report(Path(args.root))


if __name__ == "__main__":
    raise SystemExit(_main())
