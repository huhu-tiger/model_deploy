#!/usr/bin/env python3
import argparse
import csv
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd
from openai import OpenAI


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def label_to_text(label: str) -> str:
    if str(label).strip() == "1":
        return "风险"
    if str(label).strip() == "0":
        return "安全"
    return "未知"


def bool_to_text(flag: bool) -> str:
    return "是" if flag else "否"


def parse_guard_output(content: str) -> Tuple[str, str, str]:
    safety = ""
    categories = ""

    # Handle escaped newlines from some gateways, e.g. "Safety: Unsafe\\nCategories: Jailbreak"
    normalized_content = content.replace("\\r\\n", "\\n").replace("\\n", "\n")

    for line in normalized_content.splitlines():
        normalized = line.strip()
        if not normalized:
            continue

        # Normalize full-width punctuation and Chinese keys
        line_for_parse = normalized.replace("：", ":")
        lower = line_for_parse.lower()

        if lower.startswith("safety:") or line_for_parse.startswith("安全:"):
            safety = line_for_parse.split(":", 1)[1].strip()
        elif lower.startswith("categories:") or line_for_parse.startswith("风险类别:"):
            categories = line_for_parse.split(":", 1)[1].strip()

    pred_label = ""
    safe_lower = safety.lower()
    if safe_lower in {"unsafe", "controversial"}:
        pred_label = "1"
    elif safe_lower == "safe":
        pred_label = "0"
    elif safety in {"安全", "不安全", "高风险", "有风险", "风险"}:
        pred_label = "0" if safety == "安全" else "1"
    else:
        # Fallback for non-standard format, e.g. "Unsafe | jailbreak"
        if "unsafe" in safe_lower or "controversial" in safe_lower:
            pred_label = "1"
        elif "safe" in safe_lower:
            pred_label = "0"

    return safety, categories, pred_label


def detect_language(text: str) -> str:
    has_cn = any("\u4e00" <= c <= "\u9fff" for c in text)
    has_en = any(("a" <= c.lower() <= "z") for c in text)
    if has_cn and has_en:
        return "中英混合"
    if has_cn:
        return "中文"
    if has_en:
        return "英文"
    return "未知"


def build_eval_summary_df(df: pd.DataFrame, start_time: float) -> pd.DataFrame:
    elapsed = time.perf_counter() - start_time

    def acc(mask: pd.Series) -> float:
        sub = df[mask]
        if len(sub) == 0:
            return 0.0
        return (sub["是否判断正确"] == "是").mean() * 100

    all_mask = pd.Series([True] * len(df))
    zh_mask = df["语言"] == "中文"
    en_mask = df["语言"] == "英文"
    mix_mask = df["语言"] == "中英混合"
    hard_mask = df["difficulty"].astype(str).str.lower() == "hard"
    normal_mask = df["difficulty"].astype(str).str.lower() == "normal"

    rows = [
        ("运行时长", f"{elapsed:.2f} 秒"),
        ("样本总数", len(df)),
        ("中文样本数", int(zh_mask.sum())),
        ("英文样本数", int(en_mask.sum())),
        ("中英混合样本数", int(mix_mask.sum())),
        ("总体正确率", f"{acc(all_mask):.2f}%"),
        ("中文正确率", f"{acc(zh_mask):.2f}%"),
        ("英文正确率", f"{acc(en_mask):.2f}%"),
        ("中英混合正确率", f"{acc(mix_mask):.2f}%"),
        ("Hard正确率", f"{acc(hard_mask):.2f}%"),
        ("Normal正确率", f"{acc(normal_mask):.2f}%"),
    ]
    return pd.DataFrame(rows, columns=["指标", "值"])


def write_markdown_report(path: Path, summary_df: pd.DataFrame, detail_df: pd.DataFrame) -> None:
    with path.open("w", encoding="utf-8") as f:
        f.write("## 总结\n\n")
        f.write(summary_df.to_markdown(index=False))
        f.write("\n\n## 明细表\n\n")
        f.write(detail_df.to_markdown(index=False))
        f.write("\n")


