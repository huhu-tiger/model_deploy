# Qwen3.6-35B-A3B  AWQ-4bit 量化

本目录提供将 Qwen3.6-35B-A3B（BF16 完整权重）量化为 AWQ-4bit 的脚本，
基于 `llmcompressor` 实现，参考 [cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit](https://modelscope.cn/models/cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit) 的量化方法。

通用逻辑（GPU 预选 / 校准集解析 / AWQ recipe / 日志）已抽到
[`../llmcompressor_common`](../llmcompressor_common) 公共库。

## 目录结构

```
Qwen3.6-35B-A3B-AWQ/
├── README.md                    # 本文档
├── quantize_llmcompressor.py    # 量化主脚本
├── eval_quantized.py            # 量化质量评测
├── docker-compose-quantize.yml  # Docker Compose 启动
├── run_quantize.sh              # 一键运行脚本
├── requirements.txt             # Python 依赖（非镜像运行时使用）
└── logs/                        # 运行日志（自动创建,Tee 捕获 stdout+stderr,
                                 #  文件名 {时间戳}_{模型名}_awq.log）

../llmcompressor_common/         # 公共函数库（被本脚本通过 sys.path 注入引用）
├── gpu_select.py                # GPU 预选 + 信息打印
├── calib_dataset.py             # 校准集别名/解析/下载/混合
├── recipe.py                    # AWQ recipe + MODEL_IGNORE_PRESETS["qwen3_5_moe"]
├── memory.py                    # 内存/磁盘工具
└── logging_utils.py             # Tee 日志
```

## 模型信息

| 项目 | 值 |
|------|-----|
| 模型架构 | `Qwen3_5MoeForConditionalGeneration` (`qwen3_5_moe`) |
| 层类型 | 混合：linear_attention × 3 + full_attention × 1，共 40 层 |
| 专家数 | **256 个专家**,每 token 激活 8 个 |
| 原始精度 | BF16,约 70 GB |
| 量化目标 | W4A16_ASYM AWQ,约 20~24 GB |
| 量化方法 | `llmcompressor` AWQModifier + QuantizationModifier,配合校准数据 |
| 源权重路径 | `/media/llm/Qwen/Qwen3.6-35B-A3B` |
| 输出路径 | `/media/llm/Qwen/Qwen3.6-35B-A3B-AWQ-4bit` |

## 硬件需求

- **GPU**: 1 张 A800 / H800 80 GB 即可(单卡 sequential offload 模式)
- **内存**: ≥ 256 GB（模型常驻 CPU,需要 ~150 GB 余量给 activation cache）
- **磁盘**: 源权重 ~70 GB + 输出 ~24 GB,预留 ≥ 120 GB
- **预期耗时**: **4~8 小时**(单卡 sequential,256 expert MoE 校准慢)
- **Docker 镜像**: `model.vnet.com/sjhl/vllm-openai:v0.23.0-llmcompressor`
  - 基于 vLLM v0.23.0,已预装 `llmcompressor==0.12.0` / `datasets==5.0.0` / `accelerate==1.13.0`
  - 构建脚本: [`../llmcompressor-docker/build.sh`](../llmcompressor-docker/build.sh)

## ⚠️ 执行模式说明(关键)

Qwen3.6-35B-A3B 是 **256 个专家的 MoE 模型**。AWQ 量化在这种规模下的核心约束:

| 模式 | 状态 | 速度 | 稳定性 | GPU 利用 |
|------|------|------|--------|---------|
| **单卡 sequential offload**(默认) | ✅ 稳定 | 4~8 小时 | ⭐⭐⭐⭐⭐ | 只用 cuda:0 |
| **多卡 device_map**(实验性) | ❌ 会 OOM | 1~2 小时(理想) | ⭐ | 所有可见 GPU |

### 为什么默认走单卡 sequential offload?

llmcompressor 0.12.0 的 AWQ 在 256 expert 大 MoE 上,有两个不可忽视的特性:

1. **每个 expert 的 forward 都会触发 `cache_parent_kwargs_hook`**,累积 input/output 缓存
2. **`device_map="auto"` 把模型分布到多张卡时,每张卡上的 cache 独立累积**,llmcompressor 失去集中管理能力 → 必然 OOM(实测在 4×A800 80GB 上,第 3 层 calibration 就崩了)

`oneshot(model=path_str, sequential_offload_device="cpu", moe_calibrate_all_experts=True)`
是 llmcompressor 官方对 256 expert 大 MoE 的优化路径:
- 整模型常驻 CPU RAM
- **逐层、逐 expert** 流式加载到 cuda:0,做完立刻释放,缓存不累积
- 256 个 expert 顺序处理,显存占用稳定

代价是**只用 1 张 GPU**,其他 GPU 空闲。但量化能跑通。

### 实验性多卡模式

如果未来 llmcompressor 优化了大 MoE 的 multi-gpu cache 管理,或者你想自己试,可以:

```bash
USE_MULTI_GPU=1 ./run_quantize.sh 2,3,4,5
```

**当前会 OOM**,记录在这是为了等上游修复后能直接开。

## 校准数据集选择

详细对比与推荐配方见 [`../docs/dataset.md`](../docs/dataset.md)。
`--calib-dataset` 支持下列预设别名(在 [`../llmcompressor_common/calib_dataset.py`](../llmcompressor_common/calib_dataset.py) 的 `DATASET_ALIASES` 中定义),
也支持直接传入任意 HuggingFace dataset ID:

| 别名 | HuggingFace ID | 适用场景 |
|------|---------------|---------|
| `cyankiwi`| `cyankiwi/calibration` | 中英双语、代码+推理+通用,复现 cyankiwi 公开量化 |
| `ultrachat` | `HuggingFaceH4/ultrachat_200k` | llmcompressor 官方首选、Qwen/DeepSeek 验证 |
| `neuralmagic` | `neuralmagic/LLM_compression_calibration` | Neural Magic 官方混合校准集 |
| `open-platypus` | `garage-bAInd/Open-Platypus` | STEM / 数学 / 推理 |
| `nemotron-v1` | `nvidia/Llama-Nemotron-Post-Training-Dataset` | NVIDIA 数学 + 代码 |
| `nemotron-v2` | `nvidia/Nemotron-Post-Training-Dataset-v2` | 多语言推理 |
| `swebench` | `princeton-nlp/SWE-bench_Verified` | 代码 / Bug 修复 |
| `hermes-fc` | `NousResearch/hermes-function-calling-v1` | 函数调用 / Agent |
| `longbench` | `THUDM/LongBench` | 长上下文 32K+ |
| `pile` / `wikitext` / `c4` | — | 基础语料 / 基线评估 |
| `belle` / `alpaca-zh` / `firefly` | — | 中文 |

### 多数据集混合

`--calib-dataset` 支持**逗号分隔**多集混合,`--calib-samples` 可传**总数**(自动平均)
或**逐集指定**:

```bash
# 单集
--calib-dataset cyankiwi --calib-samples 384

# 多集,总数自动平均(512 → 各 256 条)
--calib-dataset cyankiwi,ultrachat --calib-samples 512

# 多集,逐集精确指定
--calib-dataset cyankiwi,ultrachat --calib-samples 256,256
```

### 推荐配方

| 配方 | 说明 | 命令 |
|------|------|------|
| **A. 默认混合**(**推荐**)| cyankiwi(中英) + ultrachat(英文) 各 256 条,合计 512 | `./run_quantize.sh 2,3,4,5` |
| **B. 单集复现** | 仅用 cyankiwi 384 条,完整复现 cyankiwi 公开量化 | `./run_quantize.sh 2,3,4,5 cyankiwi 384` |
| **C. 官方首选** | llmcompressor 官方推荐,纯英文 | `./run_quantize.sh 2,3,4,5 ultrachat 512` |
| **D. 代码偏向** | 强化代码精度 | `./run_quantize.sh 2,3,4,5 swebench 384` |
| **E. NM 通用** | 无明确领域偏好的稳健选择 | `./run_quantize.sh 2,3,4,5 neuralmagic 512` |

## 快速开始

### 方法一:一键脚本(推荐)

```bash
cd /media/source/model_deploy/model_quantize/Qwen3.6-35B-A3B-AWQ

# 默认: GPU 2,3,4,5 + cyankiwi+ultrachat 各 256 条 + 单卡 sequential offload
./run_quantize.sh

# 自定义 GPU,沿用默认混合校准集
./run_quantize.sh 2,3,4,5

# 自定义校准集 / 样本数(位置参数: GPU 校准集 样本数)
./run_quantize.sh 2,3,4,5 cyankiwi 384          # 单集 cyankiwi
./run_quantize.sh 2,3,4,5 ultrachat 512         # 单集 ultrachat
./run_quantize.sh 2,3,4,5 swebench 384          # 代码偏向

# 自定义混合校准集
./run_quantize.sh 2,3,4,5 cyankiwi,swebench 256,256

# 实验性多卡(目前会 OOM,等 llmcompressor 优化大 MoE 多卡支持后才推荐)
USE_MULTI_GPU=1 ./run_quantize.sh 2,3,4,5
```

> 即使传 4 张卡(`2,3,4,5`),**默认 sequential offload 模式只用 cuda:0**(物理卡 2),
> 其他卡空闲。容器内 GPU 编号会自动重映射,你不用关心物理 vs 逻辑编号。

### 方法二:Docker Compose

```bash
cd /media/source/model_deploy/model_quantize/Qwen3.6-35B-A3B-AWQ

# 默认配置(混合校准集 cyankiwi + ultrachat 各 256 条)
docker compose -f docker-compose-quantize.yml run --rm quant-llmcompressor

# 通过环境变量覆盖(切回单集)
CALIB_DATASET=cyankiwi CALIB_SAMPLES=384 \
  docker compose -f docker-compose-quantize.yml run --rm quant-llmcompressor

# 切换其他单集
CALIB_DATASET=ultrachat CALIB_SAMPLES=512 \
  docker compose -f docker-compose-quantize.yml run --rm quant-llmcompressor
```

> compose 会自动挂载 `model_quantize/` 父目录到 `/workspace/model_quantize`,
> 使脚本能通过 `sys.path` 注入找到 `llmcompressor_common` 公共库。

### 方法三:直接执行 Python(需先安装依赖)

> 仅在不使用预装镜像时需要安装依赖。
> 使用 `model.vnet.com/sjhl/vllm-openai:v0.23.0-llmcompressor` 镜像时跳过此步。

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

cd /media/source/model_deploy/model_quantize/Qwen3.6-35B-A3B-AWQ

# 默认混合校准集(cyankiwi + ultrachat 各 256 条)+ 单卡 sequential offload
python3 quantize_llmcompressor.py --gpus 0

# 切换单集
python3 quantize_llmcompressor.py --gpus 0 \
    --calib-dataset cyankiwi --calib-samples 384

# 自定义混合
python3 quantize_llmcompressor.py --gpus 0 \
    --calib-dataset cyankiwi,swebench --calib-samples 256,256

# 实验性多卡
python3 quantize_llmcompressor.py --gpus 0,1,2,3 --multi-gpu
```

> 脚本通过 `sys.path.insert` 将 `..` 加入搜索路径,所以**必须在本目录运行**
> (或者用绝对路径调用脚本,从 `__file__` 推导父目录依然有效)。

## MoE 量化关键注意事项

### 1. 校准样本数须充足

256 个专家需要被充分激活,否则会报 `range() arg 3 must not be zero` 错误:

| 校准集 | 建议 `calib_samples` |
|--------|---------------------|
| `cyankiwi/calibration`(默认全量) | **384** |
| `ultrachat` / `neuralmagic` 等大数据集 | **512**(更稳健) |
| 多集混合(默认推荐) | **256+256=512** |

脚本传 `moe_calibrate_all_experts=True`,强制激活所有专家路径,
配合足够的样本数即可避免上述错误。

### 2. 不量化的层

`build_awq_recipe()` 通过 `MODEL_IGNORE_PRESETS["qwen3_5_moe"]` 引用以下列表,
仅作用于 `QuantizationModifier`(`AWQModifier` 不接受 `ignore`):

```python
[
    "lm_head",                  # 词表输出层
    "re:.*mlp\\.gate$",         # MoE 路由门控
    "re:.*shared_expert.*",     # 共享专家
    "re:.*linear_attn.*",       # Qwen3.6 线性注意力层（Mamba-like）
    "re:.*self_attn.*",         # 全注意力层
    "re:.*layers\\.0\\..*",     # 第 0 层（紧接嵌入层,量化不稳定）
    "re:.*mtp.*",               # Multi-Token Prediction 头部
    "re:model\\.visual.*",      # 视觉编码器（若有）
]
```

如需修改,编辑 [`../llmcompressor_common/recipe.py`](../llmcompressor_common/recipe.py)
中的 `MODEL_IGNORE_PRESETS`。

### 3. duo_scaling

`AWQModifier` 使用 `duo_scaling="both"`,意为一半 grid search 用纯激活、
另一半用激活+权重双向缩放,对 MoE 模型效果显著优于单方向缩放。
该值在脚本中硬编码,通常无需修改。

### 4. sequential_offload_device

单卡模式下,脚本显式传 `sequential_offload_device="cpu"` 给 oneshot,
**这是必须的**——否则 oneshot 会尝试把 70 GB 整模型一次性加载到 cuda:0(80 GB),
加上激活缓冲后会 OOM。

### 5. 运行日志

脚本通过公共库 `setup_logging()` 把 `stdout` / `stderr` 同时写入终端和文件:

- **默认路径**: 脚本所在目录下的 `logs/` 子目录
- **文件名**: `{时间戳}_{模型名}_awq.log`(例如 `20260622_080000_Qwen3.6-35B-A3B_awq.log`)
- **覆盖范围**: 所有 `print()` 输出 + `transformers` `logging.warning` 等
- **指定其他目录**: `python3 quantize_llmcompressor.py --log-dir /var/log/quant ...`

容器场景下,`logs/` 在挂载的 `/workspace/model_quantize/Qwen3.6-35B-A3B-AWQ/`
内,即对应宿主机本目录,容器退出后日志依然保留。

## 预期日志(关键校验点)

```
[GPU 预选] CUDA_VISIBLE_DEVICES=0,1,2,3（import 阶段已设置）
[GPU] 实际可用 4 张 GPU:                                       ← 容器内 4 张可见
  GPU 0/1/2/3 ... 合计显存: 317.0 GiB

[数据集配方]
  'cyankiwi/calibration'  256 条
  'HuggingFaceH4/ultrachat_200k'  256 条
  合计 512 条

[校准数据集] 预下载（共 2 个数据集）
  HF Token : 已设置（hf_fsN…tGLY, 长度 37）                    ← token 正确传入
  → ✅ ...

[代理] 已取消: HTTPS_PROXY, HTTP_PROXY, NO_PROXY              ← build 后清代理

[2/3] 开始 AWQ 量化（耗时约 1~4 小时）...
  模型加载 : oneshot 内部 sequential offload(模型常驻 CPU,逐层搬到 cuda:0)
  ↓
  (1/41): Calibrating: 100% ...                                ← 进度按层推进
  (2/41): Calibrating: 100% ...
  ...
  Grid search for model.layers.X.post_attention_layernorm: ...  ← AWQ smooth
  ...
  (41/41): Calibrating: 100% ...

[3/3] 量化完成,已保存到: /media/llm/Qwen/Qwen3.6-35B-A3B-AWQ-4bit
```

`nvidia-smi` 观察:
- **cuda:0(物理卡 2)**:显存稳定在 30~50 GB,GPU util 70~90%
- **其他卡**:空闲(单卡 sequential offload 模式下不参与计算)

`htop` 观察:
- 主机内存使用 ~80-120 GB(模型 70 GB 常驻 + activation cache)

## 量化后部署

量化完成后,修改上层目录的 `docker-compose-vllm-first.yml`,
将模型路径从第三方来源改为本地量化输出:

```yaml
# 原配置（第三方）
command: >
  /media/llm/cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit ...

# 修改为本地量化版本
command: >
  /media/llm/Qwen/Qwen3.6-35B-A3B-AWQ-4bit ...
```

vLLM 加载参数无需改变,继续使用 `--quantization awq_marlin`。

## 常见问题

**Q: 量化跑了几十分钟还没看到进度,正常吗?**
A: 正常。前期阶段(模型加载 + tokenizer + 数据集准备)大约 1~3 分钟,
   之后是逐层 calibration,每层 ~5~10 分钟,40 层总计 4~7 小时。
   看 `logs/` 目录里的最新日志文件,`(N/41): Calibrating: ...` 表示进度。

**Q: 报 `range() arg 3 must not be zero` 错误**
A: 某个专家未被激活,增大 `--calib-samples`(如从 384 增到 512 或更高)。

**Q: CUDA OOM**
A: 默认单卡 sequential offload 模式下基本不会 OOM。
   如果遇到,可以:
   - 减小 `--max-seq-length`(从 2048 → 1024)
   - 减小 `--calib-samples`(但要保持 ≥ 256 让所有专家被激活)
   - 确认没设 `USE_MULTI_GPU=1`(多卡模式当前会 OOM)

**Q: 数据集下载慢**
A: 镜像里默认走内网代理 `http://172.31.0.55:20171`,如果代理不可达,可以:
   - 设环境变量 `HF_ENDPOINT=https://hf-mirror.com` 切换国内镜像
   - 或提前下载到 `HF_DATASETS_CACHE=/media/quantize/datasets`,再用 `--skip-prefetch`

**Q: `cannot import name 'AWQTransformModifier'`**
A: llmcompressor 0.12.0 的类名是 `AWQModifier`,脚本已适配;
   若自定义脚本仍报错,把 `AWQTransformModifier` 替换为 `AWQModifier`。

**Q: `ModuleNotFoundError: No module named 'llmcompressor_common'`**
A: 公共库通过 `sys.path` 注入加载(不是 pip 包),需要确认:
   1. 容器里 `model_quantize/` 父目录已挂载(compose / run_quantize.sh 自动处理)
   2. 在本目录或用绝对路径运行脚本,让 `Path(__file__).parent.parent` 指向 `model_quantize/`
   3. `llmcompressor_common/__init__.py` 存在

**Q: 想换数据集但脚本里找不到对应配置**
A: 脚本不再维护 per-dataset 配置(旧版的 `DATASET_CONFIGS`)。
   公共库的 `_to_text_column()` 自动识别 `text` / `messages` / `conversations` 列,
   或从常用字段(`instruction` / `prompt` / `problem_statement` / ...)兜底拼接。
   直接传任意 HF dataset ID 即可,通常无需手工配置。

**Q: 多卡 OOM,有什么办法?**
A: 当前 llmcompressor 0.12.0 对 256 expert MoE 的多卡 device_map 路径没有优化好,
   AWQ 的 cache hook 在每张卡上独立累积导致必 OOM。
   建议:
   - **默认就走单卡 sequential offload**(稳定),不要传 `USE_MULTI_GPU=1`
   - 等 llmcompressor 后续版本优化大 MoE 的多卡 cache 管理后再尝试
