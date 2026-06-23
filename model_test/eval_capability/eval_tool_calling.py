"""工具调用 / Function Calling 能力评测（BFCL v3 / v4）

依赖：
    pip install bfcl-eval==2025.10.27.1

推理服务前提：
    - vLLM 启动需加 `--enable-auto-tool-choice --tool-call-parser hermes`
      （Qwen3 系列用 hermes parser；不同模型 parser 不同）
    - SGLang 启动需加 `--tool-call-parser qwen3`
    若服务端不支持 tool_choice，请使用 --no-fc 走 prompt 模式

用法：
    python eval_tool_calling.py                       # 默认 bfcl_v3，function call 模式
    python eval_tool_calling.py --version v4          # 跑 bfcl_v4（含 web_search/memory）
    python eval_tool_calling.py --no-fc               # 走 prompt 模式（模型不支持 fc）
    python eval_tool_calling.py --subsets simple multiple parallel  # 只跑指定子集
    python eval_tool_calling.py --limit 20            # 每子集 20 条快测
"""

import argparse
import datetime
import os

from evalscope import TaskConfig, run_task

from write_eval_summary import write_summary


# v3 / v4 默认 subset 列表
V3_SUBSETS = [
    "simple", "multiple", "parallel", "parallel_multiple",
    "irrelevance",
    "live_simple", "live_multiple", "live_parallel", "live_parallel_multiple",
    "live_irrelevance", "live_relevance",
    "multi_turn_base", "multi_turn_miss_func", "multi_turn_miss_param",
    "multi_turn_long_context",
]

V4_SUBSETS = [
    # 单语言 / 多函数
    "simple_python", "simple_java", "simple_javascript",
    "multiple", "parallel", "parallel_multiple", "irrelevance",
    # live（更新的真实样本）
    "live_simple", "live_multiple", "live_parallel",
    "live_parallel_multiple", "live_irrelevance", "live_relevance",
    # 多轮
    "multi_turn_base", "multi_turn_miss_func",
    "multi_turn_miss_param", "multi_turn_long_context",
    # 新增：web 搜索（需 SERPAPI_API_KEY）
    "web_search_base", "web_search_no_snippet",
    # 新增：记忆
    "memory_kv", "memory_vector", "memory_rec_sum",
]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=os.getenv("MODEL_NAME", "/media/llm/Qwen/Qwen3.6-35B-A3B"))
    p.add_argument(
        "--api-url",
        default=os.getenv("API_URL") or
                f"http://{os.getenv('API_HOST', '61.49.53.41')}:{os.getenv('API_PORT', '30001')}/v1",
    )
    p.add_argument("--api-key", default=os.getenv("API_KEY", "EMPTY"))
    p.add_argument("--version", choices=["v3", "v4"], default="v3")
    p.add_argument("--subsets", nargs="+", default=None,
                   help="只跑指定子集；不传则用版本默认列表")
    p.add_argument("--no-fc", action="store_true",
                   help="禁用原生 function calling，改用 prompt 模式")
    p.add_argument("--limit", type=int,
                   default=int(os.getenv("LIMIT", "0")) or None,
                   help="每子集采样数；0/不传 = 全量")
    p.add_argument("--eval-batch-size", type=int,
                   default=int(os.getenv("EVAL_BATCH_SIZE", "10")))
    p.add_argument("--max-tokens", type=int,
                   default=int(os.getenv("MAX_TOKENS", "32000")))
    # store_true/store_false 对，default=True 且可通过 --no-parallel-tool-calls 关闭
    p.add_argument("--parallel-tool-calls", dest="parallel_tool_calls",
                   action="store_true", default=True)
    p.add_argument("--no-parallel-tool-calls", dest="parallel_tool_calls",
                   action="store_false",
                   help="禁用并行工具调用")
    return p.parse_args()


def main():
    args = parse_args()
    os.environ.setdefault("USE_MODELSCOPE_HUB", "1")
    os.environ.setdefault(
        "MODELSCOPE_CACHE",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "datasets"),
    )

    dataset = f"bfcl_{args.version}"
    default_subsets = V3_SUBSETS if args.version == "v3" else V4_SUBSETS
    subsets = args.subsets or default_subsets

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    work_dir = os.path.join(script_dir, "outputs", f"{ts}_tool_{args.version}")

    extra_params = {
        # 不少模型拒绝函数名含 "."，自动转 "_"
        "underscore_to_dot": True,
        # True=原生 function call；False=用 prompt 模拟
        "is_fc_model": not args.no_fc,
    }
    # v4 的 web_search_* 需要 SERPAPI
    if args.version == "v4" and any(s.startswith("web_search") for s in subsets):
        serp = os.getenv("SERPAPI_API_KEY")
        if not serp:
            print("[WARN] 启用了 web_search 子集但未设置 SERPAPI_API_KEY，相关子集会失败")
        else:
            extra_params["SERPAPI_API_KEY"] = serp

    dataset_args = {
        dataset: {
            "subset_list": subsets,
            "extra_params": extra_params,
        }
    }

    # v4 官方提示只支持 temperature；其它参数会被忽略
    if args.version == "v4":
        gen_cfg = {"temperature": 0.0}
    else:
        gen_cfg = {
            "temperature": 0.7,
            "top_p": 0.8,
            "max_tokens": args.max_tokens,
            "parallel_tool_calls": args.parallel_tool_calls,
        }

    print("=" * 60)
    print(f"工具调用评测  dataset={dataset}  fc_mode={not args.no_fc}")
    print(f"  api     : {args.api_url}")
    print(f"  model   : {args.model}")
    print(f"  subsets : {len(subsets)} 个 -> {subsets}")
    print(f"  limit   : {args.limit or 'full'}  batch: {args.eval_batch_size}")
    print(f"  outdir  : {work_dir}")
    print("=" * 60)

    task_cfg = TaskConfig(
        model=args.model,
        api_url=args.api_url,
        api_key=args.api_key,
        eval_type="openai_api",
        datasets=[dataset],
        dataset_args=dataset_args,
        eval_batch_size=args.eval_batch_size,
        work_dir=work_dir,
        limit=args.limit,
        generation_config=gen_cfg,
        # BFCL 中有些用例本就会被模型拒绝（irrelevance），忽略错误避免整批中断
        ignore_errors=True,
        # 出错可断点续跑
        use_cache=work_dir,
    )
    result = run_task(task_cfg=task_cfg)
    write_summary(work_dir, quiet=True)
    print("\n评测完成：", result)
    print(f"结果目录：{work_dir}")


if __name__ == "__main__":
    main()
