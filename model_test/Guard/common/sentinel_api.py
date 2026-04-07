import json
import time
from typing import Any, Dict, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def call_sentinel_api(
    endpoint: str,
    model: str,
    content: str,
    temperature: float,
    max_token: int,
    timeout: int,
    retries: int,
    backoff: float,
) -> Dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": temperature,
        "max_token": max_token,
    }

    data = json.dumps(payload).encode("utf-8")
    attempt = 0

    while True:
        attempt += 1
        try:
            request = Request(
                endpoint,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt > retries:
                raise exc
            time.sleep(backoff * attempt)


def parse_sentinel_output(response_json: Dict[str, Any]) -> Tuple[str, float, float, str]:
    try:
        data0 = response_json.get("data", [{}])[0]
        label = str(data0.get("label", "")).strip().lower()
        probs = data0.get("probs", [])

        safe_prob = float(probs[0]) if len(probs) > 0 else 0.0
        jailbreak_prob = float(probs[1]) if len(probs) > 1 else 0.0

        pred_label = "1" if label == "jailbreak" else "0" if label == "benign" else ""
        return label, safe_prob, jailbreak_prob, pred_label
    except Exception:
        return "", 0.0, 0.0, ""
