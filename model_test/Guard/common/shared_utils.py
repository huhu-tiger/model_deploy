import os
from typing import Any, Dict


def get_concurrency(cli_concurrency: int | None, env_key: str, default: int = 1) -> int:
    if cli_concurrency is not None:
        return max(1, cli_concurrency)

    raw = os.getenv(env_key, str(default))
    try:
        value = int(raw.strip())
    except ValueError:
        value = default
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


def extract_chat_content(response_json: Dict[str, Any]) -> str:
    try:
        return str(response_json["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        return ""
