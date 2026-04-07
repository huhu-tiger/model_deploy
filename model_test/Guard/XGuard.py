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
    build_eval_summary_df,
    call_guard_api,
    detect_language,
    extract_chat_content,
    get_concurrency as common_get_concurrency,
    label_to_text as common_label_to_text,
    bool_to_text as common_bool_to_text,
    sanitize_input_row as common_sanitize_input_row,
    load_env_by_priority,
    normalize_base_url,
    resolve_preferred_path,
    write_markdown_report,
)


RISK_TAXONOMY: Dict[str, Tuple[str, str]] = {
    "sec": ("Safe", "Safe"),
    "pc": ("Crimes and Illegal Activities", "Pornographic Contraband"),
    "dc": ("Crimes and Illegal Activities", "Drug Crimes"),
    "dw": ("Crimes and Illegal Activities", "Dangerous Weapons"),
    "pi": ("Crimes and Illegal Activities", "Property Infringement"),
    "ec": ("Crimes and Illegal Activities", "Economic Crimes"),
    "ac": ("Hate Speech", "Abusive Curses"),
    "def": ("Hate Speech", "Defamation"),
    "ti": ("Hate Speech", "Threats and Intimidation"),
    "cy": ("Hate Speech", "Cyberbullying"),
    "ph": ("Physical and Mental Health", "Physical Health"),
    "mh": ("Physical and Mental Health", "Mental Health"),
    "se": ("Ethics and Morality", "Social Ethics"),
    "sci": ("Ethics and Morality", "Science Ethics"),
    "pp": ("Data Privacy", "Personal Privacy"),
    "cs": ("Data Privacy", "Commercial Secret"),
    "acc": ("Cybersecurity", "Access Control"),
    "mc": ("Cybersecurity", "Malicious Code"),
    "ha": ("Cybersecurity", "Hacker Attack"),
    "ps": ("Cybersecurity", "Physical Security"),
    "ter": ("Extremism", "Violent Terrorist Activities"),
    "sd": ("Extremism", "Social Disruption"),
    "ext": ("Extremism", "Extremist Ideological Trends"),
    "fin": ("Inappropriate Suggestions", "Finance"),
    "med": ("Inappropriate Suggestions", "Medicine"),
    "law": ("Inappropriate Suggestions", "Law"),
    "cm": ("Risks Involving Minors", "Corruption of Minors"),
    "ma": ("Risks Involving Minors", "Minor Abuse and Exploitation"),
    "md": ("Risks Involving Minors", "Minor Delinquency"),
}


def get_concurrency(cli_concurrency: int | None) -> int:
    return common_get_concurrency(cli_concurrency, "XGUARD_CONCURRENCY", default=1)


def label_to_text(label: str) -> str:
    return common_label_to_text(label)


def bool_to_text(flag: bool) -> str:
    return common_bool_to_text(flag)


def sanitize_input_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return common_sanitize_input_row(row)


def extract_content(response_json: Dict[str, Any]) -> str:
    return extract_chat_content(response_json)


def parse_xguard_output(content: str) -> Tuple[str, str, str, str, str]:
    risk_id = content.strip().lower()
    if risk_id not in RISK_TAXONOMY:
        risk_id = "unknown"

    if risk_id == "sec":
        safety = "Safe"
        pred_label = "0"
        risk_dimension, risk_category = RISK_TAXONOMY["sec"]
    elif risk_id == "unknown":
        safety = "Unknown"
        pred_label = ""
        risk_dimension, risk_category = "Unknown", "Unknown"
    else:
        safety = "Unsafe"
        pred_label = "1"
        risk_dimension, risk_category = RISK_TAXONOMY[risk_id]

    return safety, risk_id, risk_dimension, risk_category, pred_label


