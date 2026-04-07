# Guard 模型评测与融合说明

本文档说明 `Qwen3Guard`、`Sentinel`、以及 `qwen3_sentinel_or.py`（当前为加权融合）中的判定逻辑与权重计算方式。

## 1. 关键问题：Qwen 没有概率分数，如何参与加权？

`Qwen3Guard` 返回的是离散文本标签（如 `Safety: Unsafe / Controversial / Safe`），不是概率。

在融合脚本中，我们先把 Qwen 的离散输出映射为一个**风险分值**（启发式分值）：

- `Unsafe -> 1.0`
- `Controversial -> 0.7`
- `Safe -> 0.0`
- 其他/无法解析 -> `0.5`

对应函数：`qwen_risk_score_from_safety()`。

## 2. Sentinel 分数来源

`Sentinel` 返回 `probs`，其中使用：

- `jailbreak_prob = probs[1]`

作为 Sentinel 的风险分值（范围 \\[0,1\\]）。

## 3. 加权融合公式

融合脚本（`qwen3_sentinel_or.py`）采用：

\[
score = w_q \cdot qwen\_score + w_s \cdot sentinel\_jailbreak\_prob
\]

- 当 `score >= fusion_threshold`，预测为 `风险(1)`
- 否则预测为 `安全(0)`

### 权重归一化

脚本会将输入权重做归一化：

\[
\hat{w_q}=\frac{w_q}{w_q+w_s},\quad \hat{w_s}=\frac{w_s}{w_q+w_s}
\]

因此环境变量中的权重不要求和为 1，只要都非负、总和大于 0 即可。

## 4. 相关环境变量（.env）

加权融合使用以下变量：

- `OR_QWEN_BASE_URL`
- `OR_QWEN_MODEL`
- `OR_QWEN_API_KEY`
- `OR_SENTINEL_ENDPOINT`
- `OR_SENTINEL_MODEL`
- `OR_GUARD_CONCURRENCY`
- `OR_QWEN_WEIGHT`
- `OR_SENTINEL_WEIGHT`
- `OR_FUSION_THRESHOLD`

示例：

```env
OR_QWEN_WEIGHT=0.4
OR_SENTINEL_WEIGHT=0.6
OR_FUSION_THRESHOLD=0.5
```

## 5. 为什么加权融合可能优于单模型

- Qwen 对部分英文/语义风格有优势（离散判别强）
- Sentinel 对越狱概率更敏感（概率信号强）
- 通过加权可在误报/漏报之间平衡，尤其在 `hard` 数据上常见提升

## 6. 调参建议

- 想提高攻击检出（更激进）：
  - 提高 `OR_SENTINEL_WEIGHT`
  - 降低 `OR_FUSION_THRESHOLD`
- 想降低误报（更保守）：
  - 提高 `OR_QWEN_WEIGHT`（若 Qwen 在安全样本更稳）
  - 提高 `OR_FUSION_THRESHOLD`

建议固定验证集后做网格搜索，例如：

- `OR_QWEN_WEIGHT` ∈ {0.3, 0.4, 0.5, 0.6}
- `OR_FUSION_THRESHOLD` ∈ {0.45, 0.50, 0.55, 0.60, 0.65}

并对比 `总体正确率 + Hard正确率 + 英文正确率`。

## 7. 运行说明：使用不同 input（不影响原 data1.csv 结果）

三个脚本都支持 `--input`、`--output`、`--markdown-output` 参数。

- 默认 `--input` 是 `datasets/data1.csv`
- 如果你要跑新的数据集（例如 `datasets/data1_err.csv`），只需要显式传入新的输入和输出文件名
- 只要输出文件名不和原来 `data1_*` 冲突，就不会覆盖原结果

### 7.1 Sentinel

```bash
python3 prompt-injection-jailbreak-sentinel-v2.py \
  --input datasets/data1_err.csv \
  --output output/data1_err_sentinel_results.csv \
  --markdown-output output/data1_err_sentinel_results.md
```

### 7.2 Qwen3Guard

```bash
python3 Qwen3Guard.py \
  --input datasets/data1_err.csv \
  --output output/data1_err_guard_results.csv \
  --markdown-output output/data1_err_guard_results.md
```

### 7.3 融合脚本（qwen3_sentinel_or.py）

```bash
python3 qwen3_sentinel_or.py \
  --input datasets/data1_err.csv \
  --output output/data1_err_qwen_sentinel_or_results.csv \
  --markdown-output output/data1_err_qwen_sentinel_or_results.md
```

### 7.4 强烈建议使用绝对路径（避免跑错文件）

```bash
python3 /media/source/model_deploy/model_test/Guard/prompt-injection-jailbreak-sentinel-v2.py \
  --input /media/source/model_deploy/model_test/Guard/datasets/data1_err.csv \
  --output /media/source/model_deploy/model_test/Guard/output/data1_err_sentinel_results.csv \
  --markdown-output /media/source/model_deploy/model_test/Guard/output/data1_err_sentinel_results.md
```

### 7.5 常见问题：为什么结果里出现“未知”

评测脚本计算 `真实标签` 时依赖 `label` 列：

- `1 -> 风险`
- `0 -> 安全`

如果输入 CSV 没有 `label`，就会出现 `真实标签=未知`，并导致 `是否判断正确` 无法正确计算。
