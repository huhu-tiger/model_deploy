# 长上下文压测（context_bench）

独立目录：从接口读取最大上下文，按档位 + 并发压测。默认只跑 **缓存不命中**（每条前缀不同）。公共方法在 `common/`，后续新脚本直接复用。

## 目录

```
context_bench/
├── test_context_sweep.sh   # 长上下文分档压测入口
├── config/content.json     # 测试正文、填充、前缀模式（命中/不命中）
├── common/                 # 公共方法（Python + Shell）
│   ├── api.py              # /v1/models、URL 规范化
│   ├── context.py          # 档位 / 并发 / 超时 / prompt 预算
│   ├── config.py           # 读取 content.json
│   ├── prompts.py          # 按配置生成 prompt
│   ├── report.py           # 汇总表格 + HTML/PNG 图表
│   ├── env.sh              # conda 激活、log/die
│   └── timeout.sh          # 进程硬超时
└── outputs/                # 运行结果
```

## 跑压测

```bash
cd model_test/context_bench
./test_context_sweep.sh

API_BASE=http://127.0.0.1:30001 ./test_context_sweep.sh
PARALLEL=4 ./test_context_sweep.sh
CONTEXT_LEVELS=64,128,256,384,512 PARALLEL=4 ./test_context_sweep.sh

# 只跑不命中（默认）/ 需要对照时再开命中
PREFIX_MODES=cache_miss ./test_context_sweep.sh
PREFIX_MODES=cache_hit ./test_context_sweep.sh

# 自定义正文配置
CONFIG=/path/to/content.json ./test_context_sweep.sh
```

环境变量见脚本头部注释。默认 `API_BASE=http://127.0.0.1:30001`。压测会激活 conda 环境 `model_test`（evalscope + pandas/matplotlib/pyecharts 出图）。Ctrl+C 也会写汇总。

跑完后在输出目录生成：

| 文件 | 说明 |
|------|------|
| `report.html` | 汇总表 + matplotlib 静态总览图 + pyecharts 交互图（ECharts 走国内 CDN `assets.pyecharts.org`） |
| `summary.md` | Markdown 表格 |
| `summary.json` | 原始汇总 |
| `content.json` | 本次使用的正文配置副本 |
| `charts/overview.png` | matplotlib 中文静态总览图 |
| `charts/overview.html` | pyecharts（Apache ECharts）交互图独立页面 |

终端只保留进度与一行指标；不打印评测表格，不生成 SwanLab / HTML 图表（`SWANLAB=1` 可打开 SwanLab）。

## 档位与并发

默认按窗口切 **全量 / 3/4 / 1/2 / 1/4 / 1/8**，**从大到小**测（先 512K×1，最后才是 64K 高并发）。512K 模型即 **512 → 384 → 256 → 128 → 64**。

`PARALLEL`（默认 `2`）是**中位档**的并发：

| 上下文 | 64K | 128K | **256K** | 384K | 512K |
|--------|-----|------|----------|------|------|
| 并发   | 8   | 4    | **2**    | 1    | 1    |

更大上下文每档减半，更小每档加倍，下限 1、上限 `PARALLEL_MAX`（默认 16，对齐常见 `--max-num-seqs`）。每档请求数 = `parallel × number_mult`，再封顶 `number_max`（默认 2×、最多 16 条）。

```bash
PARALLEL=2 ./test_context_sweep.sh          # 中位档并发 2（默认）
PARALLEL=4 ./test_context_sweep.sh          # 中位档 4 → 64K 会到 16，易顶满引擎
PARALLEL="1 2 4" ./test_context_sweep.sh    # 所有档位都扫 1/2/4
```

## 缓存：默认不命中

与 `max_length` 一样用汉字「测」铺满（约 1 字 ≈ 1 token）。生成指令放在**填充前后各一次**，避免超长正文把任务淹没。测下一档前会尝试清空服务端 prefix cache（不支持则跳过）。

每条请求开头有一段独立前缀（默认 256 字），正文再按条打戳，避免 prefix cache 命中。`cache_hit` 在配置里默认关闭；要对对照再设 `enabled: true` 或 `PREFIX_MODES=cache_hit`。

| 模式 | 前缀 | warmup | 默认 | 预期 |
|------|------|--------|------|------|
| `cache_miss` | 每条开头不同（`unique`），正文打戳 | 0 | 开启 | prefix cache **不命中** |
| `cache_hit` | 长前缀相同（`shared`），仅尾部少量不同 | 1 | 关闭 | 预热后命中 |

## 配置文件 `config/content.json`

测试上下文的正文、填充和前缀策略都写在这里，不必改脚本。

| 字段 | 说明 |
|------|------|
| `fill_text` | 循环铺满的正文（优先于 `fill_char`）；默认空，与 max_length 一样用「测」 |
| `fill_char` | `fill_text` 为空时用单字填充，默认 `测` |
| `prefix_file` | 相对配置文件目录的文本路径；非空则用文件内容循环铺满（优先于 `fill_text`） |
| `suffix` | 生成指令，会放在填充前和填充后各一次 |
| `number_mult` | 每档请求数 = 并发 × 该值，默认 `2` |
| `number_max` | 单档请求数上限，默认 `16` |
| `unique_head_chars` | 不命中模式下开头差异长度 |
| `unique_tail_chars` | 命中模式下尾部差异长度 |
| `stamp_interval` | 不命中模式下正文打戳间隔（字符） |
| `parallel` | 中位档并发，默认 `2`（512K 时 256K 用 2，更大减半、更小加倍） |
| `parallel_max` | 并发上限，默认 `16` |
| `context_fractions` | 档位比例，默认 `1, 0.75, 0.5, 0.25, 0.125`（512K → 512/384/256/128/64） |
| `context_levels` | 显式档位，空则按 fractions 自动切 |
| `min_context_k` | 最小档位 K |
| `max_tokens` / `reserve_tokens` | 输出长度、窗口预留 |
| `modes` | 前缀模式列表 |

改完 `fill_text` 或 `prefix_file` 即可换测试内容；用 `PREFIX_MODES` 只跑其中一种模式。

## 给后续脚本复用 common

### Shell

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common/env.sh"
source "${SCRIPT_DIR}/common/timeout.sh"

activate_model_test_env          # 仅当需要 evalscope 时
log "查询模型"
python3 "${COMMON_PY}/api.py" --base "${API_BASE}"
run_with_timeout 600 evalscope perf ...
```

### Python

```python
from common.api import fetch_model_info, chat_completions_url
from common.context import context_levels_k, auto_parallel, run_timeouts
from common.prompts import write_prompts, write_filler_prompts
from common.config import load_content_config, enabled_modes

info = fetch_model_info("http://127.0.0.1:30001")
levels = context_levels_k(info["max_model_len"])  # 例如 512, 384, 256, 128, 64
cfg = load_content_config("config/content.json")
```

命令行：

```bash
python3 common/api.py --base http://127.0.0.1:30001
python3 common/context.py levels --max-model-len 524288
python3 common/context.py plan --levels 64,128,256,384,512 --spec 4
python3 common/context.py parallel --ctx-k 256 --levels 64,128,256,384,512 --spec 4
python3 common/config.py --config config/content.json modes
python3 common/prompts.py --path /tmp/p.txt --n-chars 32768 --n-req 4 --mode cache_miss
python3 common/prompts.py --path /tmp/p.txt --n-chars 32768 --n-req 4 --mode cache_hit
```