def process_row(
    idx: int,
    row: Dict[str, Any],
    client: OpenAI,
    model: str,
    temperature: float,
    max_tokens: int,
    retries: int,
    backoff: float,
    sleep_seconds: float,
) -> Tuple[int, Dict[str, Any]]:
    row = sanitize_input_row(row)
    text = row.get("text", "")

    response_json = call_guard_api(
        client=client,
        model=model,
        content=text,
        temperature=temperature,
        max_token=max_tokens,
        retries=retries,
        backoff=backoff,
    )

    guard_response = extract_content(response_json)
    safety, risk_id, risk_dimension, risk_category, pred_label = parse_xguard_output(guard_response)

    updated = dict(row)
    true_label_raw = str(updated.get("label", "")).strip()

    updated["检测响应"] = guard_response
    updated["安全性"] = safety
    updated["风险类别原文"] = guard_response
    updated["风险ID"] = risk_id
    updated["风险维度"] = risk_dimension
    updated["风险分类"] = risk_category
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
    default_output_path = script_dir / "output" / "data1_xguard_results.csv"

    parser = argparse.ArgumentParser(description="Run XGuard on dataset CSV.")
    parser.add_argument("--input", default=str(default_input_path), help="Input CSV path")
    parser.add_argument("--output", default=str(default_output_path), help="Output CSV path")
    parser.add_argument(
        "--markdown-output",
        default=None,
        help="Output Markdown path, default uses output file name with .md suffix",
    )
    parser.add_argument("--env-file", default=None, help="Path to .env file")
    parser.add_argument("--base-url", default=None, help="OpenAI compatible base URL")
    parser.add_argument("--endpoint", default=None, help="Compatibility endpoint, e.g. .../v1/chat/completions")
    parser.add_argument("--api-key", default=None, help="API key, local service can use any non-empty value")
    parser.add_argument("--model", default=None, help="Model name")
    parser.add_argument("--concurrency", type=int, default=None, help="Concurrency workers")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    parser.add_argument("--max-tokens", type=int, default=1, help="Max completion tokens")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout seconds")
    parser.add_argument("--retries", type=int, default=2, help="Retry times")
    parser.add_argument("--backoff", type=float, default=1.5, help="Retry backoff")
    parser.add_argument("--sleep", type=float, default=0.0, help="Sleep seconds between requests")

    args = parser.parse_args()

    load_env_by_priority(script_dir=script_dir, env_file=args.env_file)

    endpoint = args.endpoint or os.getenv("XGUARD_ENDPOINT")
    base_url = normalize_base_url(args.base_url or os.getenv("XGUARD_BASE_URL"), endpoint)
    api_key = args.api_key or os.getenv("XGUARD_API_KEY", "dummy")
    model = args.model or os.getenv("XGUARD_MODEL", "YuFeng-XGuard-Reason-8B")
    concurrency = get_concurrency(args.concurrency)

    if not base_url:
        print(
            "Missing base URL. Set XGUARD_BASE_URL/XGUARD_ENDPOINT in .env (XGuard dedicated vars) or pass --base-url/--endpoint",
            file=sys.stderr,
        )
        sys.exit(1)

    input_path = Path(args.input)
    output_path = Path(args.output)
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=args.timeout)

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
            "检测响应",
            "安全性",
            "风险类别原文",
            "风险ID",
            "风险维度",
            "风险分类",
        ]

    results: List[Dict[str, Any]] = []

    if concurrency == 1:
        for idx, row in enumerate(rows):
            _, updated = process_row(
                idx=idx,
                row=row,
                client=client,
                model=model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
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
                    client,
                    model,
                    args.temperature,
                    args.max_tokens,
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
    if "text" in df.columns:
        df["语言"] = df["text"].map(detect_language)
    else:
        df["语言"] = "其他"

    overall_acc = calc_accuracy(df)
    zh_acc = calc_accuracy(df[df["语言"] == "中文"])
    en_acc = calc_accuracy(df[df["语言"] == "英文"])
    mixed_acc = calc_accuracy(df[df["语言"] == "中英混合"])

    zh_count = int((df["语言"] == "中文").sum())
    en_count = int((df["语言"] == "英文").sum())
    mixed_count = int((df["语言"] == "中英混合").sum())

    if "difficulty" in df.columns:
        difficulty_series = df["difficulty"].astype(str).str.strip().str.lower()
        hard_acc = calc_accuracy(df[difficulty_series == "hard"])
        normal_acc = calc_accuracy(df[difficulty_series == "normal"])
    else:
        hard_acc = 0.0
        normal_acc = 0.0

    elapsed_seconds = time.perf_counter() - start_time

    summary_df = pd.DataFrame(
        [
            {"指标": "运行时长", "值": f"{elapsed_seconds:.2f} 秒"},
            {"指标": "样本总数", "值": str(len(df))},
            {"指标": "中文样本数", "值": str(zh_count)},
            {"指标": "英文样本数", "值": str(en_count)},
            {"指标": "中英混合样本数", "值": str(mixed_count)},
            {"指标": "总体正确率", "值": f"{overall_acc:.2%}"},
            {"指标": "中文正确率", "值": f"{zh_acc:.2%}"},
            {"指标": "英文正确率", "值": f"{en_acc:.2%}"},
            {"指标": "中英混合正确率", "值": f"{mixed_acc:.2%}"},
            {"指标": "Hard正确率", "值": f"{hard_acc:.2%}"},
            {"指标": "Normal正确率", "值": f"{normal_acc:.2%}"},
        ]
    )

    summary_md = summary_df.to_markdown(index=False)
    detail_md = df.to_markdown(index=False)
    markdown_output_path.write_text(
        "## 总结\n\n" + summary_md + "\n\n## 明细表\n\n" + detail_md + "\n",
        encoding="utf-8",
    )

    print(f"Wrote CSV to {output_path} (concurrency={concurrency})")
    print(f"Wrote Markdown table to {markdown_output_path}")


if __name__ == "__main__":
    main()
