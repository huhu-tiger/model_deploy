# AWQ 量化校准数据集推荐

> AWQ（Activation-aware Weight Quantization）依靠校准数据集在前向传播中捕获激活分布，
> 从而确定每层的量化缩放因子。校准数据的分布越贴近模型的实际推理场景，
> 量化后的精度损失越小。

---

## 当前使用

### cyankiwi/calibration

| 字段 | 值 |
|---|---|
| HuggingFace ID | `cyankiwi/calibration` |
| 数量 | 384 条 |
| 语言 | 中英双语 |
| 领域 | 代码、推理、通用问答 |

由 [IQuest-Coder-V1-40B-Instruct-AWQ-4bit](https://huggingface.co/cyankiwi/IQuest-Coder-V1-40B-Instruct-AWQ-4bit) 量化实践整理而来，与 `llmcompressor` + AWQ 方案配合验证，目前作为 GLM-5.2 量化的默认校准集。

```python
from datasets import load_dataset
ds = load_dataset("cyankiwi/calibration", split="train")
```

---

## 推荐替代数据集

### 1. NVIDIA Llama-Nemotron Post Training Dataset

| 字段 | 值 |
|---|---|
| HuggingFace ID | `nvidia/Llama-Nemotron-Post-Training-Dataset` |
| 版本 | v1.1（2025-04-08） |
| 规模 | ~3000 万条合成样本 |
| 语言 | 英语 |
| 领域 | 数学（22M）、代码（10M）、科学（700K）、指令跟随、对话、安全 |
| 论文 | [arXiv 2505.00949](https://arxiv.org/abs/2505.00949) |

NVIDIA 开源的大规模后训练合成数据集，用于训练 Llama-3.1-Nemotron-Ultra-253B、Llama-3.3-Nemotron-Super-49B 等模型。NVIDIA Model Optimizer 默认将其与 `cnn_dailymail` 混合作为 AWQ/FP8 量化的校准集。

**适用场景**：通用推理、数学、代码理解能力要求较高的模型量化。

```python
from datasets import load_dataset
# 取 code 和 math 子集，各采样若干条作为校准
ds = load_dataset(
    "nvidia/Llama-Nemotron-Post-Training-Dataset",
    "SFT",
    split="code",   # 或 "math"
    trust_remote_code=True,
)
```

---

### 2. NVIDIA Nemotron Post Training Dataset v2

| 字段 | 值 |
|---|---|
| HuggingFace ID | `nvidia/Nemotron-Post-Training-Dataset-v2` |
| 版本 | 2.0（2025-08-20） |
| 规模 | ~600 万条 |
| 语言 | 英语、西班牙语、法语、德语、意大利语、日语 |
| 领域 | 数学（240K）、代码（175K）、STEM（355K）、对话（628K）、多语言（5M+） |
| 论文 | [arXiv 2508.14444](https://arxiv.org/abs/2508.14444) |

在 v1 基础上大幅扩充了多语言数据（5 种语言），支持 NVIDIA-Nemotron-Nano-8B-v2-Reasoning 训练。适合需要多语言理解的量化场景。

**适用场景**：多语言、多领域混合推理模型的量化校准。

```python
from datasets import load_dataset
ds = load_dataset(
    "nvidia/Nemotron-Post-Training-Dataset-v2",
    "SFT",
    split="code",
    trust_remote_code=True,
)
```

---

### 3. princeton-nlp/SWE-bench_Verified

| 字段 | 值 |
|---|---|
| HuggingFace ID | `princeton-nlp/SWE-bench_Verified` |
| 规模 | 500 条（人工验证） |
| 语言 | 英语 |
| 领域 | 软件工程（GitHub Issue + 代码 Patch） |
| 来源 | Python 热门开源仓库 |
| 合作方 | Princeton NLP + OpenAI Preparedness |

SWE-bench 的人工验证子集，每条数据包含真实 GitHub Issue 描述和对应的解决 PR Patch。由 `cyankiwi/IQuest-Coder-V1-40B-Instruct-AWQ-4bit` 直接使用为校准集，验证了其在代码模型量化中的有效性。

**适用场景**：以代码生成、Bug 修复、软件工程任务为主的模型量化。

```python
from datasets import load_dataset
ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
# 使用 problem_statement 字段作为文本输入
```

---

### 4. Hermes-Function-Calling（NousResearch）

| 字段 | 值 |
|---|---|
| HuggingFace ID | `NousResearch/hermes-function-calling-v1` |
| 规模 | 数万条（多子集） |
| 语言 | 英语 |
| 领域 | 函数调用、结构化 JSON 输出、工具使用 |
| 格式 | ShareGPT 多轮对话 |

NousResearch Hermes 系列模型的训练数据，涵盖单轮/多轮函数调用、JSON 模式、Agent 类结构化输出等场景。已被多个量化社区实践（如 Mistral-3.2-24B NVFP4）作为工具调用领域的校准补充。

**适用场景**：Function Calling、Agent、工具调用场景的模型量化，防止量化损失函数调用精度。

```python
from datasets import load_dataset

# 子集列表：func_calling_singleturn / func_calling /
#           glaive_func_calling / json_mode_agentic / json_mode_singleturn
ds = load_dataset(
    "NousResearch/hermes-function-calling-v1",
    "func_calling",
    split="train",
    trust_remote_code=True,
)
```

---

### 5. LongBench（THUDM）

| 字段 | 值 |
|---|---|
| HuggingFace ID | `THUDM/LongBench` |
| 版本 | v1 / v2 |
| 规模 | v1: 4,750 条；v2: 503 条（选择题） |
| 语言 | 中英双语 |
| 领域 | 长文档 QA、多文档推理、摘要、代码补全、少样本学习 |
| 上下文长度 | v1: 5K–15K；v2: 8K–2M |
| 论文 | [arXiv 2308.14508](https://arxiv.org/abs/2308.14508) |

THUDM 发布的长上下文理解基准数据集，21 个任务覆盖单文档 QA、多文档 QA、代码补全等。研究表明 4-bit AWQ 在长上下文检索任务中精度下降明显，使用 LongBench 作为校准集有助于缓解这一问题。

**适用场景**：以长上下文处理（32K+）为主要推理场景的模型量化。

```python
from datasets import load_dataset

# 可选任务: narrativeqa, qasper, hotpotqa, lcc, repobench-p 等
ds = load_dataset("THUDM/LongBench", "qasper", split="test")

# LongBench v2（更长上下文，选择题格式）
# ds = load_dataset("THUDM/LongBench-v2", split="train")
```

---

## llmcompressor 官方内置数据集

以下数据集可直接以字符串形式传入 `oneshot(dataset=...)` 无需额外处理，是 `llmcompressor` / vLLM 社区验证过的通用基线。

### 6. HuggingFaceH4/ultrachat_200k

| 字段 | 值 |
|---|---|
| HuggingFace ID | `HuggingFaceH4/ultrachat_200k` |
| 规模 | 20 万条对话（筛选后） |
| 语言 | 英语 |
| 领域 | 多轮指令跟随、问答、通用对话 |
| 格式 | messages（user/assistant 多轮） |

`llmcompressor` 官方示例与文档的**首选推荐**，高质量多轮对话，覆盖日常助手场景。在 GLM-5.2 这类通用对话模型量化时是最稳健的选择。

**适用场景**：通用指令跟随、问答、对话类模型量化。

```python
# llmcompressor 原生支持，可直接传字符串
oneshot(
    model=model, tokenizer=tokenizer,
    dataset="HuggingFaceH4/ultrachat_200k",
    num_calibration_samples=512,
    max_seq_length=2048,
    ...
)

# 或手动加载
from datasets import load_dataset
ds = load_dataset("HuggingFaceH4/ultrachat_200k",
                  split="train_sft[:512]")
```

---

### 7. garage-bAInd/Open-Platypus

| 字段 | 值 |
|---|---|
| HuggingFace ID | `garage-bAInd/Open-Platypus` |
| 规模 | ~25,000 条 |
| 语言 | 英语 |
| 领域 | STEM、数学、逻辑推理（11 个子集精选） |
| 论文 | [arXiv 2308.07317](https://arxiv.org/abs/2308.07317) |

由 11 个开源数据集精选人工设计题目（90%+ 为人工题）。Neural Magic 在其研究中发现该数据集对大模型（70B、405B）量化精度有显著帮助，并以此为基础构建了官方校准集 `neuralmagic/LLM_compression_calibration`。`llmcompressor` 内置支持字符串 `"open-platypus"`。

**适用场景**：STEM 推理、数学、逻辑类模型量化。

```python
# llmcompressor 内置支持
oneshot(model=model, tokenizer=tokenizer,
        dataset="open-platypus", ...)

# 手动加载
ds = load_dataset("garage-bAInd/Open-Platypus", split="train")
```

---

### 8. neuralmagic/LLM_compression_calibration

| 字段 | 值 |
|---|---|
| HuggingFace ID | `neuralmagic/LLM_compression_calibration` |
| 规模 | 10,000 条 |
| 语言 | 英语 |
| 领域 | 混合（STEM、对话、通用），来源持续迭代 |
| 格式 | `text`（无模板）+ `messages`（多轮，配合 chat_template） |

Neural Magic（`llmcompressor` 维护团队）的**官方默认校准集**，由 `Open-Platypus` 等多个数据集混合精炼而来，持续随研究进展更新。同时提供 `text` 和 `messages` 两种字段，无论模型是否需要 chat template 都可使用。

**适用场景**：快速验证、无明确领域偏好时的通用首选。

```python
ds = load_dataset("neuralmagic/LLM_compression_calibration",
                  split="train")
# 使用 messages 字段（chat template）
# 或 text 字段（无 template）
```

---

### 9. wikitext-2-raw-v1（WikiText）

| 字段 | 值 |
|---|---|
| HuggingFace ID | `Salesforce/wikitext`，config `wikitext-2-raw-v1` |
| 规模 | ~2M token（测试集约 250K token） |
| 语言 | 英语 |
| 领域 | 维基百科纯文本 |

量化领域的经典基准数据集，AWQ / GPTQ 原始论文均使用 WikiText-2 评估困惑度。纯净的百科文本，无指令模板，适合测量基础语言建模能力的保留程度。`llmcompressor` 内置支持字符串 `"wikitext-2-raw-v1"`。

**适用场景**：量化基线评估、通用文本生成模型、困惑度对比实验。

```python
oneshot(model=model, tokenizer=tokenizer,
        dataset="wikitext-2-raw-v1", ...)

# 手动加载
ds = load_dataset("Salesforce/wikitext",
                  "wikitext-2-raw-v1", split="test")
```

---

### 10. allenai/c4

| 字段 | 值 |
|---|---|
| HuggingFace ID | `allenai/c4` |
| 规模 | 数百 GB（按需流式加载） |
| 语言 | 英语（及多语言变体 `mc4`） |
| 领域 | 互联网网页文本（清洗过的 Common Crawl） |

Google T5 预训练数据，规模极大，内容覆盖广泛。因体积庞大，校准时建议使用流式加载或仅取少量样本。`llmcompressor` 内置支持字符串 `"c4"`。

**适用场景**：通用预训练基础模型、需要多样化网络文本激活分布的量化校准。

```python
oneshot(model=model, tokenizer=tokenizer,
        dataset="c4", ...)

# 手动流式加载（避免全量下载）
ds = load_dataset("allenai/c4", "en",
                  split="validation", streaming=True)
ds = ds.take(512)
```

---

### 11. mit-han-lab/pile-val-backup（AutoAWQ 默认）

| 字段 | 值 |
|---|---|
| HuggingFace ID | `mit-han-lab/pile-val-backup` |
| 规模 | The Pile 验证集子集 |
| 语言 | 英语 |
| 领域 | 多源混合（学术、代码、书籍、网页等 22 个来源） |

AutoAWQ 库（AWQ 的另一主要实现）在未指定数据集时**自动使用**该数据集。The Pile 的多样来源使其激活分布较为均衡，是 AWQ 算法的验证基准。

**适用场景**：对齐 AutoAWQ 默认行为、多领域基础模型量化。

```python
ds = load_dataset("mit-han-lab/pile-val-backup", split="validation")
```

---

## 参考量化模型

### cyankiwi/IQuest-Coder-V1-40B-Instruct-AWQ-4bit

| 字段 | 值 |
|---|---|
| HuggingFace 模型 | [cyankiwi/IQuest-Coder-V1-40B-Instruct-AWQ-4bit](https://huggingface.co/cyankiwi/IQuest-Coder-V1-40B-Instruct-AWQ-4bit) |
| 量化方法 | AWQ，W4A16 |
| Group Size | 32 |
| 量化工具 | `llmcompressor` |
| 校准数据集 | `princeton-nlp/SWE-bench_Verified` |

与本项目使用完全相同工具链（`llmcompressor` + AWQ）完成的代码模型量化案例，证明了 SWE-bench_Verified 作为校准集的可行性。同一作者（cyankiwi）也发布了 `cyankiwi/calibration` 数据集。

---

## 选型建议

### 按用途推荐

| 模型用途 | 首选校准集 | 备选 |
|---|---|---|
| 通用对话 / 指令跟随 | `HuggingFaceH4/ultrachat_200k` | `neuralmagic/LLM_compression_calibration` |
| 通用推理 / 开箱即用 | `neuralmagic/LLM_compression_calibration` | `garage-bAInd/Open-Platypus` |
| 数学 / STEM 推理 | `nvidia/Llama-Nemotron-Post-Training-Dataset`（math 子集） | `garage-bAInd/Open-Platypus` |
| 代码生成 / Bug 修复 | `princeton-nlp/SWE-bench_Verified` | `cyankiwi/calibration` |
| Function Calling / Agent | `NousResearch/hermes-function-calling-v1` | `nvidia/Nemotron-Post-Training-Dataset-v2`（tool_calling） |
| 长上下文（32K+）| `THUDM/LongBench` | `HuggingFaceH4/ultrachat_200k` |
| 多语言 | `nvidia/Nemotron-Post-Training-Dataset-v2`（multilingual 子集） | `allenai/c4`（mc4） |
| 基线困惑度评估 | `Salesforce/wikitext`（wikitext-2-raw-v1） | `mit-han-lab/pile-val-backup` |
| 混合场景（本项目 GLM-5.2） | `cyankiwi/calibration` | `neuralmagic/LLM_compression_calibration` |

### llmcompressor 一行字符串支持的数据集

```python
# 以下 dataset 参数直接传字符串即可，无需手动 load_dataset
oneshot(model=model, tokenizer=tokenizer,
        dataset="ultrachat-200k",      # 或以下任一
        # dataset="open-platypus"
        # dataset="wikitext-2-raw-v1"
        # dataset="c4"
        num_calibration_samples=512,
        max_seq_length=2048,
        ...)
```

---

## 关键研究结论

> **Neural Magic 论文《Give me BF16 or give me death》（arXiv 2411.02355）**：
>
> - **小模型（≤ 8B）**：使用随机 token 作为校准数据即可获得可接受精度
> - **大模型（≥ 70B，包括本项目 GLM-5.2 这类超大 MoE）**：必须使用真实分布的数据集才能准确捕获激活异常值，校准集质量对最终精度影响显著
> - **结论**：对于 GLM-5.2（千亿级 MoE）量化，校准集的选择尤为关键，建议至少使用领域相关数据（如 `cyankiwi/calibration` 中英混合），或与 `ultrachat-200k` 混合使用

---

## 经验法则

- **样本数**：128–512 条通常已足够，推荐从 256–384 开始；超大 MoE 模型（GLM-5.2）可适当增至 512
- **序列长度**：`max_seq_length` 推荐 2048，若模型长上下文能力关键可提升至 4096
- **领域相关性** > 数据量：小而精的相关数据集优于大而泛的无关数据
- **混合策略**：多数据集按 1:1 或 2:1 混合可兼顾多个能力维度
- **随机 shuffle**：使用 `dataset.shuffle(seed=42)` 确保样本分布均匀

---

## 按模型家族推荐（数据集 × 模型对照）

> 以下基于 llmcompressor 官方示例、社区实践及 Neural Magic 研究整理。
> 「**同家族数据**」原则（FAQ 论文 arXiv 2601.11200）：使用与目标模型训练分布相近的数据效果最佳。

---

### GLM 系列（ZhipuAI）

> **代表模型**：GLM-4.7（MoE）、**GLM-5.2**（MoE，本项目）、GLM-4-9B

| 模型特征 | MoE 稀疏架构、中英双语、代码 + 推理 + 对话 + 工具调用 |
|---|---|
| llmcompressor 官方示例数据集 | `HuggingFaceH4/ultrachat_200k`（512 条，2048 长） |
| 推荐组合 | `cyankiwi/calibration` + `ultrachat_200k` |
| MoE 注意事项 | 需 `moe_calibrate_all_experts=True`，确保所有专家被校准 |
| 忽略层 | `lm_head`、`embed_tokens`、`re:.*mlp.gate$` |

**推荐数据集配方（GLM-5.2 本项目）**：

```python
# 配方 A：当前脚本默认（中英双语混合）
dataset = "cyankiwi/calibration"          # 384 条，中英，代码+推理

# 配方 B：官方推荐（更通用，纯英语）
dataset = "HuggingFaceH4/ultrachat_200k"  # 取前 512 条

# 配方 C：混合（兼顾中英+代码+推理）—— 推荐尝试
from datasets import load_dataset, concatenate_datasets
ds_cn = load_dataset("cyankiwi/calibration", split="train")            # 384 条
ds_en = load_dataset("HuggingFaceH4/ultrachat_200k",
                     split="train_sft[:200]")                           # 200 条
# 用 text 列对齐后合并（根据字段实际名称调整）
```

---

### Qwen 系列（阿里）

> **代表模型**：Qwen2.5-7/14/32/72B-Instruct、Qwen2.5-72B、Qwen3-30B-A3B（MoE）、Qwen2.5-Coder

| 子类 | 推荐数据集 | 说明 |
|---|---|---|
| Qwen2.5 通用 Instruct | `HuggingFaceH4/ultrachat_200k` | 官方 Issue 验证，512 条，需应用 ChatML 模板 |
| Qwen2.5-72B+ | `ultrachat_200k` + `open-platypus` 混合 | 大模型需更多样性 |
| Qwen2.5-Coder | `princeton-nlp/SWE-bench_Verified` + `cyankiwi/calibration` | 代码+通用混合 |
| Qwen3-MoE | `ultrachat_200k`（配合 MoE 校准模块） | FAQ 论文验证有效 |

**配方示例（Qwen2.5-72B-Instruct）**：

```python
ds = load_dataset("HuggingFaceH4/ultrachat_200k",
                  split="train_sft[:512]").shuffle(seed=42)
# 必须应用 chat template，ChatML 格式
ds = ds.map(lambda x: {
    "text": tokenizer.apply_chat_template(
        x["messages"], tokenize=False, add_generation_prompt=False)
})
recipe = GPTQModifier(targets="Linear", scheme="W4A16",
                      ignore=["lm_head", "re:.*mlp.gate$"])
```

---

### DeepSeek 系列

> **代表模型**：DeepSeek-V3、DeepSeek-R1、DeepSeek-R1-0528

| 子类 | 推荐数据集 | 说明 |
|---|---|---|
| DeepSeek-V3 / R1（MoE） | `HuggingFaceH4/ultrachat_200k` | **llmcompressor 官方示例**，512 条，2048 长 |
| DeepSeek-R1（推理） | `open-platypus` + `nvidia/Llama-Nemotron`（math） | 推理链数据更能触发推理层激活 |

**DeepSeek-R1 官方配方**（来自 llmcompressor 源码）：

```python
DATASET_ID = "HuggingFaceH4/ultrachat_200k"
NUM_CALIBRATION_SAMPLES = 512
MAX_SEQUENCE_LENGTH = 2048

ds = load_dataset(DATASET_ID, split=f"train_sft[:{NUM_CALIBRATION_SAMPLES}]")
ds = ds.shuffle(seed=42)

# MoE gate 层不量化
recipe = GPTQModifier(
    targets="Linear", scheme="W4A16",
    ignore=["lm_head", "re:.*mlp.gate$"]
)
# 大模型按层顺序处理，避免 OOM
oneshot(..., sequential_targets=["DeepseekV3Attention", "DeepseekV3MLP"])
```

---

### LLaMA 系列（Meta）

> **代表模型**：Llama-3.1-8B/70B/405B-Instruct、Llama-3.3-70B

| 子类 | 推荐数据集 | 说明 |
|---|---|---|
| Llama-3.x-8B-Instruct | `HuggingFaceH4/ultrachat_200k` | llmcompressor W4A16 官方示例 |
| Llama-3.x-70B/405B | `ultrachat_200k` + `open-platypus` | 大模型需更丰富分布 |
| Llama 数学蒸馏版 | `nvidia/Llama-Nemotron-Post-Training-Dataset`（math） | 同家族数据效果最佳 |

---

### Nemotron 系列（NVIDIA）

> **代表模型**：Llama-3.1-Nemotron-Ultra-253B、Llama-3.3-Nemotron-Super-49B

| 子类 | 推荐数据集 | 说明 |
|---|---|---|
| Nemotron 通用 | `neuralmagic/LLM_compression_calibration` | NVIDIA 生态，Neural Magic 官方校准集 |
| Nemotron 推理 | `nvidia/Llama-Nemotron-Post-Training-Dataset`（math+code） | **同家族数据**，FAQ 论文最佳实践 |

---

### 代码模型

> **代表模型**：Qwen2.5-Coder-32B、IQuest-Coder-V1-40B、CodeLlama、DeepSeek-Coder

| 模型类型 | 推荐数据集组合 | 比例 |
|---|---|---|
| 代码生成为主 | `princeton-nlp/SWE-bench_Verified` | 单独使用（500条全用） |
| 代码 + 工具调用 | `SWE-bench_Verified` + `hermes-function-calling-v1` | 1:1 |
| 代码 + 通用对话 | `SWE-bench_Verified` + `cyankiwi/calibration` | 1:1 |
| 代码 + 大模型（>40B） | `SWE-bench_Verified` + `ultrachat_200k` + `open-platypus` | 2:1:1 |

---

### 推理/思考模型（Reasoning / CoT）

> **代表模型**：QwQ-32B、DeepSeek-R1、Llama-3.1-Nemotron-Ultra、o1-like 蒸馏版

| 推荐数据集 | 原因 |
|---|---|
| `garage-bAInd/Open-Platypus` | 含数学/逻辑步骤题，触发推理链激活 |
| `nvidia/Llama-Nemotron-Post-Training-Dataset`（math 子集） | 推理链样本丰富，覆盖 CoT 层激活 |
| `HuggingFaceH4/ultrachat_200k` | 兜底通用数据，防止对话能力退化 |

**推荐配方（推理模型，256 条）**：

```python
# 128 条 STEM 推理 + 128 条通用对话
ds_reason = load_dataset("garage-bAInd/Open-Platypus",
                         split="train").shuffle(seed=42).select(range(128))
ds_chat   = load_dataset("HuggingFaceH4/ultrachat_200k",
                         split="train_sft[:128]").shuffle(seed=42)
```

---

### 长上下文模型

> **代表模型**：Qwen2.5-72B（128K）、GLM-5.2（128K）、Llama-3.1（128K）

| 推荐数据集 | `max_seq_length` | 说明 |
|---|---|---|
| `THUDM/LongBench`（qasper / hotpotqa） | 4096–8192 | 长文档 QA，触发长依赖激活 |
| `HuggingFaceH4/ultrachat_200k` | 2048（基线） | 先用 2K 确保基础能力，再补 4K+ 长文本 |

> ⚠️ 研究表明 4-bit AWQ 在长上下文检索任务中精度损失明显。若模型的核心场景是 32K+ 输入，建议将 `max_seq_length` 提高至 4096 并混入 LongBench 样本。

---

### 中文 / 多语言模型

> **代表模型**：GLM-5.2、Qwen2.5（中文能力）、InternLM3、Yi 系列

| 推荐数据集组合 | 比例 | 说明 |
|---|---|---|
| `cyankiwi/calibration` + `ultrachat_200k` | 1:1 | 中英均衡，GLM-5.2 当前配方 |
| `nvidia/Nemotron-Post-Training-Dataset-v2`（multilingual） + `cyankiwi/calibration` | 1:1 | 五语言扩展 |
| `allenai/c4`（mc4 多语言版） + `cyankiwi/calibration` | 1:2 | 大范围语言覆盖 |

---

## 数据集配方速查表

| 模型 | 样本数 | seq_len | 数据集配方 |
|---|---|---|---|
| **GLM-5.2**（本项目，MoE） | 384 | 2048 | `cyankiwi/calibration` |
| **GLM-5.2**（推荐升级） | 512 | 2048 | `cyankiwi/calibration`(256) + `ultrachat_200k`(256) |
| **DeepSeek-R1/V3**（MoE） | 512 | 2048 | `ultrachat_200k` |
| **Qwen2.5-72B-Instruct** | 512 | 2048 | `ultrachat_200k` |
| **Qwen2.5-Coder-32B** | 384 | 2048 | `SWE-bench_Verified`(200) + `cyankiwi/calibration`(184) |
| **LLaMA-3.1-8B-Instruct** | 512 | 2048 | `ultrachat_200k` |
| **LLaMA-3.1-70B+** | 512 | 2048 | `ultrachat_200k`(256) + `open-platypus`(256) |
| **QwQ-32B**（推理） | 256 | 2048 | `open-platypus`(128) + `ultrachat_200k`(128) |
| **Mixtral / 通用 MoE** | 512 | 2048 | `neuralmagic/LLM_compression_calibration` |
| **代码模型（40B+）** | 512 | 2048 | `SWE-bench_Verified`(256) + `hermes-function-calling`(128) + `ultrachat_200k`(128) |
| **长上下文（128K 场景）** | 256 | 4096 | `ultrachat_200k`(128) + `LongBench`(128) |
| **通用小模型（≤8B）** | 128 | 2048 | `neuralmagic/LLM_compression_calibration` 或 `open-platypus` |
