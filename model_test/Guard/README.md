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
