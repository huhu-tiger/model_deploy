import os
import time
from typing import Any, Dict
from urllib.parse import urlparse

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError


def normalize_base_url(base_url: str | None, endpoint: str | None) -> str:
    if base_url:
        return base_url.rstrip("/")

    if not endpoint:
        return ""

    parsed = urlparse(endpoint)
    if not parsed.scheme or not parsed.netloc:
        return ""

    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")]
    elif path.endswith("/completions"):
        path = path[: -len("/completions")]

    return f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/")


def resolve_guard_config(
    cli_base_url: str | None,
    cli_endpoint: str | None,
    cli_api_key: str | None,
    cli_model: str | None,
) -> tuple[str, str, str]:
    endpoint = cli_endpoint or os.getenv("GUARD_ENDPOINT")
    base_url = normalize_base_url(cli_base_url or os.getenv("GUARD_BASE_URL"), endpoint)
    api_key = cli_api_key or os.getenv("GUARD_API_KEY", "dummy")
    model = cli_model or os.getenv("GUARD_MODEL", "Qwen3Guard-Gen-8B")
    return base_url, api_key, model


def call_guard_api(
    client: OpenAI,
    model: str,
    content: str,
    temperature: float,
    max_token: int,
    retries: int,
    backoff: float,
) -> Dict[str, Any]:
    attempt = 0
    while True:
        attempt += 1
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": content}],
                temperature=temperature,
                max_tokens=max_token,
                extra_body={"max_token": max_token},
            )
            return response.model_dump()
        except (APIConnectionError, APITimeoutError, RateLimitError, APIError) as exc:
            if attempt > retries:
                raise exc
            time.sleep(backoff * attempt)
