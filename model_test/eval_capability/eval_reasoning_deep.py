"""推理深度能力专项评测（Python API 版）

聚焦数学/推理硬骨头：math_500（按难度分级）+ aime25（竞赛级）
对比模式：可同时跑 thinking=true / false，便于评估 thinking 收益。

用法：
  python eval_reasoning_deep.py                  # 默认 thinking=true
  python eval_reasoning_deep.py --compare        # 同时跑两种模式
  python eval_reasoning_deep.py --datasets math_500
"""

import argparse
import datetime
import os

from evalscope import TaskConfig, run_task

from write_eval_summary import write_summary


DATASET_ARGS = {
    "math_500": {
        "few_shot_num": 0,
        "subset_list": ["Level 1", "Level 2", "Level 3", "Level 4", "Level 5"],
    },
    "gsm8k": {"few_shot_num": 0},
    # aime25 题目少，全量跑
    "aime25": {},
}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=os.getenv("MODEL_NAME", "/media/llm/Qwen/Qwen3.6-35B-A3B"))
    p.add_argument(
        "--api-url",
        default=os.getenv("API_URL") or
                f"http://{os.getenv('API_HOST', '61.49.53.41')}:{os.getenv('API_PORT', '30001')}/v1",
    )
    p.add_argument("--api-key", default=os.getenv("API_KEY", "EMPTY"))
    p.add_argument("--datasets", nargs="+",
                   default=["gsm8k", "math_500", "aime25"])
    p.add_argument("--limit", type=int, default=int(os.getenv("LIMIT", "50")))
    p.add_argument("--eval-batch-size", type=int,
                   default=int(os.getenv("EVAL_BATCH_SIZE", "16")))
    p.add_argument("--max-tokens", type=int,
                   default=int(os.getenv("MAX_TOKENS", "20000")),
                   help="thinking 链路较长，留足生成空间")
    p.add_argument("--compare", action="store_true",
                   help="同时跑 thinking=true 与 thinking=false")
    return p.parse_args()


def run_one(model, api_url, api_key, datasets, limit, batch_size,
            max_tokens, enable_thinking, work_dir):
    print(f"\n>>> enable_thinking={enable_thinking}  -> {work_dir}")
    task_cfg = TaskConfig(
        model=model,
        api_url=api_url,
        api_key=api_key,
        eval_type="openai_api",
        datasets=datasets,
        dataset_args={k: v for k, v in DATASET_ARGS.items() if k in datasets},
        limit=limit,
        eval_batch_size=batch_size,
        work_dir=work_dir,
        generation_config={
            "temperature": 0.6,
            "top_p": 0.95,
            "max_tokens": max_tokens,
            "n": 1,
            "extra_body": {
                "chat_template_kwargs": {"enable_thinking": enable_thinking},
            },
        },
    )
    result = run_task(task_cfg=task_cfg)
    write_summary(work_dir, quiet=True)
    return result


def main():
    args = parse_args()
    os.environ.setdefault("USE_MODELSCOPE_HUB", "1")
    os.environ.setdefault(
        "MODELSCOPE_CACHE",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "datasets"),
    )

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base = os.path.join(script_dir, "outputs", f"{ts}_reasoning_deep")

    print("=" * 60)
    print(f"推理深度评测  model={args.model}")
    print(f"  datasets: {args.datasets}  limit={args.limit}")
    print(f"  compare : {args.compare}")
    print("=" * 60)

    runs = [("thinking_on", True)]
    if args.compare:
        runs.append(("thinking_off", False))

    results = {}
    for run_name, enable_thinking in runs:
        try:
            results[run_name] = run_one(
                args.model, args.api_url, args.api_key, args.datasets,
                args.limit, args.eval_batch_size, args.max_tokens, enable_thinking,
                os.path.join(base, run_name),
            )
        except Exception as e:
            print(f"!!! [{run_name}] failed: {e}")
            results[run_name] = {"error": str(e)}

    print("\n" + "=" * 60)
    print("评测完成：")
    for k, v in results.items():
        print(f"  - {k}: {v}")
    print(f"\n输出根目录：{base}")


if __name__ == "__main__":
    main()
