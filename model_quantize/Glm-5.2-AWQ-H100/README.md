# GLM-5.2 AWQ-INT4 量化（H100 × 8）

## 模型信息

| 项目 | 值 |
|---|---|
| 模型架构 | `GlmMoeDsaForCausalLM`（`glm_moe_dsa`） |
| 层数 | 78（前 3 层 dense，后 75 层 MoE） |
| 路由专家数 | 256（每 token 激活 8 个）+ 1 共享专家 |
| 注意力 | MLA（q_lora_rank=2048，kv_lora_rank=512）+ DSA 稀疏索引器 |
| 全量 BF16 大小 | ~1.5 TB（282 个 shard，每个约 5 GB） |
| 本地路径 | `/media/llm/ZhipuAI/GLM-5.2` |

## 量化方案：llmcompressor AWQ

- **算法**：AWQ（Activation-aware Weight Quantization），使用校准数据
- **格式**：W4A16 非对称，group_size=128
- **校准集**：`cyankiwi/calibration`（256 条）+ `HuggingFaceH4/ultrachat_200k`（256 条），共 512 条，max_seq_length=2048
- **镜像**：`model.vnet.com/sjhl/vllm-openai:v0.23.0-llmcompressor`（已内置 llmcompressor 0.12.0）
- **压缩**：~1.5 TB → ~375~450 GB（约 25~30%）
- **输出**：`/media/llm/ZhipuAI/GLM-5.2-AWQ-4bit-LC`

## 运行模式说明

### 模式 A：单卡 sequential offload（**当前实际使用**）

| 项目 | 说明 |
|---|---|
| GPU 使用 | 1 × H100 80GB |
| 加载方式 | sequential offload，逐层 CPU→GPU→CPU |
| CPU offload | ~1.5 TB 全部常驻 CPU RAM |
| 预计耗时 | 4~12 小时 |
| 稳定性 | ✅ 成熟，推荐使用 |

### 模式 B：8 卡 device_map（**当前不可用**）

模式 B 在 transformers 5.10.1 + GLM-5.2 组合下存在结构性不兼容：

**根本原因**：GLM-5.2 的 checkpoint 将 MoE 专家的 `gate_proj` 和 `up_proj` 分开存储，
而模型架构期望 `gate_up_proj`（合并张量）。transformers 加载时需执行 `MergeModulelist`
转换，合并峰值约 36 GiB/层（256 专家），远超每卡剩余 25 GiB 的空闲空间，导致
1202 个参数停留在 `meta` 设备，无法参与 AWQ 前向传播。

即使将显存利用率降到 45%（每卡 36 GiB → 剩余 44 GiB），合并虽可通过，但模型 80%
的层（~63 层）将在 CPU 上计算，速度比模式 A sequential offload 还慢 2~5 倍。

**结论**：在 8 × H100 80GiB 上，量化 1.5 TB 的 GLM-5.2 MoE 模型应使用模式 A。

### 自动回退机制

脚本运行时会优先尝试模式 B；若检测到 `meta` 参数（加载失败标志），将自动释放
GPU 缓存并切换到模式 A，量化结果与直接运行模式 A 完全相同。

## 文件说明

```
Glm-5.2-AWQ-H100/
├── docker-compose-quantize.yml   # 量化任务编排（含模式 A、B）
├── quantize_llmcompressor.py     # AWQ 量化脚本
├── logs/                         # 量化运行日志（自动创建）
├── eval_ppl.py                   # 量化精度验证（Perplexity）
└── README.md
```

> 依赖已内置于镜像，无需单独安装。校准数据集首次运行通过代理下载，
> 缓存至宿主机 `/media/quantize/datasets`，后续复用。

## 日志与缓存路径

| 用途 | 路径 |
|---|---|
| 量化运行日志 | `./logs/`（脚本同目录，自动挂载到宿主机） |
| 校准数据集缓存 | `/media/quantize/datasets/` |
| PyTorch 缓存 | `/media/quantize/torch/` |

日志文件名格式：`YYYYMMDD_HHMMSS_<模型名>_mode_<a|b>.log`

```bash
# 查看最新日志
ls -lt logs/

# 实时跟踪当前运行（模式 A）
tail -f logs/*_GLM-5.2_mode_b.log

# 搜索量化进度或错误
grep -E "AWQ 量化完成|模式切换|Traceback|ERROR" logs/*.log
```

## 前置条件

1. **完整下载模型权重**（共 282 个 shard）：

```bash
ls /media/llm/ZhipuAI/GLM-5.2/model-*.safetensors | wc -l
# 应输出 282
```

2. 确认量化镜像已构建：

```bash
docker images model.vnet.com/sjhl/vllm-openai:v0.23.0-llmcompressor
# 如未构建，执行：
# cd /media/source/model_deploy/model_quantize/llmcompressor-docker && bash build.sh
```

## 运行量化

```bash
cd /media/source/model_deploy/model_quantize/Glm-5.2-AWQ-H100

# 推荐：脚本自动尝试模式 B，检测到不可用后回退到模式 A
docker compose -f docker-compose-quantize.yml run --rm quant-llmcompressor-multi

# 直接运行模式 A（跳过模式 B 尝试，更快开始）
docker compose -f docker-compose-quantize.yml run --rm quant-llmcompressor
```

### 关键参数说明

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--gpu-memory-utilization` | `0.70` | 模式 B 每卡显存比例，OOM 时可降低 |
| `--cpu-memory` | `auto` | CPU offload 容量，自动取可用内存 × 80% |
| `--calib-dataset` | `cyankiwi/calibration,HuggingFaceH4/ultrachat_200k` | 逗号分隔多集 |
| `--calib-samples` | `256,256` | 各数据集采样数 |
| `--max-seq-length` | `2048` | 校准序列最大长度 |
| `--no-fallback-to-mode-a` | 未设置 | 禁用自动回退（调试用） |
| `--log-dir` | `./logs/` | 日志目录 |

## 精度验证

量化完成后验证 Perplexity（需代理下载 wikitext-2）：

```bash
docker compose -f docker-compose-quantize.yml run --rm quant-llmcompressor \
  bash -c "python3 eval_ppl.py \
    --model-path /media/llm/ZhipuAI/GLM-5.2-AWQ-4bit-LC \
    --gpus 0,1,2,3,4,5,6,7 \
    --samples 64"
```

**精度参考（wikitext-2 PPL，越低越好）：**
- BF16 原始：~2.5~3.5
- AWQ 量化优秀：BF16 + 0.1~0.3
- AWQ 量化差（专家覆盖不足）：BF16 + 1.0+

## 跳过层说明

| 跳过模式 | 原因 |
|---|---|
| `lm_head` | 输出词表投影，影响生成精度 |
| `embed_tokens` | 词嵌入查找表，非矩阵乘法 |
| `indexer` | DSA 稀疏注意力索引器，精度高度敏感 |
| `mlp.gate` | MoE 路由门控，路由精度影响专家激活 |
| `mlp.shared_expert` | 共享专家，每层必激活，保持精度 |
| `layers.0.` | 第 0 层紧接嵌入层，量化不稳定 |

## 量化产物加载

```bash
vllm serve /media/llm/ZhipuAI/GLM-5.2-AWQ-4bit-LC \
  --quantization awq_marlin \
  --tensor-parallel-size 8
```