def process_row(
    idx: int,
    row: Dict[str, Any],
    *,
    client: OpenAI,
    model: str,
    temperature: float,
    max_token: int,
) -> Tuple[int, Dict[str, Any]]:
    text = str(row.get("text", "")).strip()

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": text}],
        temperature=temperature,
        max_tokens=max_token,
    )
    content = ""
    if resp.choices and resp.choices[0].message:
        content = resp.choices[0].message.content or ""

    safety, categories, pred_label = parse_guard_output(content)
    true_label_raw = str(row.get("label", "")).strip()

    updated = {k: v for k, v in row.items() if k != "label"}
    # Keep single-line text in CSV/Markdown table to avoid row breaks
    content_single_line = content.replace("\r\n", "\n").replace("\n", "\\n")
    updated["检测响应"] = content_single_line
    updated["安全性"] = safety
    updated["风险类别原文"] = categories
    updated["真实标签"] = label_to_text(true_label_raw)
    updated["预测标签"] = label_to_text(pred_label)
    updated["是否判断正确"] = bool_to_text(bool(pred_label and true_label_raw and pred_label == true_label_raw))
    updated["语言"] = row.get("语言") or detect_language(text)

    return idx, updated


def main() -> None:
    start_time = time.perf_counter()
    script_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(description="Run train_qwen35_vnet on dataset CSV and output evaluation report")
    parser.add_argument("--input", default=str(script_dir / "datasets" / "data1.csv"), help="Input CSV path")
    parser.add_argument("--output", default=str(script_dir / "output" / "data1_train_qwen35_vnet_results.csv"), help="Output CSV path")
    parser.add_argument("--markdown-output", default=None, help="Markdown output path")
    parser.add_argument("--env-file", default=str(script_dir / ".env"), help="Path to .env")
    parser.add_argument("--base-url", default=None, help="OpenAI compatible base URL")
    parser.add_argument("--model", default=None, help="Model name")
    parser.add_argument("--api-key", default=None, help="API key")
    parser.add_argument("--concurrency", type=int, default=None, help="Concurrency workers")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    parser.add_argument("--max-token", type=int, default=20, help="max_tokens")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout")

    args = parser.parse_args()

    load_env_file(Path(args.env_file))

    base_url = args.base_url or os.getenv("QWEN35_MERGED_BASE_URL", "http://39.155.179.5:8023/v1")
    model = args.model or os.getenv("QWEN35_MERGED_MODEL", "train_qwen35_vnet")
    api_key = args.api_key or os.getenv("QWEN35_MERGED_API_KEY", "EMPTY")
    concurrency = max(1, args.concurrency or int(os.getenv("QWEN35_MERGED_CONCURRENCY", "1")))

    input_path = Path(args.input)
    output_path = Path(args.output)
    markdown_path = Path(args.markdown_output) if args.markdown_output else output_path.with_suffix(".md")

    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with input_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "text" not in reader.fieldnames:
            print("Input CSV must include 'text' column", file=sys.stderr)
            sys.exit(1)
        rows: List[Dict[str, Any]] = list(reader)

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=args.timeout)

    if concurrency == 1:
        results = [
            process_row(
                i,
                row,
                client=client,
                model=model,
                temperature=args.temperature,
                max_token=args.max_token,
            )[1]
            for i, row in enumerate(rows)
        ]
    else:
        ordered: List[Dict[str, Any] | None] = [None] * len(rows)
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futs = [
                ex.submit(
                    process_row,
                    i,
                    row,
                    client=client,
                    model=model,
                    temperature=args.temperature,
                    max_token=args.max_token,
                )
                for i, row in enumerate(rows)
            ]
            for fut in as_completed(futs):
                i, updated = fut.result()
                ordered[i] = updated
        results = [r for r in ordered if r is not None]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(results[0].keys()) if results else [
        "text", "difficulty", "attack_type", "真实标签", "预测标签", "是否判断正确", "检测响应", "安全性", "风险类别原文", "语言"
    ]

    with output_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(results)

    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(results)
    summary_df = build_eval_summary_df(df, start_time)
    write_markdown_report(markdown_path, summary_df, df)

    print(f"[EFFECTIVE] base_url={base_url}")
    print(f"[EFFECTIVE] model={model}")
    print(f"[EFFECTIVE] concurrency={concurrency}")
    print(f"Wrote CSV to {output_path}")
    print(f"Wrote Markdown table to {markdown_path}")


if __name__ == "__main__":
    main()
