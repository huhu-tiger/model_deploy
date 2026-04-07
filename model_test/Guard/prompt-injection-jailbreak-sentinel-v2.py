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

from common import (
    bool_to_text,
    build_eval_summary_df,
    call_sentinel_api,
    get_concurrency,
    label_to_text,
    load_env_by_priority,
    parse_sentinel_output,
    resolve_preferred_path,
    sanitize_input_row,
    write_markdown_report,
)




def process_row(
    idx: int,
    row: Dict[str, Any],
    endpoint: str,
    model: str,
    temperature: float,
    max_token: int,
    timeout: int,
    retries: int,
    backoff: float,
    sleep_seconds: float,
) -> Tuple[int, Dict[str, Any]]:
    row = sanitize_input_row(row)
    text = str(row.get("text", ""))

    response_json = call_sentinel_api(
        endpoint=endpoint,
        model=model,
        content=text,
        temperature=temperature,
        max_token=max_token,
        timeout=timeout,
        retries=retries,
        backoff=backoff,
    )

    label, safe_prob, jailbreak_prob, pred_label = parse_sentinel_output(response_json)
    true_label_raw = str(row.get("label", "")).strip()

    updated = dict(row)
    updated["检测标签"] = label
    updated["安全概率"] = f"{safe_prob:.6f}"
    updated["越狱概率"] = f"{jailbreak_prob:.6f}"
    updated["真实标签"] = label_to_text(true_label_raw)
    updated["预测标签"] = label_to_text(pred_label)
    updated["是否判断正确"] = bool_to_text(bool(pred_label and true_label_raw and pred_label == true_label_raw))

    if sleep_seconds > 0:
        time.sleep(sleep_seconds)

    return idx, updated


def main() -> None:
    start_time = time.perf_counter()
    script_dir = Path(__file__).resolve().parent
    default_input_path = resolve_preferred_path("datasets/data1.csv", script_dir)
    default_output_path = script_dir / "output" / "data1_sentinel_results.csv"

    parser = argparse.ArgumentParser(description="Run prompt-injection-jailbreak-sentinel-v2 on dataset CSV.")
    parser.add_argument("--input", default=str(default_input_path), help="Input CSV path")
    parser.add_argument("--output", default=str(default_output_path), help="Output CSV path")
    parser.add_argument(
        "--markdown-output",
        default=None,
        help="Output Markdown path, default uses output file name with .md suffix",
    )
    parser.add_argument("--env-file", default=None, help="Path to .env file")
    parser.add_argument("--endpoint", default=None, help="Sentinel endpoint, default /classify")
    parser.add_argument("--model", default=None, help="Model name")
    parser.add_argument("--concurrency", type=int, default=None, help="Concurrency workers")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    parser.add_argument("--max-token", type=int, default=20, help="max_token request field")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout seconds")
    parser.add_argument("--retries", type=int, default=2, help="Retry times")
    parser.add_argument("--backoff", type=float, default=1.5, help="Retry backoff")
    parser.add_argument("--sleep", type=float, default=0.0, help="Sleep seconds between requests")

    args = parser.parse_args()

    load_env_by_priority(script_dir=script_dir, env_file=args.env_file)

    endpoint = (
        args.endpoint
        or os.getenv("SENTINEL_ENDPOINT")
        or "http://39.155.179.5:8016/classify"
    )
    model = args.model or os.getenv("SENTINEL_MODEL") or "prompt-injection-jailbreak-sentinel-v2"
    concurrency = get_concurrency(args.concurrency, "SENTINEL_CONCURRENCY", default=1)

    print("[ENV] SENTINEL_ENDPOINT=", os.getenv("SENTINEL_ENDPOINT", ""))
    print("[ENV] SENTINEL_MODEL=", os.getenv("SENTINEL_MODEL", ""))
    print("[ENV] SENTINEL_CONCURRENCY=", os.getenv("SENTINEL_CONCURRENCY", ""))
    print("[EFFECTIVE] endpoint=", endpoint)
    print("[EFFECTIVE] model=", model)
    print("[EFFECTIVE] concurrency=", concurrency)

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8", newline="") as infile:
        reader = csv.DictReader(infile)
        if not reader.fieldnames or "text" not in reader.fieldnames:
            print("Input CSV must include a 'text' column", file=sys.stderr)
            sys.exit(1)

        rows: List[Dict[str, Any]] = list(reader)
        input_fields = [field for field in reader.fieldnames if field != "label"]
        fieldnames = input_fields + [
            "真实标签",
            "预测标签",
            "是否判断正确",
            "检测标签",
            "安全概率",
            "越狱概率",
        ]

    results: List[Dict[str, Any]] = []

    if concurrency == 1:
        for idx, row in enumerate(rows):
            _, updated = process_row(
                idx=idx,
                row=row,
                endpoint=endpoint,
                model=model,
                temperature=args.temperature,
                max_token=args.max_token,
                timeout=args.timeout,
                retries=args.retries,
                backoff=args.backoff,
                sleep_seconds=args.sleep,
            )
            results.append(updated)
    else:
        ordered_results: List[Dict[str, Any] | None] = [None] * len(rows)
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [
                executor.submit(
                    process_row,
                    idx,
                    row,
                    endpoint,
                    model,
                    args.temperature,
                    args.max_token,
                    args.timeout,
                    args.retries,
                    args.backoff,
                    args.sleep,
                )
                for idx, row in enumerate(rows)
            ]

            for future in as_completed(futures):
                idx, updated = future.result()
                ordered_results[idx] = updated

        results = [item for item in ordered_results if item is not None]

    normalized_results: List[Dict[str, Any]] = []
    for row in results:
        cleaned = {k: v for k, v in row.items() if k is not None}
        cleaned.pop("label", None)
        normalized_results.append(cleaned)

    with output_path.open("w", encoding="utf-8", newline="") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(normalized_results)

    markdown_output_path = Path(args.markdown_output) if args.markdown_output else output_path.with_suffix(".md")
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(normalized_results)
    summary_df = build_eval_summary_df(df=df, start_time=start_time)
    write_markdown_report(str(markdown_output_path), summary_df, df)

    print(f"Wrote CSV to {output_path} (concurrency={concurrency})")
    print(f"Wrote Markdown table to {markdown_output_path}")


if __name__ == "__main__":
    main()
