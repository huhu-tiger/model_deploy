# Qwen3.6-35B-A3B  AWQ-4bit 量化

本目录提供将 Qwen3.6-35B-A3B（BF16 完整权重）量化为 AWQ-4bit 的脚本，
参考 [cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit](https://modelscope.cn/models/cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit)
和 [QuantTrio/Qwen3.6-35B-A3B-AWQ](https://modelscope.cn/models/QuantTrio/Qwen3.6-35B-A3B-AWQ) 的量化方法。

## 目录结构

```
├── README.md                    # 本文档
├── quantize_rtn.py              # 方案一: RTN（推荐首选）
├── quantize_llmcompressor.py    # 方案二: llmcompressor（精度最高）
├── eval_quantized.py            # 量化质量评测
├── docker-compose-quantize.yml  # Docker Compose 启动
├── run_quantize.sh              # 一键运行脚本
└── requirements.txt             # Python 依赖（llmcompressor 方案）
```

## 模型信息

| 项目 | 值 |
|------|-----|
| 模型架构 | `Qwen3_5MoeForConditionalGeneration` (`qwen3_5_moe`) |
| 层类型 | 混合：linear_attention × 3 + full_attention × 1，共 40 层 |
| 专家数 | 256 个专家，每 token 激活 8 个 |
| 原始精度 | BF16，约 70GB |
| 量化目标 | W4A16 AWQ，约 20~24GB |
| 源权重路径 | `/media/llm/Qwen/Qwen3.6-35B-A3B` |
| 输出路径 | `/media/llm/Qwen/Qwen3.6-35B-A3B-AWQ-4bit` |

## 两个参考模型的量化方法

> 经过调研，**两者均未公开量化脚本**，但方法细节已被第三方复现。

| 模型 | 量化方法 | 校准数据 | 公开脚本 |
|------|---------|---------|---------|
| [QuantTrio/Qwen3.6-35B-A3B-AWQ](https://huggingface.co/QuantTrio/Qwen3.6-35B-A3B-AWQ) | **data-free RTN**（无校准数据） | 无 | ❌ 未公开（已被 [FeanorsCodeSL](https://github.com/FeanorsCodeSL/dgx-spark-quantization) 精确复现） |
| [cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit](https://huggingface.co/cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit) | **AWQ + 校准数据**（STEM & Agentic 领域） | 多语言STEM/Agentic | ❌ 未公开 |

## 两套量化方案对比

| 方案 | 脚本 | 对标 | 校准数据 | 显存需求 | 耗时 | 精度 |
|------|------|------|---------|---------|------|------|
| **RTN（推荐首选）** | `quantize_rtn.py` | QuantTrio | 无 | < 30GB | ~8~30分钟 | ★★★☆ |
| **llmcompressor** | `quantize_llmcompressor.py` | cyankiwi | 需要 | 4×80GB GPU | 2~4小时 | ★★★★ |

## 硬件需求

- **GPU**: 建议 4× A800/H800 80GB（量化过程峰值显存 ~80GB+）
- **内存**: ≥ 128GB
- **磁盘**: 源权重 ~70GB + 输出 ~24GB，预留 ≥ 120GB

## 快速开始

### 方法一：一键脚本（推荐）

```bash
cd /media/source/model_deploy/model_quantize/Qwen3.6-35B-A3B-AWQ

# 方案 RTN（推荐首选）
./run_quantize.sh rtn 2,3,4,5

# 方案 llmcompressor（精度最高，需多卡）
./run_quantize.sh llmcompressor 2,3,4,5
```

### 方法二：Docker Compose

```bash
cd /media/source/model_deploy/model_quantize/Qwen3.6-35B-A3B-AWQ

# 方案一（推荐）
docker compose -f docker-compose-quantize.yml run --rm quant-rtn

# 方案二（精度最高）
docker compose -f docker-compose-quantize.yml run --rm quant-llmcompressor
```

### 方法三：直接执行 Python（需先安装依赖）

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

# 方案 RTN
python3 quantize_rtn.py --gpus 2,3,4,5

# 方案 llmcompressor
python3 quantize_llmcompressor.py --gpus 2,3,4,5 --calib-samples 512
```

## MoE 量化关键注意事项

### 1. 校准样本数须充足

Qwen3.6-35B-A3B 有 **256 个专家**，量化校准时必须确保所有专家都被激活，
否则会报 `range() arg 3 must not be zero` 错误。

| 方案 | 建议 `calib_samples` |
|------|---------------------|
| llmcompressor | **512**（默认） |

### 2. 不量化的层

以下层应排除在量化范围之外，以保护路由精度：
- `lm_head`：词表输出层
- `mlp.gate`：MoE 路由门控
- `mlp.shared_expert_gate`：共享专家门控

### 3. duo_scaling

llmcompressor 方案使用 `duo_scaling="both"`，同时对输入激活和权重做
channel-wise 缩放，对 MoE 模型效果显著优于单方向缩放。

## 量化后部署

量化完成后，修改上层目录的 `docker-compose-vllm-first.yml`，
将模型路径从第三方来源改为本地量化输出：

```yaml
# 原配置（第三方）
command: >
  /media/llm/cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit ...

# 修改为本地量化版本
command: >
  /media/llm/Qwen/Qwen3.6-35B-A3B-AWQ-4bit ...
```

vLLM 加载参数无需改变，继续使用 `--quantization awq_marlin`。

## 预期量化时长

| GPU 配置 | RTN | llmcompressor |
|---------|-----|--------------|
| 4× A800 80GB | ~8 分钟 | 2~4 小时 |
| 单卡 | ~30 分钟 | — |

> 耗时受校准样本数、数据集下载速度、专家激活率等影响。

## 常见问题

**Q: 报 `range() arg 3 must not be zero` 错误**  
A: 某个专家未被激活，增大 `--calib-samples`（从 256 增到 512 或更高）。

**Q: CUDA OOM**  
A: 减小 `--calib-samples` 或 `--max-seq-length`。

**Q: 数据集下载慢**  
A: 设置环境变量 `HF_ENDPOINT=https://hf-mirror.com` 使用国内镜像，
   或提前下载后传入本地路径（`--calib-dataset /path/to/local/dataset`）。
