import time
from typing import Any

import pandas as pd

from .lang_utils import calc_accuracy, detect_language


def enrich_language(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    if "text" in result.columns:
        result["语言"] = result["text"].map(detect_language)
    else:
        result["语言"] = "其他"
    return result


def build_summary_df(
    df: pd.DataFrame,
    start_time: float,
    extra_rows: list[dict[str, Any]] | None = None,
) -> pd.DataFrame:
    work = enrich_language(df)

    zh_df = work[work["语言"] == "中文"]
    en_df = work[work["语言"] == "英文"]
    mixed_df = work[work["语言"] == "中英混合"]

    overall_acc = calc_accuracy(work)
    zh_acc = calc_accuracy(zh_df)
    en_acc = calc_accuracy(en_df)
    mixed_acc = calc_accuracy(mixed_df)

    if "difficulty" in work.columns:
        difficulty_series = work["difficulty"].astype(str).str.strip().str.lower()
        hard_acc = calc_accuracy(work[difficulty_series == "hard"])
        normal_acc = calc_accuracy(work[difficulty_series == "normal"])
    else:
        hard_acc = 0.0
        normal_acc = 0.0

    elapsed_seconds = time.perf_counter() - start_time

    rows = [
        {"指标": "运行时长", "值": f"{elapsed_seconds:.2f} 秒"},
        {"指标": "样本总数", "值": str(len(work))},
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

    if extra_rows:
        rows = [{"指标": r["指标"], "值": str(r["值"])} for r in extra_rows] + rows

    return pd.DataFrame(rows)


def build_eval_summary_df(
    df: pd.DataFrame,
    start_time: float,
    extra_rows: list[dict[str, Any]] | None = None,
) -> pd.DataFrame:
    return build_summary_df(df=df, start_time=start_time, extra_rows=extra_rows)


def write_markdown_report(markdown_path: str, summary_df: pd.DataFrame, df: pd.DataFrame) -> None:
    detail_df = enrich_language(df)
    content = "## 总结\n\n" + summary_df.to_markdown(index=False) + "\n\n## 明细表\n\n" + detail_df.to_markdown(index=False) + "\n"
    with open(markdown_path, "w", encoding="utf-8") as f:
        f.write(content)
