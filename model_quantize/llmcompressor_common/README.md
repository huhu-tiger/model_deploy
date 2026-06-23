# llmcompressor_common

llmcompressor AWQ 量化的公共函数库,从 GLM-5.2 和 Qwen3.6-35B-A3B 量化脚本中抽出。

## 模块

| 模块 | 说明 |
|------|------|
| `gpu_select` | GPU 预选（必须在 import torch 之前）+ GPU 信息打印 |
| `calib_dataset` | 校准集解析 / 别名 / 下载 / 混合 / `text` 列统一格式 |
| `recipe` | AWQ recipe 构造（AWQModifier + QuantizationModifier）+ 各模型 IGNORE 预设 |
| `memory` | 内存 / 磁盘 / 模型大小工具（仅 stdlib） |
| `resource_check` | 量化前资源预检（模式 A 单卡 / 模式 B 多卡） |
| `logging_utils` | Tee stdout/stderr → 日志文件 |

## 校准集别名

`DATASET_ALIASES` 中预定义的短名(完整推荐见 `../docs/dataset.md`):

```
cyankiwi       → cyankiwi/calibration                     # 默认,中英双语
ultrachat      → HuggingFaceH4/ultrachat_200k             # 官方首选
neuralmagic    → neuralmagic/LLM_compression_calibration  # NM 官方混合
open-platypus  → garage-bAInd/Open-Platypus               # STEM/数学
nemotron-v1    → nvidia/Llama-Nemotron-Post-Training-Dataset
nemotron-v2    → nvidia/Nemotron-Post-Training-Dataset-v2
swebench       → princeton-nlp/SWE-bench_Verified         # 代码
hermes-fc      → NousResearch/hermes-function-calling-v1  # 工具调用
longbench      → THUDM/LongBench                          # 长上下文
pile / wikitext / c4
belle / alpaca-zh / firefly                               # 中文
```

## 多数据集混合

`parse_dataset_specs` 支持单集 / 多集 / 自动平均 / 逐集指定:

```python
parse_dataset_specs("cyankiwi", "384")
# → [("cyankiwi/calibration", 384)]

parse_dataset_specs("cyankiwi,ultrachat", "512")
# → [("cyankiwi/calibration", 256), ("HuggingFaceH4/ultrachat_200k", 256)]

parse_dataset_specs("cyankiwi,ultrachat", "256,256")
# → 同上,但逐集精确指定
```

## IGNORE 预设

`MODEL_IGNORE_PRESETS` 提供以下模型族的默认 ignore 列表:

| Key | 适用模型 |
|-----|---------|
| `qwen3_5_moe` | Qwen3.6-35B-A3B（含 linear_attn / self_attn / mtp / visual） |
| `glm_moe_dsa` | GLM-5.2（含 indexer / embed_tokens） |
| `generic_moe` | 通用 MoE 兜底（lm_head / embed_tokens / gate / shared_expert / layer 0） |

需要补充其他模型时,可在 `recipe.py` 添加。

## 调用示例

参见同级目录:
- `../Qwen3.6-35B-A3B-AWQ/quantize_llmcompressor.py`
- `../Glm-5.2-AWQ-H100/quantize_llmcompressor.py`

## 在 Docker 中使用

两个量化脚本通过 `sys.path` 注入找到本目录(不是 pip 包):

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llmcompressor_common.gpu_select import pre_select_gpus
pre_select_gpus()
```

容器内挂载关系:

```
/media/source/model_deploy/model_quantize/  →  容器内同路径
                                                ├─ llmcompressor_common/   ← 公共库
                                                ├─ Qwen3.6-35B-A3B-AWQ/    ← 调用方
                                                └─ Glm-5.2-AWQ-H100/       ← 调用方
```

docker-compose / run 脚本里需要把 `/media/source/model_deploy/model_quantize`
整体挂载进容器,确保 `llmcompressor_common` 可被 `sys.path` 找到。
