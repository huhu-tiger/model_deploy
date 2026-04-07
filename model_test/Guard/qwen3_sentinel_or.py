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

from common import (
    bool_to_text,
    build_eval_summary_df,
    call_guard_api,
    call_sentinel_api,
    get_concurrency,
    label_to_text,
    load_env_by_priority,
    parse_sentinel_output,
    resolve_guard_config,
    resolve_preferred_path,
    sanitize_input_row,
    write_markdown_report,
)




def parse_qwen_pred_label(response_json: Dict[str, Any]) -> Tuple[str, str, str]:
    try:
        content = str(response_json["choices"][0]["message"]["content"] or "")
    except Exception:
        content = ""

    safety = ""
    categories = ""
    for line in content.splitlines():
        v = line.strip()
        if not v:
            continue
        low = v.lower()
        if low.startswith("safety:"):
            safety = v.split(":", 1)[1].strip()
        elif low.startswith("categories:"):
            categories = v.split(":", 1)[1].strip()

    pred = ""
    low_safety = safety.lower()
    if low_safety in {"unsafe", "controversial"}:
        pred = "1"
    elif low_safety == "safe":
        pred = "0"

    return content, safety, categories if categories else ""




def qwen_risk_score_from_safety(qwen_safety: str) -> float:
    s = (qwen_safety or "").strip().lower()
    if s == "unsafe":
        return 1.0
    if s == "controversial":
        return 0.7
    if s == "safe":
        return 0.0
    return 0.5


def weighted_fusion(qwen_safety: str, jailbreak_prob: float, qwen_weight: float, sentinel_weight: float, threshold: float) -> Tuple[str, float]:
    qwen_score = qwen_risk_score_from_safety(qwen_safety)
    score = qwen_weight * qwen_score + sentinel_weight * float(jailbreak_prob)
    pred = "1" if score >= threshold else "0"
    return pred, score


def process_row(
    idx: int,
    row: Dict[str, Any],
    qwen_client: OpenAI,
    qwen_model: str,
    sentinel_endpoint: str,
    sentinel_model: str,
    temperature: float,
    max_token: int,
    timeout: int,
    retries: int,
    backoff: float,
    sleep_seconds: float,
    qwen_weight: float,
    sentinel_weight: float,
    fusion_threshold: float,
) -> Tuple[int, Dict[str, Any]]:
    row = sanitize_input_row(row)
    text = str(row.get("text", ""))

    qwen_json = call_guard_api(
        client=qwen_client,
        model=qwen_model,
        content=text,
        temperature=temperature,
        max_token=max_token,
        retries=retries,
        backoff=backoff,
    )
    qwen_content, qwen_safety, qwen_categories = parse_qwen_pred_label(qwen_json)
    qwen_pred = ""
    if qwen_safety.lower() in {"unsafe", "controversial"}:
        qwen_pred = "1"
    elif qwen_safety.lower() == "safe":
        qwen_pred = "0"

    sentinel_json = call_sentinel_api(
        endpoint=sentinel_endpoint,
        model=sentinel_model,
        content=text,
        temperature=temperature,
        max_token=max_token,
        timeout=timeout,
        retries=retries,
        backoff=backoff,
    )
    sentinel_label, safe_prob, jailbreak_prob, sentinel_pred = parse_sentinel_output(sentinel_json)

    fused_pred, fused_score = weighted_fusion(
        qwen_safety=qwen_safety,
        jailbreak_prob=jailbreak_prob,
        qwen_weight=qwen_weight,
        sentinel_weight=sentinel_weight,
        threshold=fusion_threshold,
    )

    updated = dict(row)
    true_label_raw = str(updated.get("label", "")).strip()
    updated["Qwen_检测响应"] = qwen_content
    updated["Qwen_安全性"] = qwen_safety
    updated["Qwen_风险类别原文"] = qwen_categories
    updated["Qwen_预测标签"] = label_to_text(qwen_pred)

    updated["Sentinel_检测标签"] = sentinel_label
    updated["Sentinel_安全概率"] = f"{safe_prob:.6f}"
    updated["Sentinel_越狱概率"] = f"{jailbreak_prob:.6f}"
    updated["Sentinel_预测标签"] = label_to_text(sentinel_pred)

    updated["融合策略"] = "WEIGHTED"
    updated["融合得分"] = f"{fused_score:.6f}"
    updated["融合阈值"] = f"{fusion_threshold:.3f}"
    updated["真实标签"] = label_to_text(true_label_raw)
    updated["预测标签"] = label_to_text(fused_pred)
    updated["是否判断正确"] = bool_to_text(bool(fused_pred and true_label_raw and fused_pred == true_label_raw))

    if sleep_seconds > 0:
        time.sleep(sleep_seconds)

    return idx, updated


