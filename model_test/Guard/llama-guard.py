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

from common.env_utils import load_env_by_priority, resolve_preferred_path
from common.lang_utils import calc_accuracy, detect_language
from common.openai_guard import call_guard_api, normalize_base_url


LLAMA_GUARD_TAXONOMY: Dict[str, Tuple[str, str]] = {
    "S1": ("Violent Crimes", "暴力犯罪"),
    "S2": ("Non-Violent Crimes", "非暴力犯罪"),
    "S3": ("Sex-Related Crimes", "性相关犯罪"),
    "S4": ("Child Sexual Exploitation", "儿童性剥削"),
    "S5": ("Specialized Advice", "专业建议"),
    "S6": ("Privacy", "隐私"),
    "S7": ("Intellectual Property", "知识产权"),
    "S8": ("Indiscriminate Weapons", "无差别武器"),
    "S9": ("Hate", "仇恨言论"),
    "S10": ("Suicide & Self-Harm", "自杀与自残"),
    "S11": ("Sexual Content", "性内容"),
}


def get_concurrency(cli_concurrency: int | None) -> int:
    if cli_concurrency is not None:
        return max(1, cli_concurrency)

    raw = os.getenv("LLAMAGUARD_CONCURRENCY", "1")
    try:
        value = int(raw.strip())
    except ValueError:
        value = 1
    return max(1, value)


def label_to_text(label: str) -> str:
    normalized = str(label).strip().lower()
    if normalized == "1":
        return "风险"
    if normalized == "0":
        return "安全"
    return "未知"


def bool_to_text(flag: bool) -> str:
    return "是" if flag else "否"


def sanitize_input_row(row: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = dict(row)
    extras = cleaned.pop(None, None)

    if extras:
        extra_parts = [str(part) for part in extras if part is not None and str(part) != ""]
        if extra_parts:
            current_text = str(cleaned.get("text", ""))
            suffix = ",".join(extra_parts)
            cleaned["text"] = f"{current_text},{suffix}" if current_text else suffix

    return cleaned


def extract_content(response_json: Dict[str, Any]) -> str:
    try:
        return str(response_json["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        return ""


def parse_llama_guard_output(content: str) -> Tuple[str, str, str, str, str]:
    # 常见返回示例: "S1"
    token = content.strip().upper()

    if token in LLAMA_GUARD_TAXONOMY:
        dimension_en, category_zh = LLAMA_GUARD_TAXONOMY[token]
        return "Unsafe", token, dimension_en, category_zh, "1"

    # 兼容 Safe/SAFE 等输出
    if token in {"SAFE", "OK", "BENIGN", "NONE", "S0"}:
        return "Safe", "SAFE", "Safe", "安全", "0"

    return "Unknown", "UNKNOWN", "Unknown", "未知", ""


def process_row(
    idx: int,
    row: Dict[str, Any],
    client: OpenAI,
    model: str,
    temperature: float,
    max_token: int,
    retries: int,
    backoff: float,
    sleep_seconds: float,
) -> Tuple[int, Dict[str, Any]]:
    row = sanitize_input_row(row)
    text = str(row.get("text", ""))

    response_json = call_guard_api(
        client=client,
        model=model,
        content=text,
        temperature=temperature,
        max_token=max_token,
        retries=retries,
        backoff=backoff,
    )

    guard_response = extract_content(response_json)
    safety, risk_id, risk_dimension, risk_category, pred_label = parse_llama_guard_output(guard_response)

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
    default_output_path = script_dir / "output" / "data1_llama_guard_results.csv"

    parser = argparse.ArgumentParser(description="Run Llama-Guard-2-8B on dataset CSV.")
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
    parser.add_argument("--max-token", type=int, default=20, help="max_token request field")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout seconds")
    parser.add_argument("--retries", type=int, default=2, help="Retry times")
    parser.add_argument("--backoff", type=float, default=1.5, help="Retry backoff")
    parser.add_argument("--sleep", type=float, default=0.0, help="Sleep seconds between requests")

    args = parser.parse_args()

    load_env_by_priority(script_dir=script_dir, env_file=args.env_file)

    endpoint = args.endpoint or os.getenv("LLAMAGUARD_ENDPOINT")
    base_url = normalize_base_url(args.base_url or os.getenv("LLAMAGUARD_BASE_URL"), endpoint)
    api_key = args.api_key or os.getenv("LLAMAGUARD_API_KEY", "dummy")
    model = args.model or os.getenv("LLAMAGUARD_MODEL", "Llama-Guard-2-8B")
    concurrency = get_concurrency(args.concurrency)

    if not base_url:
        print(
            "Missing base URL. Set LLAMAGUARD_BASE_URL/LLAMAGUARD_ENDPOINT in .env or pass --base-url/--endpoint",
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
                max_token=args.max_token,
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
                    args.max_token,
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

    zh_df = df[df["语言"] == "中文"]
    en_df = df[df["语言"] == "英文"]
    mixed_df = df[df["语言"] == "中英混合"]

    overall_acc = calc_accuracy(df)
    zh_acc = calc_accuracy(zh_df)
    en_acc = calc_accuracy(en_df)
    mixed_acc = calc_accuracy(mixed_df)

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
            {"指标": "中文样本数", "值": str(len(zh_df))},
            {"指标": "英文样本数", "值": str(len(en_df))},
            {"指标": "中英混合样本数", "值": str(len(mixed_df))},
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
