# 模型能力评测（EvalScope）

基于 [EvalScope](https://github.com/modelscope/evalscope) 对 **OpenAI 兼容接口** 进行 **能力/准确率评测**（区别于父目录 `test_*.sh` 的性能压测）。

| 关注点 | 父目录脚本 | 本目录脚本 |
|--------|-----------|-----------|
| 评测对象 | 吞吐 / 延迟 / SLA | 答对率 / 推理能力 / 指令遵循 |
| 数据集 | `random` / `openqa`（任意 prompt） | `ceval` / `gsm8k` / `mmlu` / `humaneval` 等 |
| 输出 | `benchmark_*.json` / HTML 报告 | 各数据集得分 + 详细错样 |

**推荐流程**

```bash
make install          # 1. 装依赖
make check            # 2. 确认推理服务 & 模型名
make download         # 3. 预下载数据集（已缓存跳过）
make quick            # 4. 冒烟
make download-hard    # 5. 若要跑 reasoning-hard，再下 LCB
make reasoning-hard   # 6. 深度推理评测
```

## 环境

与父目录共用 `model_test` 环境，也可直接：

```bash
make install    # evalscope[all]==1.8.1 + bfcl-eval
```

或手动安装：

```bash
conda activate model_test
pip install "evalscope[all]==1.8.1"
pip install bfcl-eval==2025.10.27.1   # 工具调用评测需要
```

## 推理服务

脚本默认指向 `http://61.49.53.41:30001/v1`（可通过 `API_HOST` / `API_PORT` / `API_URL` 覆盖），对应 docker-compose 中已启动的 vLLM/SGLang OpenAI 兼容服务。

### 修改模型访问地址（三种方式）

**方式 1 ── Makefile / 环境变量（推荐）**

```bash
make quick API_HOST=10.0.0.5 API_PORT=8000 MODEL_NAME=Qwen3.6-35B-A3B
make quick API_URL=http://10.0.0.5:8000/v1          # 整段覆盖 host+port
export API_HOST=127.0.0.1 API_PORT=30001 && ./eval_quick.sh
```

**方式 2 ── 改 `.sh` 脚本默认值**

各脚本顶部变量段，已支持 `API_HOST`、`CONDA_ENV`、`MODELSCOPE_CACHE`：

```bash
API_HOST="${API_HOST:-61.49.53.41}"
API_PORT="${API_PORT:-30001}"
API_URL="${API_URL:-http://${API_HOST}:${API_PORT}/v1}"
MODELSCOPE_CACHE="${MODELSCOPE_CACHE:-${SCRIPT_DIR}/datasets}"
CONDA_ENV="${CONDA_ENV:-model_test}"
```

**方式 3 ── Python 脚本命令行**

```bash
python eval_full.py \
  --api-url http://10.0.0.5:8000/v1 \
  --model Qwen3.6-35B-A3B \
  --api-key EMPTY
```

> URL 拼装规则：`http://<host>:<port>/v1`，evalscope 内部会自动追加 `/chat/completions`。
> 查看推理服务已注册的模型名：`make check`（SGLang 通常返回模型路径作为 `id`，须与 `MODEL_NAME` 完全一致）。
> 当前默认 `MODEL_NAME=/media/llm/Qwen/Qwen3.6-35B-A3B`。

## 一键入口：Makefile

所有脚本都可通过 `make` 统一调用，参数走 `make X=Y` 透传到 shell/Python 脚本。**可在任意目录执行**，Makefile 会自动 `cd` 到脚本目录。

```bash
make help                                  # 列出全部 target
make print-config LIMIT=50 API_PORT=30000  # 看当前生效参数
make install                               # 装 evalscope + bfcl-eval
make check                                 # curl /v1/models 查注册模型
make download                              # 预下载全部常规数据集 + NLTK（已缓存跳过）
make download-hard                         # reasoning-hard 专用（含 LCB ~2.4GB）
```

### 数据集预下载

跑评测时如果出现 `SSL: UNEXPECTED_EOF_WHILE_READING` 之类错误，是直连 `www.modelscope.cn` 受限。处理方式：**先把数据集一次性下到固定目录，后续评测复用、不再走外网**。

```bash
# 常规下载（10 个 ModelScope 数据集 + NLTK，已缓存自动跳过）
make download

# reasoning-hard 专用（gpqa_diamond + aime25 + LCB release_latest ~2.4GB）
make download-hard

# 自定义
make download DL_DATASETS="AI-ModelScope/gsm8k opencompass/ifeval"  # 只下指定
make download MODELSCOPE_CACHE=/data/ms_cache                        # 放共享盘
make download HTTPS_PROXY=http://proxy:8080                         # ModelScope 也走代理
FORCE_DOWNLOAD=1 make download                                      # 强制重下（忽略缓存）
make download-nltk NLTK_PROXY=http://proxy:8080                       # 仅 NLTK
make download-zip                                                   # 官方 zip（国内 OSS）
```

**下载源与代理**

| 下载项 | 地址 | 是否国外 | 默认代理 |
|--------|------|----------|----------|
| ModelScope 数据集 | `www.modelscope.cn` | 国内 | 无（直连） |
| 官方 zip | `modelscope.oss-cn-beijing.aliyuncs.com` | 国内 | 无（直连） |
| NLTK（ifeval 分词） | `raw.githubusercontent.com` | 国外 | `NLTK_PROXY`（默认 `http://172.22.220.21:20171`） |

**机制**：
- 已缓存的数据集自动 `[SKIP]`，并打印缓存路径和大小
- 下载中每 3 秒打印 `[PROGRESS]`（目录大小 / 文件数 / 用时）；ModelScope 自身 tqdm 进度条也会显示
- `HTTPS_PROXY` **仅在 download 子进程内生效**，下载完自动清除；评测 target 不挂代理
- `MODELSCOPE_CACHE` 默认 `./datasets/`（脚本同级），便于打包迁移；NLTK 缓存通常在 `~/nltk_data`
- LiveCodeBench **不在** `make download` 默认列表中（全量 ~48GB）；需 `make download-hard`，且只下 `release_latest` 子集（~2.4GB）

**常用 target**

| target | 作用 | 对应脚本 |
|--------|------|---------|
| `make quick` | 冒烟 | `eval_quick.sh` |
| `make chinese` | 中文综合 | `eval_chinese.sh` |
| `make reasoning` | 推理基础 | `eval_reasoning.sh` |
| `make reasoning-hard` | 推理硬骨头 | `eval_reasoning_hard.sh` |
| `make reasoning-deep` | 推理深度 | `eval_reasoning_deep.py` |
| `make full` | 综合 5 维度 | `eval_full.py` |
| `make tool-v3` / `make tool-v4` | 工具调用 BFCL | `eval_tool_calling.py` |
| `make all` | quick + chinese + reasoning + tool-v3 | — |
| `make download` | 预下载常规数据集 + NLTK | — |
| `make download-hard` | 预下载 reasoning-hard（含 LCB） | — |
| `make clean` | 清理 outputs/（交互确认；非 TTY 自动执行） | — |

**传参示例**

```bash
# 基础参数
make quick API_HOST=10.0.0.5 API_PORT=8000 MODEL_NAME=Qwen3.6-35B-A3B
make quick LIMIT=50 EVAL_BATCH_SIZE=16

# Python 脚本特有参数
make full GROUPS="chinese reasoning" LIMIT=100
make full NO_THINKING=1
make reasoning-deep COMPARE=1 LIMIT=30
make tool-v4 SUBSETS="simple_python multiple" LIMIT=20
make tool-v3 NO_FC=1

# Shell 脚本特有参数
make reasoning ENABLE_THINKING=false
make reasoning-hard LCB_START=2024-08-01 LCB_END=2026-06-01
make reasoning-hard CODE_BENCH=humaneval          # 用 humaneval 替代 LCB（~几 MB）
make quick BFCL_FC_MODE=true

# 跳过数据集预检（已有缓存或允许在线拉取）
SKIP_DATASET_CHECK=1 make quick
```

**可传参数总览**

| 变量 | 适用 target | 说明 |
|------|------------|------|
| `API_HOST` | 全部 | 推理服务主机（默认 `61.49.53.41`） |
| `API_PORT` | 全部 | 推理服务端口（默认 `30001`） |
| `API_URL` | 全部 | 完整 URL，优先级高于 `API_HOST`+`API_PORT` |
| `MODEL_NAME` | 全部 | 模型名（与 `/v1/models` 注册名一致） |
| `API_KEY` | 全部 | API key |
| `LIMIT` | 全部 | 每数据集采样数（Makefile 默认 `50`） |
| `EVAL_BATCH_SIZE` | 全部 | 并发请求数（默认 `16`） |
| `ENABLE_THINKING` | quick / reasoning / reasoning-hard | `true`/`false` |
| `MAX_TOKENS` | quick / reasoning / reasoning-hard | 生成长度上限 |
| `BFCL_FC_MODE` | quick | `true`=原生 fc，`false`=prompt |
| `LCB_START` / `LCB_END` | reasoning-hard | LiveCodeBench 时间窗 |
| `LCB_SUBSET` | download-hard / reasoning-hard | LCB 子集（默认 `release_latest`） |
| `CODE_BENCH` | reasoning-hard | `live_code_bench`（默认）或 `humaneval` |
| `GROUPS` | full | 选分组，空格分隔 |
| `DATASETS` | reasoning-deep | 选数据集，空格分隔 |
| `SUBSETS` | tool-v3 / tool-v4 | BFCL 子集，空格分隔 |
| `COMPARE` | reasoning-deep | `1`=同时跑 thinking on/off |
| `NO_THINKING` | full | `1`=所有分组关 thinking |
| `NO_FC` | tool-v3 / tool-v4 | `1`=BFCL 切 prompt 模式 |
| `BFCL_VERSION` | tool-calling | `v3` 或 `v4` |
| `CONDA_ENV` | 全部 | conda 环境名（默认 `model_test`） |
| `MODELSCOPE_CACHE` | 全部 | 数据集缓存（默认 `./datasets/`） |
| `DL_DATASETS` | download | 自定义下载列表（注意不是 `DATASETS`） |
| `FORCE_DOWNLOAD` | download / download-nltk / download-zip | `1`=忽略缓存强制重下 |
| `HTTPS_PROXY` / `HTTP_PROXY` | download / download-zip | ModelScope 下载代理（默认空=直连） |
| `NLTK_PROXY` | download-nltk | NLTK 下载代理（默认见 Makefile） |
| `NO_PROXY` | download | 代理白名单（含 `API_HOST`） |
| `SKIP_DATASET_CHECK` | 评测 target | `1`=跳过数据集预检 |

## 脚本

### 1. `eval_quick.sh` — 快速冒烟（推荐先跑这个）

每个数据集默认 50 条样本（`make quick LIMIT=50`），覆盖**数学 / 指令遵循 / 硬推理 / 工具调用**四个维度。
适合上线前快速验证模型没"哑火"。

**覆盖数据集**（4 个，每集默认 20 条）：

| 数据集 | 维度 | 指标 |
|--------|------|------|
| `gsm8k` | 基础数学推理 | acc |
| `ifeval` | 指令遵循 | acc |
| `gpqa_diamond` | 研究生级科学推理（硬推理） | acc |
| `bfcl_v3` | 工具调用 / Function Calling（4 个核心子集）| acc |

> 默认开 `enable_thinking=true`、`max_tokens=8192` 兼顾推理类需求。
> BFCL 默认走 **prompt 模式**（任何 OpenAI 接口都能跑），需切原生 function call 时设 `BFCL_FC_MODE=true`，并确认服务端开了 tool parser。

```bash
./eval_quick.sh
# 自定义样本数：
LIMIT=50 EVAL_BATCH_SIZE=16 ./eval_quick.sh
# BFCL 改走原生 function call：
BFCL_FC_MODE=true ./eval_quick.sh
# 关 thinking（更快、但 gpqa 准确率会掉）：
ENABLE_THINKING=false ./eval_quick.sh
```

### 2. `eval_chinese.sh` — 中文综合能力

跑 `ceval`（52 学科）+ `cmmlu`（67 学科）。默认每数据集 100 条。

```bash
./eval_chinese.sh
LIMIT=200 ./eval_chinese.sh
```

### 3. `eval_reasoning.sh` — 推理 / 数学 / 代码

跑 `gsm8k` + `math_500`（按难度 Level 1-5）+ `humaneval`。
默认开启 `enable_thinking`，发挥思考链路：

```bash
./eval_reasoning.sh
ENABLE_THINKING=false ./eval_reasoning.sh    # 关闭 thinking 对比
```

### 4. `eval_full.py` — 综合多维度（Python API）

一次性跑五个分组（chinese / knowledge / reasoning / instruction / code），不同分组用不同生成参数。
所有结果落到同一个时间戳目录下，便于横向对比。

**覆盖数据集**（5 组共 9 个，每集默认 50 条）：

| 分组 | 数据集 | thinking | temperature | max_tokens |
|------|--------|:---:|:---:|:---:|
| **chinese** | `ceval`, `cmmlu` | off | 0.0 | 2048 |
| **knowledge** | `mmlu`, `mmlu_pro`（仅 `computer science`/`math`/`physics` 子集）| off | 0.0 | 2048 |
| **reasoning** | `gsm8k`, `math_500`（Level 1-5 全切片，0-shot）| **on** | 0.6 | 16384 |
| **instruction** | `ifeval` | off | 0.0 | 2048 |
| **code** | `humaneval` | off | 0.2 | 4096 |

```bash
python eval_full.py --limit 50
python eval_full.py --groups chinese reasoning --limit 100
python eval_full.py --no-thinking            # 全部关闭 thinking
```

> 单组耗时（参考，A800 + 50 样本）：chinese ~5 min、knowledge ~5 min、reasoning ~20 min（思考链长）、instruction ~3 min、code ~3 min。

### 5. `eval_reasoning_deep.py` — 推理深度专项

只跑硬骨头：`gsm8k` + `math_500` + `aime25`（竞赛级）。
支持 `--compare` 同时跑 thinking on/off，量化 thinking 收益：

```bash
python eval_reasoning_deep.py --compare
python eval_reasoning_deep.py --datasets math_500 --limit 50
```

### 6. `eval_reasoning_hard.sh` — 深度推理"铁三角"

业内对标 DeepSeek-R1 / QwQ / Qwen3-Thinking 那一档的推理评测组合：
`gpqa_diamond`（研究生级理科）+ `aime25`（竞赛数学）+ 代码评测（默认 `live_code_bench`）。
默认开 thinking，`max_tokens=32000`。

```bash
make reasoning-hard
make download-hard                              # 先下载（含 LCB release_latest ~2.4GB）
LIMIT=30 ./eval_reasoning_hard.sh

# LiveCodeBench 时间窗（防训练泄漏，建议取模型 cutoff 之后）
LCB_START=2024-08-01 LCB_END=2026-06-01 make reasoning-hard

# 轻量替代：用 humaneval 代替 live_code_bench（~几 MB，已在 make download 中）
CODE_BENCH=humaneval make reasoning-hard
```

> `live_code_bench` 默认只用 `release_latest` 子集，并按 `LCB_START`/`LCB_END` 过滤题目。
> 全量 LCB 仓库约 48GB（28 个历史版本），**不要**整库下载；`make download-hard` 仅拉 `release_latest/`。
> 过滤 thinking 标签：`filters: {"remove_until": "</think>"}`。

### 7. `eval_tool_calling.py` — 工具调用 / Function Calling（BFCL）

基于 Berkeley Function Calling Leaderboard（BFCL）v3 / v4 评测工具调用能力。

**前置依赖**：
```bash
pip install bfcl-eval==2025.10.27.1
```

**推理服务端要求**：
- vLLM：启动加 `--enable-auto-tool-choice --tool-call-parser hermes`（Qwen3 系列）
- SGLang：启动加 `--tool-call-parser qwen3`
- 不支持原生 function calling 的模型用 `--no-fc` 走 prompt 模式

```bash
python eval_tool_calling.py                              # bfcl_v3 + 原生 fc
python eval_tool_calling.py --version v4                 # 跑 v4（含 web_search / memory）
python eval_tool_calling.py --no-fc                      # 模型不支持 fc，走 prompt
python eval_tool_calling.py --subsets simple multiple parallel --limit 20  # 快测
python eval_tool_calling.py --version v4 --subsets web_search_base  # 需 SERPAPI_API_KEY
```

**v3 vs v4 选哪个**：
| 维度 | v3 | v4 |
|------|-----|-----|
| 单/多/并行 fc | ✅ | ✅ |
| 多语言（Java/JS） | ✅ | ✅（拆得更细） |
| 多轮（multi_turn） | ✅ | ✅ |
| Web Search | ❌ | ✅（需 SerpAPI）|
| Memory（kv/vector） | ❌ | ✅ |
| Format Sensitivity | ❌ | ✅ |
| 业务上线评测推荐 | v3 | v4（最新基线） |

## 数据集速查

### 能力维度 × 脚本覆盖矩阵

横向看脚本，纵向看能力维度，✅ = 覆盖，⭕ = 部分覆盖（仅少量样本/单数据集）。

| 能力维度 | 数据集 | `eval_quick` | `eval_chinese` | `eval_reasoning` | `eval_reasoning_deep` | `eval_reasoning_hard` | `eval_full` | `eval_tool_calling` |
|---------|--------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **中文综合** | `ceval` | | ✅ | | | | ✅ | |
| **中文综合** | `cmmlu` | | ✅ | | | | ✅ | |
| **英文知识** | `mmlu` | | | | | | ✅ | |
| **英文知识进阶** | `mmlu_pro` | | | | | | ✅ | |
| **小学数学** | `gsm8k` | ⭕ | | ✅ | ✅ | | ✅ | |
| **高难数学** | `math_500` | | | ✅ | ✅ | | ✅ | |
| **竞赛数学** | `aime25` | | | | ✅ | ✅ | | |
| **研究生级科学推理** | `gpqa_diamond` | ⭕ | | | | ✅ | | |
| **代码生成** | `humaneval` | | | ✅ | | ⭕¹ | ✅ | |
| **代码推理** | `live_code_bench` | | | | | ✅ | | |

¹ `CODE_BENCH=humaneval` 时可替代 LCB。
| **指令遵循** | `ifeval` | ⭕ | | | | | ✅ | |
| **工具调用** | `bfcl_v3` | ⭕ | | | | | | ✅ |
| **工具调用+Agent** | `bfcl_v4` | | | | | | | ✅ |

**怎么选脚本**：
- 只想 10-20 分钟内确认服务通畅（含工具调用） → `eval_quick.sh`
- 中文场景上线评测 → `eval_chinese.sh`（≥200 样本）
- 看模型整体水平 → `eval_full.py`（5 维一次跑完）
- 推理/数学专项调优 → `eval_reasoning.sh` 或 `eval_reasoning_deep.py --compare`
- 对标 R1/QwQ 那一档 → `make reasoning-hard`（需先 `make download-hard`）
- 不想下 LCB → `CODE_BENCH=humaneval make reasoning-hard`
- Agent / Function Calling 深度评测（全子集 / v4）→ `eval_tool_calling.py`

### 数据集详细说明

| 数据集 | 维度 | 语言 | 指标 | 样本量 | 说明 |
|--------|------|------|------|--------|------|
| `ceval` | 中文综合 | zh | acc | ~13.9K | 52 个中文学科 MCQ（人文/理工/社科） |
| `cmmlu` | 中文综合 | zh | acc | ~11.5K | 67 个中文学科 MCQ，比 ceval 更偏中国本土 |
| `mmlu` | 英文知识 | en | acc | ~14K | 57 学科 MCQ，5-shot |
| `mmlu_pro` | 英文知识进阶 | en | acc | ~12K | 10 选 1，干扰项更强 |
| `gsm8k` | 小学数学 | en | acc | 1319 测试 | 多步骤应用题，CoT 友好 |
| `math_500` | 高难数学 | en | acc | 500 | MATH 子集，分 Level 1-5 |
| `aime24` / `aime25` | 竞赛数学 | en | pass@1 | 30 / 年 | AIME 真题，建议 n≥4 取平均 |
| `gpqa_diamond` | 研究生级科学推理 | en | acc | 198 | 物/化/生 PhD 题目，强干扰项 |
| `bbh` | 通用推理 | en | acc | ~6.5K | BigBenchHard 23 子任务 |
| `drop` | 阅读+数值推理 | en | f1/em | ~9.5K | 段落理解 + 数值计算 |
| `arc` | 科学常识 | en | acc | ~7.7K | 小学科学 MCQ |
| `humaneval` | 代码生成 | en | pass@1 | 164 | 经典 Python 题 |
| `live_code_bench` | 代码推理 | en | pass@1 | 按时间筛 | LeetCode 风格；默认 `release_latest` 子集；全库 ~48GB |
| `ifeval` | 指令遵循 | en | acc | 541 | 可程序验证的格式/字数/关键词约束 |
| `bfcl_v3` | 工具调用 | en | acc | ~4K | 单/多/并行/多轮 fc，含 Java/JS |
| `bfcl_v4` | 工具调用+Agent | en | acc | ~5K | v3 全部 + web_search + memory + 格式敏感性 |

> 推荐补齐方向：本仓库脚本目前未覆盖 `bbh` / `drop` / `arc`（可在 `eval_full.py` 的 `GROUPS` 中按需追加），
> 中文工具调用可关注后续可能加入的 `chinese_simpleqa` / 内部 fc 数据集。

更多数据集见 [evalscope 文档](https://evalscope.readthedocs.io/zh-cn/latest/get_started/supported_dataset/llm.html)
和 [Agent benchmarks](https://evalscope.readthedocs.io/zh-cn/latest/get_started/supported_dataset/agent.html)。

## 输出结构

```
outputs/
└── 20260622_143012_full/
    ├── chinese/
    │   ├── reports/
    │   │   └── Qwen3.6-35B-A3B/
    │   │       ├── ceval.json           # 总得分
    │   │       └── cmmlu.json
    │   └── reviews/                     # 逐题详情（含错样）
    ├── reasoning/
    └── ...
```

报告关键字段：

| 字段 | 说明 |
|------|------|
| `score` | 整体准确率 |
| `subset.acc` | 各 subset（学科/难度）准确率 |
| `model_info` | 模型 + 生成参数快照 |

## 常见问题

**Q: thinking 模式应该开还是关？**
推理/数学类**开**（`enable_thinking=true`），中文知识 MCQ / 指令遵循类**关**（避免长输出影响 MCQ 解析）。
默认配置已按此设置，无须手动调。

**Q: 数据集下载慢 / 看起来卡住？**
- ModelScope 数据集走国内 `www.modelscope.cn`，默认直连，下载中会打印 `[PROGRESS]` 进度
- 启动时会打印 ModelScope ASCII logo，属正常现象
- 缓存目录默认 `./datasets/`，已下载的会自动 `[SKIP]`
- NLTK 走 GitHub，需 `NLTK_PROXY`；`make download` 末尾会自动调 `download-nltk`
- LCB 全量 ~48GB，请用 `make download-hard`（仅 `release_latest` ~2.4GB）或 `CODE_BENCH=humaneval`

**Q: limit 设多少合适？**
冒烟用 20-50；正式评测中文/知识类 ≥ 200，推理类全量（math_500/aime25 题量本身就少）。

**Q: 评测同时会不会影响线上压测？**
会。两者共用同一个推理服务，请错峰跑。
