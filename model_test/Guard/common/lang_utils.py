import re

import pandas as pd


ZH_RE = re.compile(r"[\u4e00-\u9fff]")
EN_RE = re.compile(r"[A-Za-z]")


def detect_language(text: str) -> str:
    value = str(text)
    has_zh = bool(ZH_RE.search(value))
    has_en = bool(EN_RE.search(value))

    if has_zh and has_en:
        return "中英混合"
    if has_zh:
        return "中文"
    if has_en:
        return "英文"
    return "其他"


def calc_accuracy(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return float((df["是否判断正确"] == "是").mean())
