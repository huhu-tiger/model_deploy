def label_to_text(label: str) -> str:
    normalized = str(label).strip().lower()
    if normalized == "1":
        return "风险"
    if normalized == "0":
        return "安全"
    return "未知"


def bool_to_text(flag: bool) -> str:
    return "是" if flag else "否"
