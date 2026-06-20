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
- **校准集**：`cyankiwi/calibration`，384 条样本，max_seq_length=2048
- **镜像**：`model.vnet.com/sjhl/vllm-openai:v0.23.0-llmcompressor`（已内置 llmcompressor 0.12.0）
- **压缩**：~1.5 TB → ~375~450 GB（约 25~30%）
- **输出**：`/media/llm/ZhipuAI/GLM-5.2-AWQ-4bit-LC`

### 两种运行模式

| | 模式 A（单卡） | 模式 B（8 卡，推荐） |
|---|---|---|
| GPU 使用 | 1 × H100 80GB | 8 × H100 80GB = **640 GB** |
| 加载方式 | sequential offload，逐层 CPU→GPU→CPU | device_map="auto"，640 GB 常驻 GPU |
| CPU offload | ~1.5 TB 全部 | ~860 GB（剩余部分） |
| 预计耗时 | 4~12 小时 | **2~6 小时** |
| 稳定性 | ✅ 成熟 | ⚠️ MoE 专家覆盖需验证 |

## 文件说明

```
Glm-5.2-AWQ-H100/
├── docker-compose-quantize.yml   # 量化任务编排（含模式 A、B）
├── quantize_llmcompressor.py     # AWQ 量化脚本
├── eval_ppl.py                   # 量化精度验证（Perplexity）
└── README.md
```

> 依赖已内置于镜像，无需单独安装。校准数据集首次运行通过代理下载，
> 缓存至宿主机 `/media/quantize/datasets`，后续复用。

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

# 模式 B（8 卡，推荐优先尝试）
docker compose -f docker-compose-quantize.yml run --rm quant-llmcompressor-multi

# 模式 A（单卡，稳定回退）
docker compose -f docker-compose-quantize.yml run --rm quant-llmcompressor
```

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
