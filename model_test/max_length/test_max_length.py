#!/usr/bin/env python3
"""按字数阶梯探测 OpenAI 兼容接口的最大输入 / 输出长度（16K→32K→…→512K，报错即停）。"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass
class ProbeResult:
    ok: bool
    status: int | None
    error: str | None
    usage: dict[str, int] | None
    elapsed_s: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按字数阶梯测试模型 API 最大输入/输出（不用 tokenizer）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--url", required=True, help="chat/completions 完整 URL")
    parser.add_argument("--model", required=True, help="模型名称")
    parser.add_argument("--api-key", default="", help="Bearer API Key，空则不带 Authorization")
    parser.add_argument(
        "--extra-body",
        default="{}",
        help='附加 JSON 请求体，如 \'{"chat_template_kwargs":{"enable_thinking":false}}\'',
    )
    parser.add_argument("--timeout", type=float, default=600.0, help="单次请求超时（秒）")
    parser.add_argument("--start-k", type=int, default=16, help="输入起始档位（K），如 128 表示 128K 字")
    parser.add_argument("--max-k", type=int, default=512, help="输入最大档位（K），如 512 表示 512K 字")
    parser.add_argument(
        "--step-k",
        type=int,
        default=0,
        help="输入步进档位（K）；0=翻倍（16→32→64→…），正整数=等步进（如 16 表示每次 +16K）",
    )
    parser.add_argument(
        "--output-start-k",
        type=int,
        default=0,
        help="输出探测起始档位（K），0 表示与 --start-k 相同",
    )
    parser.add_argument(
        "--output-max-k",
        type=int,
        default=0,
        help="输出探测最大档位（K），0 表示与 --max-k 相同",
    )
    parser.add_argument(
        "--k-unit",
        type=int,
        default=1024,
        help="1K 对应的字符数，1024=二进制 K，1000=十进制 K",
    )
    parser.add_argument(
        "--probe-output-tokens",
        type=int,
        default=8,
        help="测最大输入时请求的 max_tokens",
    )
    parser.add_argument(
        "--auto-cap-max-k",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="根据 max_model_len 自动压低输入探测上限（汉字约 1 字≈1 token）",
    )
    parser.add_argument("--skip-input", action="store_true", help="跳过最大输入测试")
    parser.add_argument("--skip-output", action="store_true", help="跳过最大输出测试")
    parser.add_argument(
        "--joint-input-k",
        type=int,
        default=0,
        help="联合测试：固定该 K 字输入，探测最大输出；0=不做联合测试（如 192 表示固定 192K 字输入）",
    )
    parser.add_argument(
        "--fetch-model-info",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="尝试从 /v1/models 读取服务端声明的上下文信息",
    )
    return parser.parse_args()


def step_sizes(start_k: int, max_k: int, k_unit: int, step_k: int = 0) -> Iterator[tuple[int, int]]:
    """返回 (档位 K, 字符数或 max_tokens)。step_k=0 时翻倍，>0 时等步进。"""
    k = start_k
    while k <= max_k:
        yield k, k * k_unit
        if step_k > 0:
            k += step_k
        else:
            k *= 2


def format_k(k: int) -> str:
    return f"{k}K"


def build_content_chars(n_chars: int) -> str:
    unit = "测"
    if n_chars <= 0:
        return ""
    reps = (n_chars + len(unit) - 1) // len(unit)
    content = unit * reps
    return content[:n_chars]


def messages_for(content: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": content}]


def chat_completion(
    url: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    api_key: str,
    extra_body: dict[str, Any],
    timeout: float,
) -> ProbeResult:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": False,
    }
    payload.update(extra_body)

    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            elapsed = time.perf_counter() - started
            obj = json.loads(raw)
            usage = obj.get("usage") or {}
            return ProbeResult(
                ok=True,
                status=resp.status,
                error=None,
                usage={
                    "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                    "completion_tokens": int(usage.get("completion_tokens", 0)),
                    "total_tokens": int(usage.get("total_tokens", 0)),
                },
                elapsed_s=elapsed,
            )
    except urllib.error.HTTPError as exc:
        elapsed = time.perf_counter() - started
        body = exc.read().decode("utf-8", errors="replace")
        return ProbeResult(
            ok=False,
            status=exc.code,
            error=body,
            usage=None,
            elapsed_s=elapsed,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - started
        return ProbeResult(
            ok=False,
            status=None,
            error=str(exc),
            usage=None,
            elapsed_s=elapsed,
        )


def fetch_model_info(url: str, model: str, api_key: str, timeout: float) -> dict[str, Any] | None:
    if "/v1/chat/completions" not in url:
        return None
    models_url = url.rsplit("/v1/chat/completions", 1)[0] + "/v1/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(models_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=min(timeout, 30)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    for item in data.get("data") or []:
        if item.get("id") == model or item.get("name") == model:
            return item
    if data.get("data"):
        return data["data"][0]
    return None


def parse_api_error(error: str | None) -> dict[str, Any]:
    if not error:
        return {}
    try:
        obj = json.loads(error)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    return {"message": error}


def print_fail(result: ProbeResult) -> None:
    err = parse_api_error(result.error)
    message = str(err.get("message") or result.error or "")[:240].replace("\n", " ")
    print(f"  FAIL  status={result.status}  {message}")


def get_max_model_len(model_info: dict[str, Any] | None) -> int | None:
    if not model_info:
        return None
    for key in ("max_model_len", "context_length", "max_input_tokens"):
        value = model_info.get(key)
        if isinstance(value, int) and value > 0:
            return value
    return None


def cap_input_max_k(
    max_k: int,
    start_k: int,
    k_unit: int,
    model_info: dict[str, Any] | None,
    probe_output_tokens: int,
    enabled: bool,
) -> int:
    if not enabled:
        return max_k
    max_model_len = get_max_model_len(model_info)
    if not max_model_len:
        return max_k
    # 填充用汉字时约 1 字≈1 token，再预留 suffix 与 max_tokens 余量
    reserve_tokens = probe_output_tokens + 512
    cap_chars = max(max_model_len - reserve_tokens, start_k * k_unit)
    cap_k = max(start_k, cap_chars // k_unit)
    if cap_k < max_k:
        print(
            f"\n[提示] max_model_len={max_model_len}，汉字约 1字≈1token，"
            f"输入探测上限 {format_k(max_k)} 自动调整为 {format_k(cap_k)}"
        )
        return cap_k
    return max_k


def probe_input_steps(
    args: argparse.Namespace,
    extra_body: dict[str, Any],
) -> dict[str, Any]:
    step_desc = f"+{args.step_k}K" if args.step_k > 0 else "翻倍"
    print(
        f"\n[输入] 阶梯探测 {format_k(args.start_k)} → {format_k(args.max_k)}"
        f"（步进: {step_desc}，约 {args.k_unit} 字/K），报错即停"
    )
    last_ok: dict[str, Any] | None = None
    fail_at: dict[str, Any] | None = None

    for k, n_chars in step_sizes(args.start_k, args.max_k, args.k_unit, args.step_k):
        content = build_content_chars(n_chars)
        suffix = "\n请只回复 OK。"
        result = chat_completion(
            url=args.url,
            model=args.model,
            messages=messages_for(content + suffix),
            max_tokens=args.probe_output_tokens,
            api_key=args.api_key,
            extra_body=extra_body,
            timeout=args.timeout,
        )

        if result.ok:
            usage = result.usage or {}
            row = {
                "step_k": k,
                "approx_chars": n_chars,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "elapsed_s": round(result.elapsed_s, 2),
            }
            last_ok = row
            print(
                f"  {format_k(k):>6}  (~{n_chars:>7} 字)  OK  "
                f"prompt_tokens={row['prompt_tokens']:<7}  elapsed={result.elapsed_s:.1f}s"
            )
        else:
            err = parse_api_error(result.error)
            fail_at = {
                "step_k": k,
                "approx_chars": n_chars,
                "status": result.status,
                "error_message": err.get("message"),
            }
            print(f"  {format_k(k):>6}  (~{n_chars:>7} 字)  ", end="")
            print_fail(result)
            if last_ok and err.get("message"):
                print(
                    f"  [说明] 本档约 {n_chars} 字，服务端报错；"
                    f"上一档 {format_k(last_ok['step_k'])} 约 "
                    f"{last_ok['prompt_tokens']} tokens 仍可用"
                )
            break

    return {
        "last_ok": last_ok,
        "fail_at": fail_at,
        "max_input_approx_chars": (last_ok or {}).get("approx_chars"),
        "max_input_prompt_tokens": (last_ok or {}).get("prompt_tokens"),
    }


def probe_output_steps(
    args: argparse.Namespace,
    extra_body: dict[str, Any],
    start_k: int,
    max_k: int,
) -> dict[str, Any]:
    print(f"\n[输出] 阶梯探测 max_tokens {format_k(start_k)} → {format_k(max_k)}，报错即停")
    last_ok: dict[str, Any] | None = None
    fail_at: dict[str, Any] | None = None
    short_input = "请从 1 开始连续输出数字，每个数字一行，尽量多输出。"

    for k, max_tokens in step_sizes(start_k, max_k, args.k_unit, args.step_k):
        result = chat_completion(
            url=args.url,
            model=args.model,
            messages=messages_for(short_input),
            max_tokens=max_tokens,
            api_key=args.api_key,
            extra_body=extra_body,
            timeout=args.timeout,
        )

        if result.ok:
            usage = result.usage or {}
            row = {
                "step_k": k,
                "max_tokens": max_tokens,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "elapsed_s": round(result.elapsed_s, 2),
            }
            last_ok = row
            print(
                f"  {format_k(k):>6}  (max_tokens={max_tokens:<7})  OK  "
                f"completion_tokens={row['completion_tokens']:<7}  elapsed={result.elapsed_s:.1f}s"
            )
        else:
            fail_at = {"step_k": k, "max_tokens": max_tokens, "status": result.status}
            print(f"  {format_k(k):>6}  (max_tokens={max_tokens:<7})  ", end="")
            print_fail(result)
            break

    return {
        "last_ok": last_ok,
        "fail_at": fail_at,
        "max_output_max_tokens": (last_ok or {}).get("max_tokens"),
        "max_output_completion_tokens": (last_ok or {}).get("completion_tokens"),
    }


def probe_output_with_fixed_input(
    args: argparse.Namespace,
    extra_body: dict[str, Any],
    fixed_input_k: int,
    max_model_len: int | None,
) -> dict[str, Any]:
    """固定 fixed_input_k K 字的输入，阶梯探测最大 max_tokens。"""
    n_chars = fixed_input_k * args.k_unit
    content = build_content_chars(n_chars) + "\n请从 1 开始连续输出数字，每个数字一行，尽量多输出。"

    # 先发一次探针确认输入能过，并获取 prompt_tokens
    probe = chat_completion(
        url=args.url,
        model=args.model,
        messages=messages_for(content),
        max_tokens=8,
        api_key=args.api_key,
        extra_body=extra_body,
        timeout=args.timeout,
    )
    if not probe.ok:
        err = parse_api_error(probe.error)
        print(
            f"\n[联合] 固定输入 {format_k(fixed_input_k)} 探针失败: "
            f"status={probe.status}  {err.get('message', '')}"
        )
        return {"fixed_input_k": fixed_input_k, "error": err.get("message")}

    actual_prompt_tokens = (probe.usage or {}).get("prompt_tokens", n_chars)

    # 理论剩余
    if max_model_len:
        theory_remain = max_model_len - actual_prompt_tokens
    else:
        theory_remain = None

    print(
        f"\n[联合] 固定输入 {format_k(fixed_input_k)} (~{n_chars} 字)，"
        f"prompt_tokens={actual_prompt_tokens}"
    )
    if theory_remain is not None:
        print(f"       理论最大输出 = {max_model_len} - {actual_prompt_tokens} = {theory_remain} tokens")

    # 确定输出探测上限
    upper = theory_remain if theory_remain and theory_remain > 0 else 65536
    # 对齐到 1K
    upper_k = max(1, upper // args.k_unit)
    start_k = max(1, upper_k // 4)   # 从上限 1/4 处开始
    print(f"       阶梯探测 max_tokens: {format_k(start_k)} → {format_k(upper_k)}，步进=翻倍")

    last_ok: dict[str, Any] | None = None
    fail_at: dict[str, Any] | None = None
    for k, max_tokens in step_sizes(start_k, upper_k, args.k_unit, 0):
        result = chat_completion(
            url=args.url,
            model=args.model,
            messages=messages_for(content),
            max_tokens=max_tokens,
            api_key=args.api_key,
            extra_body=extra_body,
            timeout=args.timeout,
        )
        if result.ok:
            usage = result.usage or {}
            row = {
                "step_k": k,
                "max_tokens": max_tokens,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "elapsed_s": round(result.elapsed_s, 2),
            }
            last_ok = row
            print(
                f"  {format_k(k):>6}  (max_tokens={max_tokens:<7})  OK  "
                f"completion_tokens={row['completion_tokens']:<7}  elapsed={result.elapsed_s:.1f}s"
            )
        else:
            err = parse_api_error(result.error)
            fail_at = {"step_k": k, "max_tokens": max_tokens, "status": result.status,
                       "error_message": err.get("message")}
            print(f"  {format_k(k):>6}  (max_tokens={max_tokens:<7})  ", end="")
            print_fail(result)
            break

    result_summary = {
        "fixed_input_k": fixed_input_k,
        "actual_prompt_tokens": actual_prompt_tokens,
        "theory_max_output_tokens": theory_remain,
        "last_ok": last_ok,
        "fail_at": fail_at,
        "max_output_max_tokens": (last_ok or {}).get("max_tokens"),
        "max_output_completion_tokens": (last_ok or {}).get("completion_tokens"),
    }

    if last_ok:
        print(
            f"\n>>> [联合] 输入 {format_k(fixed_input_k)} 时最大输出: "
            f"max_tokens={last_ok['max_tokens']}，"
            f"实际 completion_tokens={last_ok['completion_tokens']}"
        )
        if theory_remain:
            print(f"    理论值 {theory_remain} tokens，实测最大档位 {last_ok['max_tokens']}")

    return result_summary


def main() -> int:
    args = parse_args()
    try:
        extra_body = json.loads(args.extra_body)
        if not isinstance(extra_body, dict):
            raise ValueError("extra-body 必须是 JSON object")
    except json.JSONDecodeError as exc:
        print(f"extra-body JSON 解析失败: {exc}", file=sys.stderr)
        return 2

    print("=" * 60)
    print("最大输入/输出长度探测（字数阶梯，无 tokenizer）")
    print("=" * 60)
    print(f"URL:      {args.url}")
    print(f"Model:    {args.model}")
    output_start_k = args.output_start_k or args.start_k
    output_max_k = args.output_max_k or args.max_k
    step_desc = f"+{args.step_k}K" if args.step_k > 0 else "翻倍"
    print(f"输入阶梯: {format_k(args.start_k)} → {format_k(args.max_k)}，步进={step_desc}，×{args.k_unit} 字/K")
    print(f"输出阶梯: {format_k(output_start_k)} → {format_k(output_max_k)}，步进={step_desc}，×{args.k_unit}")
    print("说明:     填充汉字「测」约 1 字≈1 token，字数档位仅作粗估")

    model_info: dict[str, Any] | None = None
    if args.fetch_model_info:
        model_info = fetch_model_info(args.url, args.model, args.api_key, args.timeout)
        if model_info:
            print("\n[/v1/models 信息]")
            for key in ("id", "max_model_len", "context_length"):
                if key in model_info:
                    print(f"  {key}: {model_info[key]}")

    input_max_k = cap_input_max_k(
        args.max_k,
        args.start_k,
        args.k_unit,
        model_info,
        args.probe_output_tokens,
        args.auto_cap_max_k,
    )

    summary: dict[str, Any] = {
        "url": args.url,
        "model": args.model,
        "input_step_plan": [
            format_k(k) for k in _k_values(args.start_k, input_max_k, args.step_k)
        ],
        "output_step_plan": [
            format_k(k) for k in _k_values(output_start_k, output_max_k, args.step_k)
        ],
        "k_unit": args.k_unit,
        "max_model_len": get_max_model_len(model_info),
    }

    if not args.skip_input:
        input_args = argparse.Namespace(**{**vars(args), "max_k": input_max_k})
        input_result = probe_input_steps(input_args, extra_body)
        summary["input"] = input_result
        if input_result["last_ok"]:
            max_len = get_max_model_len(model_info)
            print(
                f"\n>>> 最大输入（本脚本阶梯）: {format_k(input_result['last_ok']['step_k'])} "
                f"(约 {input_result['last_ok']['approx_chars']} 字, "
                f"prompt_tokens={input_result['last_ok']['prompt_tokens']})"
            )
            if max_len:
                print(
                    f"    模型 context 上限 {max_len} tokens，"
                    f"粗估还可再增大约 {max_len - input_result['last_ok']['prompt_tokens']} tokens"
                )
        else:
            print("\n>>> 最大输入: 首档即失败")

    if not args.skip_output:
        output_result = probe_output_steps(args, extra_body, output_start_k, output_max_k)
        summary["output"] = output_result
        if output_result["last_ok"]:
            print(
                f"\n>>> 最大输出（短输入）: {format_k(output_result['last_ok']['step_k'])} "
                f"(max_tokens={output_result['last_ok']['max_tokens']}, "
                f"completion_tokens={output_result['last_ok']['completion_tokens']})"
            )
        else:
            print("\n>>> 最大输出（短输入）: 首档即失败")

    if args.joint_input_k > 0:
        joint_result = probe_output_with_fixed_input(
            args,
            extra_body,
            args.joint_input_k,
            get_max_model_len(model_info),
        )
        summary["joint"] = joint_result

    print("\n" + "=" * 60)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("=" * 60)
    return 0


def _k_values(start_k: int, max_k: int, step_k: int = 0) -> list[int]:
    out: list[int] = []
    k = start_k
    while k <= max_k:
        out.append(k)
        k = k + step_k if step_k > 0 else k * 2
    return out


if __name__ == "__main__":
    raise SystemExit(main())
