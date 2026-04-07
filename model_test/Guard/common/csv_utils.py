from typing import Any, Dict


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
