#!/usr/bin/env python3
"""OpenAI 兼容接口：规范化 URL、读取 /v1/models。"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


def normalize_base_url(url: str) -> str:
    """接受根地址或 chat/completions 完整 URL，返回服务根（无尾斜杠）。"""
    base = (url or "").strip().rstrip("/")
    for suffix in (
        "/v1/chat/completions",
        "/chat/completions",
        "/v1/models",
        "/models",
        "/v1",
    ):
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


def models_url(base: str) -> str:
    return f"{normalize_base_url(base)}/v1/models"


def chat_completions_url(base: str) -> str:
    return f"{normalize_base_url(base)}/v1/chat/completions"


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and value > 0:
        return int(value)
    if isinstance(value, str):
        try:
            parsed = int(float(value.strip()))
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def get_max_model_len(model_info: dict[str, Any] | None) -> int | None:
    if not model_info:
        return None
    for key in ("max_model_len", "context_length", "max_input_tokens"):
        parsed = _positive_int(model_info.get(key))
        if parsed:
            return parsed
    return None


def reset_prefix_cache(base: str, api_key: str = "", timeout: float = 10.0) -> dict[str, Any]:
    """尝试清空服务端 prefix cache。不支持时返回 ok=false，不抛错。"""
    root = normalize_base_url(base)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    last_error = ""
    for path in ("/flush_cache", "/reset_prefix_cache", "/v1/reset_prefix_cache", "/reset_cache"):
        url = f"{root}{path}"
        req = urllib.request.Request(url, data=b"{}", headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return {"ok": True, "url": url, "status": int(resp.status)}
        except urllib.error.HTTPError as exc:
            last_error = f"{path} HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{path} {exc}"
    return {"ok": False, "error": last_error}


def fetch_model_info(
    base: str,
    model: str | None = None,
    api_key: str = "",
    timeout: float = 20.0,
) -> dict[str, Any]:
    """GET /v1/models。指定 model 时必须匹配到 id/name，否则报错；未指定则取第一条。"""
    url = models_url(base)
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"GET {url} HTTP {exc.code}: {body}") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"GET {url} 失败: {exc}") from exc

    items = payload.get("data") or []
    if not items:
        raise RuntimeError(f"{url} 返回空 data")

    want = (model or "").strip()
    picked = None
    if want:
        for item in items:
            if item.get("id") == want or item.get("name") == want:
                picked = item
                break
        if picked is None:
            available = [item.get("id") or item.get("name") for item in items]
            raise RuntimeError(f"未找到模型 {want!r}，可用: {available}")
    else:
        picked = items[0]

    return {
        "id": picked.get("id") or picked.get("name"),
        "max_model_len": get_max_model_len(picked),
        "raw": picked,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="读取 /v1/models")
    parser.add_argument("--base", required=True, help="服务根或 chat/completions URL")
    parser.add_argument("--model", default="", help="按 id/name 匹配，空则取第一条")
    parser.add_argument("--api-key", default="", help="Bearer Token")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--print-chat-url", action="store_true", help="只打印 chat/completions URL，不请求接口")
    parser.add_argument("--reset-cache", action="store_true", help="尝试清空 prefix cache")
    args = parser.parse_args()
    if args.print_chat_url:
        print(chat_completions_url(args.base))
        return 0
    if args.reset_cache:
        print(json.dumps(reset_prefix_cache(args.base, args.api_key, args.timeout), ensure_ascii=False))
        return 0
    try:
        info = fetch_model_info(args.base, args.model or None, args.api_key, args.timeout)
    except RuntimeError as exc:
        print(f"FETCH_FAIL: {exc}", file=sys.stderr)
        return 2
    out = {
        "id": info["id"],
        "max_model_len": info["max_model_len"],
        "raw_keys": sorted(str(k) for k in (info.get("raw") or {}).keys()),
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
