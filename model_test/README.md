# 模型压测工具使用说明

基于 [EvalScope](https://github.com/modelscope/evalscope) 对 OpenAI 兼容接口进行性能压测，支持 SLA 自动调优和 HTML 可视化报告。

## 环境安装

```bash
conda activate model_test

pip install "evalscope[all]==1.8.1"
pip install transformers -U
pip install huggingface_hub==0.25.2

# 可选：SwanLab 可视化
pip install swanlab
pip install 'swanlab[dashboard]' -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
```

## 脚本说明

### test_sla_random.py — SLA 自动调优（Random 数据集）

随机生成指定 token 长度的 prompt，自动二分搜索满足 SLA 条件的最大并发数。压测结束后自动生成 HTML 报告。

**适用场景**：需要精确控制 input token 长度，测试特定负载下的性能边界。

```bash
python test_sla_random.py
```

关键参数（在脚本内修改）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `url` | `http://...` | 推理服务地址 |
| `min_prompt_length` | 512 | 最小 prompt token 数 |
| `max_prompt_length` | 1024 | 最大 prompt token 数 |
| `max_tokens` | 2048 | 最大输出 token 数 |
| `sla_params` | `p99_ttft <= 2` | SLA 约束条件 |
| `sla_upper_bound` | 128 | 并发数搜索上限 |
| `sla_lower_bound` | 2 | 并发数搜索下限 |
| `number` | 50 | 每档并发的请求总数 |
| `sla_num_runs` | 3 | 每档并发重复测试次数（取平均） |

> **注意**：Random 数据集生成的是随机 token 序列，decode 后实际 input token 数可能比设定值大 2-5 倍（多字节字符膨胀）。若需精确控制，按比例缩小 `min/max_prompt_length`。

---

### test_sla_openqa.sh — SLA 自动调优（OpenQA 数据集）

使用真实问答数据，无需 tokenizer，自动搜索满足 SLA 的最大并发数。

**适用场景**：测试真实对话场景下的性能边界。

```bash
./test_sla_openqa.sh
```

---

### context_bench/ — 长上下文分档压测

独立目录 `context_bench/`：从 `/v1/models` 读取 `max_model_len`，按 **全量 / 1/2 / 1/4** 切档（例如 128K → 128 / 64 / 32K），每档再扫并发。默认测 **缓存不命中**（每条前缀不同，填充汉字「测」，末尾要求连续输出数字）。正文写在 `context_bench/config/content.json`。公共方法在 `context_bench/common/`，后续脚本可直接复用。

```bash
./context_bench/test_context_sweep.sh
API_BASE=http://127.0.0.1:30001 ./context_bench/test_context_sweep.sh
PARALLEL=4 ./context_bench/test_context_sweep.sh
CONTEXT_LEVELS=64,128,256,384,512 PARALLEL=8 ./context_bench/test_context_sweep.sh
```

详见 [context_bench/README.md](context_bench/README.md)。

---

### test_openqa.sh — 基础压测（OpenQA 数据集）

对多个并发级别逐一测试，输出各级别的完整性能指标，支持 SwanLab 可视化。

**适用场景**：全面了解不同并发下的性能曲线。

```bash
./test_openqa.sh
```

并发级别和请求数在脚本内配置：

```bash
--parallel 1 2 4 8 16 32   # 测试的并发档位
--number   2 4 8 16 32 64  # 各档位对应的请求数
```

---

### gen_report.py — 生成 HTML 可视化报告

对已有压测结果目录生成交互式 HTML 报告。SLA 模式下同一并发的多个 run 自动取平均值。

```bash
# 自动找最新结果
python gen_report.py

# 指定目录
python gen_report.py outputs/20260316_110205/deepseek-v3.2
```

报告生成在指定目录下的 `perf_report.html`，用浏览器直接打开，或起临时 HTTP 服务远程访问：

```bash
python3 -m http.server 8080 --directory outputs/20260316_110205/deepseek-v3.2
# 访问 http://<服务器IP>:8080/perf_report.html
```

---

## 输出目录结构

```
outputs/
└── <timestamp>/
    └── <model_name>/
        ├── sla_tuning/                  # SLA 模式各 run 原始数据
        │   ├── sla_parallel_2_run_0/
        │   │   ├── benchmark_summary.json
        │   │   ├── benchmark_percentile.json
        │   │   ├── benchmark_args.json
        │   │   └── benchmark_data.db
        │   └── sla_parallel_4_run_0/
        ├── sla_summary.json             # SLA 调优汇总
        ├── performance_summary.txt      # 文本格式汇总
        ├── benchmark.log
        └── perf_report.html             # HTML 可视化报告（gen_report.py 生成）
```

## 报告指标说明

| 指标 | 说明 |
|------|------|
| TTFT (s) | Time To First Token，首字延迟 |
| ITL (s) | Inter-Token Latency，token 间延迟 |
| TPOT (s) | Time Per Output Token，每输出 token 耗时 |
| Latency (s) | 完整请求端到端延迟 |
| Output (tok/s) | 单请求输出吞吐 |
| Total (tok/s) | 总 token 吞吐（含输入） |