def main() -> None:
    start_time = time.perf_counter()
    script_dir = Path(__file__).resolve().parent
    default_env_path = resolve_preferred_path(".env", script_dir)
    default_input_path = resolve_preferred_path("datasets/data1.csv", script_dir)
    default_output_path = script_dir / "output" / "data1_qwen_sentinel_or_results.csv"

    parser = argparse.ArgumentParser(description="Run Qwen3Guard + Sentinel OR fusion on dataset CSV.")
    parser.add_argument("--input", default=str(default_input_path), help="Input CSV path")
    parser.add_argument("--output", default=str(default_output_path), help="Output CSV path")
    parser.add_argument("--markdown-output", default=None, help="Markdown output path")
    parser.add_argument("--env-file", default=str(default_env_path), help="Path to .env file")

    parser.add_argument("--qwen-base-url", default=None, help="Qwen base URL")
    parser.add_argument("--qwen-endpoint", default=None, help="Qwen endpoint fallback")
    parser.add_argument("--qwen-api-key", default=None, help="Qwen API key")
    parser.add_argument("--qwen-model", default=None, help="Qwen model")

    parser.add_argument("--sentinel-endpoint", default=None, help="Sentinel endpoint")
    parser.add_argument("--sentinel-model", default=None, help="Sentinel model")

    parser.add_argument("--concurrency", type=int, default=None, help="Concurrency workers")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    parser.add_argument("--max-token", type=int, default=20, help="max_token")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout")
    parser.add_argument("--retries", type=int, default=2, help="Retries")
    parser.add_argument("--backoff", type=float, default=1.5, help="Retry backoff")
    parser.add_argument("--sleep", type=float, default=0.0, help="Sleep between rows")
    parser.add_argument("--qwen-weight", type=float, default=float(os.getenv("OR_QWEN_WEIGHT", "0.4")), help="Qwen weight in weighted fusion")
    parser.add_argument("--sentinel-weight", type=float, default=float(os.getenv("OR_SENTINEL_WEIGHT", "0.6")), help="Sentinel weight in weighted fusion")
    parser.add_argument("--fusion-threshold", type=float, default=float(os.getenv("OR_FUSION_THRESHOLD", "0.5")), help="Weighted fusion threshold")

    args = parser.parse_args()
    load_env_by_priority(script_dir=script_dir, env_file=args.env_file)

    qwen_base_url, qwen_api_key, qwen_model = resolve_guard_config(
        cli_base_url=args.qwen_base_url or os.getenv("OR_QWEN_BASE_URL"),
        cli_endpoint=args.qwen_endpoint or os.getenv("OR_QWEN_ENDPOINT"),
        cli_api_key=args.qwen_api_key or os.getenv("OR_QWEN_API_KEY"),
        cli_model=args.qwen_model or os.getenv("OR_QWEN_MODEL") or "Qwen3Guard-Gen-8B",
    )

    sentinel_endpoint = args.sentinel_endpoint or os.getenv("OR_SENTINEL_ENDPOINT")
    sentinel_model = args.sentinel_model or os.getenv("OR_SENTINEL_MODEL") or "prompt-injection-jailbreak-sentinel-v2"

    if not qwen_base_url:
        print("Missing Qwen base URL. Set OR_QWEN_BASE_URL/OR_QWEN_ENDPOINT or pass --qwen-*", file=sys.stderr)
        sys.exit(1)
    if not sentinel_endpoint:
        print("Missing Sentinel endpoint. Set OR_SENTINEL_ENDPOINT or pass --sentinel-endpoint", file=sys.stderr)
        sys.exit(1)

    concurrency = get_concurrency(args.concurrency, "OR_GUARD_CONCURRENCY", default=1)

    print("[ENV] OR_QWEN_BASE_URL=", os.getenv("OR_QWEN_BASE_URL", ""))
    print("[ENV] OR_QWEN_ENDPOINT=", os.getenv("OR_QWEN_ENDPOINT", ""))
    print("[ENV] OR_QWEN_MODEL=", os.getenv("OR_QWEN_MODEL", ""))
    print("[ENV] OR_QWEN_API_KEY=", os.getenv("OR_QWEN_API_KEY", ""))
    print("[ENV] OR_SENTINEL_ENDPOINT=", os.getenv("OR_SENTINEL_ENDPOINT", ""))
    print("[ENV] OR_SENTINEL_MODEL=", os.getenv("OR_SENTINEL_MODEL", ""))
    print("[ENV] OR_GUARD_CONCURRENCY=", os.getenv("OR_GUARD_CONCURRENCY", ""))
    print("[ENV] OR_QWEN_WEIGHT=", os.getenv("OR_QWEN_WEIGHT", ""))
    print("[ENV] OR_SENTINEL_WEIGHT=", os.getenv("OR_SENTINEL_WEIGHT", ""))
    print("[ENV] OR_FUSION_THRESHOLD=", os.getenv("OR_FUSION_THRESHOLD", ""))
    print("[EFFECTIVE] qwen_base_url=", qwen_base_url)
    print("[EFFECTIVE] qwen_model=", qwen_model)
    print("[EFFECTIVE] sentinel_endpoint=", sentinel_endpoint)
    print("[EFFECTIVE] sentinel_model=", sentinel_model)
    print("[EFFECTIVE] concurrency=", concurrency)

    total_w = args.qwen_weight + args.sentinel_weight
    if total_w <= 0:
        print("qwen-weight + sentinel-weight must be > 0", file=sys.stderr)
        sys.exit(1)
    qwen_weight = args.qwen_weight / total_w
    sentinel_weight = args.sentinel_weight / total_w

    input_path = Path(args.input)
    output_path = Path(args.output)
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    qwen_client = OpenAI(base_url=qwen_base_url, api_key=qwen_api_key, timeout=args.timeout)

    with input_path.open("r", encoding="utf-8", newline="") as infile:
        reader = csv.DictReader(infile)
        if not reader.fieldnames or "text" not in reader.fieldnames:
            print("Input CSV must include a 'text' column", file=sys.stderr)
            sys.exit(1)
        rows: List[Dict[str, Any]] = list(reader)
        input_fields = [f for f in reader.fieldnames if f != "label"]

    fieldnames = input_fields + [
        "真实标签", "预测标签", "是否判断正确", "融合策略", "融合得分", "融合阈值",
        "Qwen_检测响应", "Qwen_安全性", "Qwen_风险类别原文", "Qwen_预测标签",
        "Sentinel_检测标签", "Sentinel_安全概率", "Sentinel_越狱概率", "Sentinel_预测标签",
    ]

    results: List[Dict[str, Any]] = []
    if concurrency == 1:
        for idx, row in enumerate(rows):
            _, updated = process_row(
                idx, row, qwen_client, qwen_model,
                sentinel_endpoint, sentinel_model,
                args.temperature, args.max_token, args.timeout,
                args.retries, args.backoff, args.sleep,
                qwen_weight, sentinel_weight, args.fusion_threshold,
            )
            results.append(updated)
    else:
        ordered: List[Dict[str, Any] | None] = [None] * len(rows)
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futures = [
                ex.submit(
                    process_row,
                    idx, row, qwen_client, qwen_model,
                    sentinel_endpoint, sentinel_model,
                    args.temperature, args.max_token, args.timeout,
                    args.retries, args.backoff, args.sleep,
                    qwen_weight, sentinel_weight, args.fusion_threshold,
                )
                for idx, row in enumerate(rows)
            ]
            for fut in as_completed(futures):
                idx, updated = fut.result()
                ordered[idx] = updated
        results = [x for x in ordered if x is not None]

    normalized: List[Dict[str, Any]] = []
    for r in results:
        cleaned = {k: v for k, v in r.items() if k is not None}
        cleaned.pop("label", None)
        normalized.append(cleaned)

    with output_path.open("w", encoding="utf-8", newline="") as out:
        w = csv.DictWriter(out, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(normalized)

    md_path = Path(args.markdown_output) if args.markdown_output else output_path.with_suffix(".md")
    md_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(normalized)
    summary_df = build_eval_summary_df(
        df=df,
        start_time=start_time,
        extra_rows=[
            {"指标": "融合方式", "值": "Weighted"},
            {"指标": "Qwen权重", "值": f"{qwen_weight:.3f}"},
            {"指标": "Sentinel权重", "值": f"{sentinel_weight:.3f}"},
            {"指标": "融合阈值", "值": f"{args.fusion_threshold:.3f}"},
        ],
    )
    write_markdown_report(str(md_path), summary_df, df)

    print(f"Wrote CSV to {output_path} (concurrency={concurrency})")
    print(f"Wrote Markdown table to {md_path}")


if __name__ == "__main__":
    main()
