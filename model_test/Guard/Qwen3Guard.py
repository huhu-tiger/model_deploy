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
    extract_chat_content,
    get_concurrency as common_get_concurrency,
    label_to_text as common_label_to_text,
    bool_to_text as common_bool_to_text,
    sanitize_input_row as common_sanitize_input_row,
    load_env_by_priority,
    resolve_guard_config,
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

CATEGORY_NAME_TO_ID: Dict[str, str] = {
    category.lower(): risk_id for risk_id, (_, category) in RISK_TAXONOMY.items()
}

CATEGORY_ALIAS_TO_ID: Dict[str, str] = {
    "jailbreak": "acc",
    "prompt injection": "acc",
    "policy violation": "acc",
    "access control": "acc",
    "hacker attack": "ha",
    "malicious code": "mc",
    "privacy": "pp",
    "personal privacy": "pp",
    "commercial secret": "cs",
    "violence": "ter",
    "terrorism": "ter",
    "extremism": "ext",
    "hate speech": "ac",
    "defamation": "def",
    "threat": "ti",
    "threats": "ti",
    "cyberbullying": "cy",
    "self-harm": "mh",
    "mental health": "mh",
    "drugs": "dc",
    "drug crimes": "dc",
    "weapons": "dw",
    "economic crimes": "ec",
    "law": "law",
    "medicine": "med",
    "finance": "fin",
    "safe": "sec",
}


def get_concurrency(cli_concurrency: int | None) -> int:
    return common_get_concurrency(cli_concurrency, "GUARD_CONCURRENCY", default=1)


def extract_content(response_json: Dict[str, Any]) -> str:
    return extract_chat_content(response_json)


def normalize_category_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def split_categories(raw_categories: str) -> List[str]:
    if not raw_categories:
        return []
    normalized = raw_categories.replace(";", ",").replace("|", ",").replace("/", ",")
    return [part.strip() for part in normalized.split(",") if part.strip()]


def resolve_risk_id_from_category(category_name: str) -> str:
    normalized = normalize_category_name(category_name)
    if not normalized:
        return ""

    risk_id = CATEGORY_NAME_TO_ID.get(normalized)
    if risk_id:
        return risk_id

    alias = CATEGORY_ALIAS_TO_ID.get(normalized)
    if alias:
        return alias

    for key, alias_id in CATEGORY_ALIAS_TO_ID.items():
        if key in normalized:
            return alias_id

    return ""


def label_to_text(label: str) -> str:
    return common_label_to_text(label)


def bool_to_text(flag: bool) -> str:
    return common_bool_to_text(flag)


def parse_guard_output(content: str) -> Tuple[str, str, str, str, str, str]:
    safety = ""
    categories = ""

    for line in content.splitlines():
        normalized = line.strip()
        if not normalized:
            continue

        lower = normalized.lower()
        if lower.startswith("safety:"):
            safety = normalized.split(":", 1)[1].strip()
        elif lower.startswith("categories:"):
            categories = normalized.split(":", 1)[1].strip()

    pred_label = ""
    if safety:
        safe_lower = safety.lower()
        if safe_lower in {"unsafe", "controversial"}:
            pred_label = "1"
        elif safe_lower == "safe":
            pred_label = "0"

    category_ids: List[str] = []
    dimensions: List[str] = []
    canonical_categories: List[str] = []

    for category_name in split_categories(categories):
        risk_id = resolve_risk_id_from_category(category_name)
        if not risk_id:
            continue

        dim, canonical = RISK_TAXONOMY[risk_id]
        if risk_id not in category_ids:
            category_ids.append(risk_id)
        if dim not in dimensions:
            dimensions.append(dim)
        if canonical not in canonical_categories:
            canonical_categories.append(canonical)

    risk_id_str = "|".join(category_ids)
    risk_dimension_str = "|".join(dimensions)
    risk_category_str = "|".join(canonical_categories)

    if not risk_id_str:
        if pred_label == "0":
            risk_id_str = "sec"
            risk_dimension_str = RISK_TAXONOMY["sec"][0]
            risk_category_str = RISK_TAXONOMY["sec"][1]
        elif pred_label == "1":
            risk_id_str = "unknown"
            risk_dimension_str = "Unknown"
            risk_category_str = "Unknown"

    return safety, categories, pred_label, risk_id_str, risk_dimension_str, risk_category_str


