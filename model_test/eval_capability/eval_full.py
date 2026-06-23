"""综合能力评测（Python API 版）

相比 .sh 脚本，Python 版本可以：
- 一次跑多个分组（中文/推理/知识/指令遵循/代码），每组使用不同的生成参数
- 集中产出结果到同一个 work_dir，便于横向对比
- 灵活控制每个数据集的 subset_list / few_shot_num

环境：conda activate model_test
用法：python eval_full.py [--limit 50] [--no-thinking]
"""

import argparse
import copy
import datetime
import os

from evalscope import TaskConfig, run_task

from write_eval_summary import write_summary


# 评测分组：每组共享一份生成配置
GROUPS = {
    "chinese": {
        "datasets": ["ceval", "cmmlu"],
        "dataset_args": {},
        "generation_config": {
            "temperature": 0.0,
            "max_tokens": 2048,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        },
    },
    "knowledge": {
        "datasets": ["mmlu", "mmlu_pro"],
        "dataset_args": {
            "mmlu_pro": {"subset_list": ["computer science", "math", "physics"]},
        },
        "generation_config": {
            "temperature": 0.0,
            "max_tokens": 2048,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        },
    },
    "reasoning": {
        "datasets": ["gsm8k", "math_500"],
        "dataset_args": {
            "math_500": {
                "few_shot_num": 0,
                "subset_list": ["Level 1", "Level 2", "Level 3", "Level 4", "Level 5"],
            },
        },
        # 推理类放开温度 + thinking
        "generation_config": {
            "temperature": 0.6,
            "top_p": 0.95,
            "max_tokens": 16384,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": True}},
        },
    },
    "instruction": {
        "datasets": ["ifeval"],
        "dataset_args": {},
        "generation_config": {
            "temperature": 0.0,
            "max_tokens": 2048,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        },
    },
    "code": {
        "datasets": ["humaneval"],
        "dataset_args": {},
        "generation_config": {
            "temperature": 0.2,
            "top_p": 0.95,
            "max_tokens": 4096,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        },
    },
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
    p.add_argument("--limit", type=int, default=int(os.getenv("LIMIT", "50")),
                   help="每个数据集采样数")
    p.add_argument("--eval-batch-size", type=int,
                   default=int(os.getenv("EVAL_BATCH_SIZE", "16")))
    p.add_argument("--groups", nargs="+", default=list(GROUPS.keys()),
                   choices=list(GROUPS.keys()), help="选择要跑的分组")
    p.add_argument("--no-thinking", action="store_true",
                   help="所有分组都关闭 thinking（覆盖默认）")
    return p.parse_args()


def main():
    args = parse_args()
    os.environ.setdefault("USE_MODELSCOPE_HUB", "1")
    os.environ.setdefault(
        "MODELSCOPE_CACHE",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "datasets"),
    )

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_work_dir = os.path.join(script_dir, "outputs", f"{ts}_full")
    os.makedirs(base_work_dir, exist_ok=True)

    print("=" * 60)
    print(f"综合能力评测  model={args.model}")
    print(f"  api    : {args.api_url}")
    print(f"  groups : {args.groups}")
    print(f"  limit  : {args.limit}  batch: {args.eval_batch_size}")
    print(f"  outdir : {base_work_dir}")
    print("=" * 60)

    summary = {}
    for group in args.groups:
        cfg = GROUPS[group]
        gen_cfg = copy.deepcopy(cfg["generation_config"])
        if args.no_thinking:
            gen_cfg.setdefault("extra_body", {}).setdefault("chat_template_kwargs", {})
            gen_cfg["extra_body"]["chat_template_kwargs"]["enable_thinking"] = False

        work_dir = os.path.join(base_work_dir, group)
        print(f"\n>>> [{group}] datasets={cfg['datasets']}")
        task_cfg = TaskConfig(
            model=args.model,
            api_url=args.api_url,
            api_key=args.api_key,
            eval_type="openai_api",
            datasets=cfg["datasets"],
            dataset_args=cfg["dataset_args"],
            limit=args.limit,
            eval_batch_size=args.eval_batch_size,
            work_dir=work_dir,
            generation_config=gen_cfg,
        )
        try:
            result = run_task(task_cfg=task_cfg)
            write_summary(work_dir, quiet=True)
            summary[group] = result
            print(f"<<< [{group}] done -> {work_dir}")
        except Exception as e:  # 单个数据集失败不影响其它分组
            print(f"!!! [{group}] failed: {e}")
            summary[group] = {"error": str(e)}

    print("\n" + "=" * 60)
    print("全部分组评测完成，结果汇总：")
    for g, r in summary.items():
        print(f"  - {g}: {r}")
    print(f"\n输出根目录：{base_work_dir}")


if __name__ == "__main__":
    main()
