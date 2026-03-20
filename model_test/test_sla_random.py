#!/usr/bin/env python3
"""
EvalScope 压测脚本 - Random 数据集
目标: 自动寻找满足 P99 TTFT <= 2秒 的最大并发数

说明: DeepSeek-V3.2 的 tokenizer 缺少 chat_template，
      脚本会在 /tmp 创建一个补丁目录（软链接原始文件 + 注入 chat_template），
      不修改原始缓存文件。
"""

import os
import json
import shutil

# 使用 ModelScope 而不是 HuggingFace
os.environ['USE_MODELSCOPE_HUB'] = '1'
os.environ['MODELSCOPE_CACHE'] = '/root/.cache/modelscope'

# ── 修复 tokenizer chat_template（不动原始缓存）──────────────────────────
ORIG_TOKENIZER = '/root/.cache/modelscope/models/deepseek-ai/DeepSeek-V3.2'
PATCHED_TOKENIZER = '/tmp/deepseek_tokenizer_patched'

# DeepSeek / Qwen 系列通用 chat template
CHAT_TEMPLATE = (
    "{% for message in messages %}"
    "{% if message['role'] == 'system' %}"
    "<|im_start|>system\n{{ message['content'] }}<|im_end|>\n"
    "{% elif message['role'] == 'user' %}"
    "<|im_start|>user\n{{ message['content'] }}<|im_end|>\n"
    "{% elif message['role'] == 'assistant' %}"
    "<|im_start|>assistant\n{{ message['content'] }}<|im_end|>\n"
    "{% endif %}"
    "{% endfor %}"
    "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}"
)

os.makedirs(PATCHED_TOKENIZER, exist_ok=True)

# 软链接所有原始文件
for fname in os.listdir(ORIG_TOKENIZER):
    src = os.path.join(ORIG_TOKENIZER, fname)
    dst = os.path.join(PATCHED_TOKENIZER, fname)
    if not os.path.exists(dst):
        os.symlink(src, dst)

# 单独复制并注入 chat_template（覆盖软链接）
cfg_dst = os.path.join(PATCHED_TOKENIZER, 'tokenizer_config.json')
if os.path.islink(cfg_dst):
    os.unlink(cfg_dst)
with open(os.path.join(ORIG_TOKENIZER, 'tokenizer_config.json')) as f:
    cfg = json.load(f)
cfg['chat_template'] = CHAT_TEMPLATE
with open(cfg_dst, 'w') as f:
    json.dump(cfg, f, indent=2)

print(f"Patched tokenizer ready at: {PATCHED_TOKENIZER}")
# ─────────────────────────────────────────────────────────────────────────────

from evalscope.perf.main import run_perf_benchmark

print("=" * 42)
print("压测配置: Random 数据集")
print("=" * 42)
print("数据集: Random (随机生成)")
print("Tokenizer: DeepSeek-V3.2 (patched)")
print("Prompt 长度: 512-1024 tokens")
print("并发范围: 2 - 128")
print("每级请求数: 50")
print("SLA 目标: P99 TTFT <= 2秒")
print("=" * 42)

args = {
    # ── 模型与接口 ────────────────────────────────────────────────────────────
    "model": "deepseek-v3.2",           # 模型名称，需与服务端部署名一致
    "url": "http://61.49.53.5:30002/v1/chat/completions",  # 推理服务地址
    "api": "openai",                    # API 协议类型，固定 openai 兼容格式
    "dataset": "random",                # 数据集类型：random = 随机生成 prompt

    # ── Tokenizer ─────────────────────────────────────────────────────────────
    # random dataset 必须提供 tokenizer，用于将目标 token 数转换为实际文本
    # 这里使用补丁后的本地路径（注入了 chat_template，原始缓存不受影响）
    "tokenizer_path": PATCHED_TOKENIZER,
    "apply_chat_template": True,        # 是否套用 chat template 格式化消息
                                        # random dataset 必须为 True，否则请求格式错误

    # ── Input Token 长度控制 ──────────────────────────────────────────────────
    # evalscope 先生成 [min, max] 范围内的随机 token 序列，再 decode 成文本，
    # 最终发送给服务端的 input token 数 ≈ min_prompt_length ~ max_prompt_length
    # + chat_template overhead（通常几十个 token）
    #
    # 注意：随机 token decode 后 re-encode 可能有轻微偏差（±几十 token），
    # 这是 tokenizer 的正常行为，不影响压测结论。
    "min_prompt_length": 128,           # 生成 prompt 的最小 token 数（不含 template）
    "max_prompt_length": 256,          # 生成 prompt 的最大 token 数（不含 template）
    "prefix_length": 0,                 # 所有请求共享的固定前缀长度（模拟 system prompt 缓存场景）

    # ── 生成参数 ──────────────────────────────────────────────────────────────
    "max_tokens": 2048,                 # 单次请求最大输出 token 数
    "temperature": 0.1,                 # 采样温度，越低输出越确定
    "top_p": 1.0,                       # nucleus sampling 概率阈值
    "stream": True,                     # 流式输出，TTFT 指标依赖此项为 True

    # ── 请求模板 ──────────────────────────────────────────────────────────────
    "query_template": "@query_template.json",  # 请求体模板，@ 前缀表示从文件读取

    # ── SLA 自动调优 ──────────────────────────────────────────────────────────
    # evalscope 用二分法在 [sla_lower_bound, sla_upper_bound] 范围内搜索
    # 满足 sla_params 条件的最大并发数
    "sla_auto_tune": True,              # 开启 SLA 自动调优模式
    "sla_variable": "parallel",         # 调优变量：parallel（并发数）或 rate（请求速率）
    "sla_params": [{"p99_ttft": "<=2"}],# SLA 约束：P99 首字延迟 <= 2 秒
    "parallel": 2,                      # 初始并发数（二分搜索起点）
    "sla_upper_bound": 32,             # 并发数搜索上限
    "sla_lower_bound": 2,               # 并发数搜索下限
    "sla_num_runs": 3                   # 每个并发档位重复测试次数，取平均以减少抖动
}

results = run_perf_benchmark(args)
print("\n压测完成")

# ── 生成 HTML 报告 ────────────────────────────────────────────────────────────
# SLA 模式结果在 sla_tuning/ 下，需要通过 gen_report.py 的逻辑整理后生成
import glob as _glob
import subprocess
candidates = sorted(_glob.glob("./outputs/*/*"), key=os.path.getmtime, reverse=True)
output_dir = next(
    (d for d in candidates if os.path.isdir(os.path.join(d, "sla_tuning"))
     or any(s.startswith("parallel_") for s in os.listdir(d))),
    None
)
if output_dir:
    script = os.path.join(os.path.dirname(__file__), "gen_report.py")
    subprocess.run(["python3", script, output_dir], check=False)