def sanitize_input_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return common_sanitize_input_row(row)


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
    text = row.get("text", "")
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
    guard_safety, guard_categories, pred_label, _, _, _ = parse_guard_output(guard_response)

    updated = dict(row)
    updated["检测响应"] = guard_response
    updated["安全性"] = guard_safety
    updated["风险类别原文"] = guard_categories
    true_label_raw = str(updated.get("label", "")).strip()
    updated["真实标签"] = label_to_text(true_label_raw)
    updated["预测标签"] = label_to_text(pred_label)
    is_correct = bool(pred_label and true_label_raw and pred_label == true_label_raw)
    updated["是否判断正确"] = bool_to_text(is_correct)

    if sleep_seconds > 0:
        time.sleep(sleep_seconds)

    return idx, updated


def main() -> None:
    start_time = time.perf_counter()
    script_dir = Path(__file__).resolve().parent
    default_env_path = resolve_preferred_path(".env", script_dir)
    default_input_path = resolve_preferred_path("datasets/data1.csv", script_dir)
    default_output_path = script_dir / "output" / "data1_guard_results.csv"

    parser = argparse.ArgumentParser(description="Run Qwen3Guard on a dataset CSV with OpenAI SDK.")
    parser.add_argument(
        "--input",
        default=str(default_input_path),
        help="Input CSV path with columns: text,label,difficulty,attack_type",
    )
    parser.add_argument(
        "--output",
        default=str(default_output_path),
        help="Output CSV path to write results",
    )
    parser.add_argument(
        "--markdown-output",
        default=None,
        help="Output Markdown table path, default is output csv name with .md suffix",
    )
    parser.add_argument(
        "--env-file",
        default=str(default_env_path),
        help="Path to .env file",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="OpenAI compatible base URL, e.g. http://host:port/v1 (override .env GUARD_BASE_URL)",
    )
    parser.add_argument(
        "--endpoint",
        default=None,
        help="Compatibility fallback endpoint (override .env GUARD_ENDPOINT)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key (override .env GUARD_API_KEY). For local gateways, any non-empty value can work.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name (override .env GUARD_MODEL)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="Concurrency workers (override .env GUARD_CONCURRENCY)",
    )
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    parser.add_argument("--max-token", type=int, default=20, help="Max token parameter")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds")
    parser.add_argument("--retries", type=int, default=2, help="Retry times on failure")
    parser.add_argument("--backoff", type=float, default=1.5, help="Backoff factor for retries")
    parser.add_argument("--sleep", type=float, default=0.0, help="Sleep between requests")

    args = parser.parse_args()

    load_env_by_priority(script_dir, args.env_file)

    base_url, api_key, model = resolve_guard_config(
        cli_base_url=args.base_url,
        cli_endpoint=args.endpoint,
        cli_api_key=args.api_key,
        cli_model=args.model,
    )
    concurrency = get_concurrency(args.concurrency)

    print("[ENV] GUARD_BASE_URL=", os.getenv("GUARD_BASE_URL", ""))
    print("[ENV] GUARD_ENDPOINT=", os.getenv("GUARD_ENDPOINT", ""))
    print("[ENV] GUARD_MODEL=", os.getenv("GUARD_MODEL", ""))
    print("[ENV] GUARD_API_KEY=", os.getenv("GUARD_API_KEY", ""))
    print("[ENV] GUARD_CONCURRENCY=", os.getenv("GUARD_CONCURRENCY", ""))
    print("[EFFECTIVE] base_url=", base_url)
    print("[EFFECTIVE] model=", model)
    print("[EFFECTIVE] concurrency=", concurrency)

    if not base_url:
        print(
            "Missing base URL. Set GUARD_BASE_URL (recommended) or GUARD_ENDPOINT in .env, or pass --base-url/--endpoint",
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
    summary_df = build_eval_summary_df(df=df, start_time=start_time)
    write_markdown_report(str(markdown_output_path), summary_df, df)

    print(f"Wrote CSV to {output_path} (concurrency={concurrency})")
    print(f"Wrote Markdown table to {markdown_output_path}")


if __name__ == "__main__":
    main()
