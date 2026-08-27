#!/usr/bin/env python3
"""上下文档位、并发与超时计算。"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Iterable, Sequence


def context_levels_k(
    max_model_len: int,
    k_unit: int = 1024,
    fractions: Sequence[float] = (1.0, 0.75, 0.5, 0.25, 0.125),
    explicit: Sequence[int] | None = None,
    cap_k: int | None = None,
    min_k: int = 8,
) -> list[int]:
    """由 max_model_len 得到测试档位（单位 K），从小到大。

    默认 fractions=(1, 0.75, 0.5, 0.25, 0.125)：
    512K 窗口 → 64 / 128 / 256 / 384 / 512。
    """
    max_k = max(1, max_model_len // k_unit)
    if cap_k:
        max_k = min(max_k, cap_k)

    if explicit:
        candidates: Iterable[int] = explicit
    else:
        candidates = [max(1, int(max_k * frac)) for frac in fractions]

    out: list[int] = []
    seen: set[int] = set()
    for k in candidates:
        if k < min_k or k in seen:
            continue
        if cap_k and k > cap_k:
            continue
        if k * k_unit > max_model_len:
            continue
        seen.add(k)
        out.append(k)
    if not out:
        raise ValueError("没有可用的上下文档位")
    out.sort()
    return out


def prompt_token_budget(max_model_len: int, max_tokens: int, reserve_tokens: int) -> int:
    return max(0, max_model_len - max_tokens - reserve_tokens)


def cap_prompt_tokens(target_tokens: int, budget: int) -> int:
    return min(target_tokens, budget) if budget > 0 else 0


def auto_parallel(
    ctx_k: int,
    override: Sequence[int] | None = None,
    median: int = 4,
    levels: Sequence[int] | None = None,
    max_parallel: int = 64,
) -> list[int]:
    """按档位相对中位数加减并发。

    配置值 ``median`` 用在档位列表的中位上下文上。
    例如档位 512,384,256,128,64 且 median=4：
    512→1, 384→2, 256→4, 128→8, 64→16。
    override 多个数字时，所有档位都用该列表（显式覆盖）。
    override 单个数字时，当作 median。
    """
    if override and len(override) > 1:
        return [max(1, int(x)) for x in override]
    if override and len(override) == 1:
        median = int(override[0])
    return [parallel_at(ctx_k, levels or [ctx_k], median, max_parallel)]


def parallel_at(
    ctx_k: int,
    levels: Sequence[int],
    median: int,
    max_parallel: int = 64,
) -> int:
    median = max(1, int(median))
    cap = max(1, int(max_parallel))
    ordered = sorted({int(x) for x in levels if int(x) > 0}, reverse=True)
    if not ordered:
        return min(cap, median)
    mid_idx = (len(ordered) - 1) // 2
    if ctx_k in ordered:
        idx = ordered.index(int(ctx_k))
    else:
        idx = min(range(len(ordered)), key=lambda i: abs(ordered[i] - int(ctx_k)))
    steps = idx - mid_idx
    if steps < 0:
        value = max(1, median // (2 ** (-steps)))
    else:
        value = median * (2 ** steps)
    return max(1, min(cap, int(value)))


def parallel_plan(
    levels: Sequence[int],
    median: int = 4,
    override: Sequence[int] | None = None,
    max_parallel: int = 64,
) -> list[tuple[int, int]]:
    """各档位实际并发（每档取列表第一个，便于打印）。"""
    out: list[tuple[int, int]] = []
    for ctx_k in levels:
        vals = auto_parallel(
            ctx_k,
            override=override,
            median=median,
            levels=levels,
            max_parallel=max_parallel,
        )
        out.append((int(ctx_k), int(vals[0])))
    return out


def auto_read_timeout(
    ctx_k: int,
    override: int | None = None,
    per_k: int = 5,
    min_s: int = 180,
    max_s: int = 1800,
) -> int:
    """读超时需覆盖长 prefill 的 TTFT。"""
    if override is not None:
        return int(override)
    return max(min_s, min(max_s, ctx_k * per_k))


def run_timeouts(
    ctx_k: int,
    parallel: int,
    n_req: int,
    read_timeout: int | None = None,
    total_timeout: int | None = None,
    duration: int | None = None,
    hard_extra: int = 90,
) -> dict[str, int]:
    read_to = auto_read_timeout(ctx_k, override=read_timeout)
    total_to = int(total_timeout) if total_timeout is not None else read_to * 2
    if duration is None:
        rounds = max(1, (n_req + parallel - 1) // max(parallel, 1))
        duration = rounds * total_to + 60
    hard_timeout = int(duration) + hard_extra
    return {
        "read_timeout": read_to,
        "total_timeout": total_to,
        "duration": int(duration),
        "hard_timeout": hard_timeout,
    }


def _parse_int_list(text: str) -> list[int]:
    if not text.strip():
        return []
    return [int(x.strip()) for x in text.replace(" ", ",").split(",") if x.strip()]


def _parse_float_list(text: str) -> list[float]:
    if not text.strip():
        return []
    return [float(x.strip()) for x in text.replace(" ", ",").split(",") if x.strip()]


def _main() -> int:
    parser = argparse.ArgumentParser(description="上下文档位 / 并发 / 超时")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_lv = sub.add_parser("levels", help="计算档位 K")
    p_lv.add_argument("--max-model-len", type=int, required=True)
    p_lv.add_argument("--k-unit", type=int, default=1024)
    p_lv.add_argument("--min-k", type=int, default=8)
    p_lv.add_argument("--cap-k", type=int, default=0)
    p_lv.add_argument("--explicit", default="", help="逗号分隔，如 128,64,32")
    p_lv.add_argument("--fractions", default="", help="逗号分隔比例，如 1,0.75,0.5,0.25,0.125")

    p_par = sub.add_parser("parallel", help="计算并发列表")
    p_par.add_argument("--ctx-k", type=int, required=True)
    p_par.add_argument("--spec", default="4", help="中位数（单个数字），或多个并发覆盖所有档位")
    p_par.add_argument("--levels", default="", help="逗号分隔档位，如 512,384,256,128,64")
    p_par.add_argument("--max-parallel", type=int, default=64)

    p_plan = sub.add_parser("plan", help="打印各档位并发")
    p_plan.add_argument("--spec", default="4")
    p_plan.add_argument("--levels", required=True)
    p_plan.add_argument("--max-parallel", type=int, default=64)

    p_to = sub.add_parser("timeouts", help="计算超时")
    p_to.add_argument("--ctx-k", type=int, required=True)
    p_to.add_argument("--parallel", type=int, required=True)
    p_to.add_argument("--n-req", type=int, required=True)
    p_to.add_argument("--read-timeout", type=int, default=0)
    p_to.add_argument("--total-timeout", type=int, default=0)
    p_to.add_argument("--duration", type=int, default=0)

    p_bd = sub.add_parser("budget", help="计算实际 prompt token 数")
    p_bd.add_argument("--max-model-len", type=int, required=True)
    p_bd.add_argument("--max-tokens", type=int, default=256)
    p_bd.add_argument("--reserve", type=int, default=512)
    p_bd.add_argument("--target-k", type=int, required=True)
    p_bd.add_argument("--k-unit", type=int, default=1024)

    args = parser.parse_args()
    try:
        if args.cmd == "levels":
            kwargs = dict(
                max_model_len=args.max_model_len,
                k_unit=args.k_unit,
                explicit=_parse_int_list(args.explicit) or None,
                cap_k=args.cap_k or None,
                min_k=args.min_k,
            )
            fracs = _parse_float_list(args.fractions)
            if fracs:
                kwargs["fractions"] = fracs
            levels = context_levels_k(**kwargs)
            print(",".join(str(x) for x in levels))
        elif args.cmd == "parallel":
            spec = _parse_int_list(args.spec)
            override = spec if len(spec) > 1 else None
            median = spec[0] if len(spec) == 1 else 4
            vals = auto_parallel(
                args.ctx_k,
                override=override,
                median=median,
                levels=_parse_int_list(args.levels) or None,
                max_parallel=args.max_parallel,
            )
            print(" ".join(str(x) for x in vals))
        elif args.cmd == "plan":
            spec = _parse_int_list(args.spec)
            override = spec if len(spec) > 1 else None
            median = spec[0] if len(spec) == 1 else 4
            levels = _parse_int_list(args.levels)
            parts = []
            for ctx_k in levels:
                vals = auto_parallel(
                    ctx_k,
                    override=override,
                    median=median,
                    levels=levels,
                    max_parallel=args.max_parallel,
                )
                parts.append(f"{ctx_k}K:{','.join(str(x) for x in vals)}")
            print(" ".join(parts))
        elif args.cmd == "timeouts":
            data = run_timeouts(
                ctx_k=args.ctx_k,
                parallel=args.parallel,
                n_req=args.n_req,
                read_timeout=args.read_timeout or None,
                total_timeout=args.total_timeout or None,
                duration=args.duration or None,
            )
            print(json.dumps(data))
        elif args.cmd == "budget":
            budget = prompt_token_budget(args.max_model_len, args.max_tokens, args.reserve)
            target = args.target_k * args.k_unit
            print(cap_prompt_tokens(target, budget))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
