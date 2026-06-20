# AutoAWQ vs LLM-Compressor 调研

> 量化算法（AWQ）相同，工具链已发生世代更替。本文聚焦：
>
> 1. 两个工具的现状与维护情况
> 2. 在本机硬件环境（8 × H100 80GB 或 8 × H20 96GB，CPU RAM 2 TB；
>    见 [hardware_capacity.md](./hardware_capacity.md) 第 1 节）下的能力差异
> 3. 对 GLM-5.2 / 大 MoE 模型的适用性
> 4. 选型结论（含 AWQ vs GPTQ 对比、其它可被 vLLM 启动的量化工具）

---

## 1. 维护状态（2026-06）

| 项目 | 状态 | 最后更新 | 备注 |
|---|---|---|---|
| **AutoAWQ**（`casper-hansen/AutoAWQ`） | ❌ **已废弃** | 仓库 2025-05 归档 | 最后测试组合 Torch 2.6.0 + Transformers 4.51.3；后续 transformers 不兼容由用户自行向 transformers 反馈 |
| **LLM-Compressor**（`vllm-project/llm-compressor`） | ✅ 活跃维护 | 0.12+（2026 持续发版） | vLLM 项目官方推荐，AutoAWQ 的能力已合并进来 |
| **AutoGPTQ** | ❌ 已废弃（2025-04 归档） | — | 替代为 `GPTQModel` |
| **GPTQModel** | ✅ 活跃维护 | 7.x（2026） | GPTQ 的 drop-in 替代 |

> 关键信号：HuggingFace transformers 已在 issue #38078 讨论用 llm-compressor 替代 autoawq；
> vLLM 文档（AutoAWQ 页）显式标注 "deprecated, use llm-compressor"。

---

## 2. 算法层面：完全相同

两者都实现 AWQ（Activation-aware Weight Quantization），核心步骤一致：

1. 用校准集前向，按层采集激活 |X| 的分位/RMS
2. 在 `(scale, clip)` 网格上搜索最小化 |X(W − Q(W·s)/s)|²
3. 写出 `W4A16` 权重 + per-group scale/zero（默认 group_size=128）

> 量化后产物本质相同，理论精度（PPL、下游任务）也相同——差异只在工程实现、对 MoE 的支持、可处理的模型规模。

---

## 3. 工程差异（影响本机能否跑）

| 维度 | AutoAWQ | LLM-Compressor |
|---|---|---|
| **加载方式** | 全模型一次性加载到 GPU（或 device_map 切分） | `device_map=None` 全量到 CPU，然后 **layer-sequential pipeline**：逐层 CPU→GPU→CPU |
| **GPU 峰值** | 需 1 张 ≥ 24 GiB（小模型） / 多卡分片 | 1 张 H100 即足够（同一时刻只持有 1~2 层） |
| **CPU 峰值** | 模型大小 + 校准激活（多卡 device_map 时仍需 CPU 物化） | 模型大小 × 1.0 + MoE 解包瞬时（~18 GiB/层） |
| **磁盘 offload** | ❌ 无原生支持（仅社区 PR） | ✅ 通过 `AWQModifier(offload_device=torch.device("cpu"))` 把缓存激活 offload；MoE 流式解包文档化 |
| **MoE 支持** | Mixtral / DeepSeek-Coder-Lite 早期实现，新 MoE（GLM、Qwen3-MoE）官方未跟进 | `llmcompressor.modeling` 含 `linearize_moe`、`replace_modules_for_calibration`、`load_context` 等 MoE 专用入口；新架构持续更新 |
| **校准样本上限** | 受 GPU/CPU RAM 限制，128~256 常见 | sequential pipeline 下校准样本数对峰值影响很小，可 512+ |
| **vLLM 兼容** | ✅ 原生 `awq` / `awq_marlin` 内核 | ✅ 同上，与 vLLM 同项目，格式 100% 对齐 |
| **DDP / 多卡量化** | ❌ 单进程 | ✅ 0.10+ AWQ + DDP，2.9~3.2× 加速 + 51% 单卡显存下降；GPTQ + 磁盘 offload 已支持 |
| **transformers 兼容** | 锁定 4.51.3（旧版） | 跟进 transformers 5.x |
| **新模型架构（GLM-5.2、Llama 4 等）** | 不可能跟进 | 通过 `llmcompressor.modeling` 模块化扩展，且本仓库 `glm_moe_calibration.py` 已有解包补丁 |

---

## 4. 在本机硬件上的能力对比

> 本机：8 × H100 80GB（或 H20 96GB）+ **2 TB CPU RAM**（系统可用 ~1980 GiB）+ 16 TB 磁盘。
> 单位：BF16 权重大小。
> 详细的 CPU RAM 扩展能力（3 TB / 4 TB）见 [hardware_capacity.md](./hardware_capacity.md) 第 3 节。

### 4.1 AutoAWQ

| 模型体量 | 是否可行 | 限制点 |
|---|---|---|
| ≤ 70 B dense | ✅ | 单卡 H100 24 GiB 阈值轻松满足 |
| 100~200 B | ⚠️ 可行但慢 | 需 device_map 手动切分 |
| 200 B+ MoE（新架构） | ❌ | 架构未跟进，无 GLM-5 / Qwen3-MoE / Llama 4 适配；transformers 锁旧版无法加载 |
| 671 B+（DeepSeek-V3） | ❌ | 无磁盘 offload、无 sequential pipeline，CPU 峰值 = 1.3 TiB + 激活，多卡 device_map 仍需全量 BF16 物化 |
| 1 T+（GLM-5.2） | ❌ | 同上，且模型本身不被支持 |

**结论**：AutoAWQ 仅适合 ≤ 70~200 B 的旧架构 dense 模型。

### 4.2 LLM-Compressor

| 模型体量 | 当前 2 TB | 3 TB | 4 TB | 限制点 |
|---|---|---|---|---|
| ≤ 70 B dense | ✅ 2~4 h | ✅ | ✅ | — |
| 100~400 B（含 Qwen3-MoE 235B） | ✅ 5~10 h | ✅ | ✅ | — |
| 671 B（DeepSeek-V3） | ⚠️ 临界 10~16 h | ✅ | ✅ | CPU 峰值 ~1.55~1.65 TiB，2 TB 留余量不足；建议扩 swap 兜底 |
| 700~900 B（DeepSeek R1-class、Kimi K2） | ❌ 易 OOM | ⚠️ 勉强 | ✅ | CPU 峰值 ~1.8~2.0 TiB |
| 855 GiB（MiniMax-M3） | ⚠️ 临界 6~10 h | ✅ | ✅ | CPU 峰值 ~1.25 TiB；建议扩 swap |
| ≥ 1 TiB（GLM-5.2） | ❌ **实测 OOM** | ⚠️ 勉强（扩 swap） | ✅ 稳的 | 修 pending 引用后峰值 ~1.65 TiB |
| 1.5~2 TiB BF16 | ❌ | ❌ | ✅ | — |

**结论**：LLM-Compressor 把本机量化上限从 AutoAWQ 的 "200 B 级" 推到 "**按 CPU RAM 决定**"——
2 TB 上限 ~900 GiB BF16；3 TB 可勉强吃 GLM-5.2（1.4 TiB）；4 TB 稳吃 ≤ 2 TiB BF16。

---

## 5. 对当前任务（GLM-5.2 AWQ）的具体取舍

| 方案 | 评价 |
|---|---|
| AutoAWQ | ❌ 架构不支持 + 已废弃，**不可选** |
| LLM-Compressor 模式 A 单卡 sequential offload | ⚠️ 唯一可行路径；GLM-5.2 BF16 1.4 TiB 已超本机 2 TB CPU 容量，需要**扩 CPU RAM 到 4 TB**（3 TB 勉强）或改流式 from_pretrained 或借用大内存机器 |
| LLM-Compressor 模式 B 多卡 device_map | ❌ MoE + AWQ 在 sequential pipeline 上有未修复 bug（issue #1939、#2068），且 CPU 峰值不下降 |
| GPTQModel（W4 GPTQ，非 AWQ） | 备选；6.1.0+ 已支持 GLM 5/5.1，大 MoE VRAM 优化更激进。如果 AWQ 路径走不通可考虑切到 GPTQ；CPU 峰值与 AWQ 接近，仍受 CPU RAM 限制 |

---

## 6. 选型建议（一句话）

> **本机所有量化项目统一使用 LLM-Compressor**（已经是项目现状）。
> AutoAWQ 仅作为历史参考，不再用于新项目。
> 对 1 TiB+ 模型（GLM-5.2 级别），即使是 LLM-Compressor 也需要先解决 CPU OOM：
> 优先扩 CPU RAM 到 4 TB；备选改流式解包或切 GPTQModel。

---

## 7. 参考资料

- [AutoAWQ 仓库（已归档）](https://github.com/casper-hansen/AutoAWQ)
- [LLM-Compressor 仓库](https://github.com/vllm-project/llm-compressor)
- [vLLM AutoAWQ 文档（已弃用提示）](https://docs.vllm.ai/en/stable/features/quantization/auto_awq/)
- [LLM-Compressor AWQModifier API](https://docs.vllm.ai/projects/llm-compressor/en/latest/reference/llmcompressor/modifiers/awq/base/)
- [HF Transformers issue #38078: replace autoawq with llm-compressor](https://github.com/huggingface/transformers/issues/38078)
- 关联开放问题：`vllm-project/llm-compressor` issue #1939、#2068（AWQ + MoE + device_map="auto"）
- GPTQModel（GPTQ 路径替代）：<https://github.com/ModelCloud/GPTQModel>

---

## 8. 其它可被 vLLM 启动的量化工具

vLLM 官方支持远不止 AWQ 一种格式。下表把生产中常见的量化工具按"工具 → 算法/格式 → vLLM 启动方式"梳理（来源：vLLM 0.14 文档 `features/quantization`）：

| 量化工具 | 输出格式 | 适合的精度 | vLLM 启动参数 | 是否适合本机 GLM-5.2 级 MoE |
|---|---|---|---|---|
| **LLM-Compressor** | `compressed-tensors`（含 AWQ、GPTQ、AutoRound、QuIP、SpinQuant、FP8、INT8、INT4、NVFP4、MXFP4、KV cache 量化、混合精度） | W4A16 / W8A8 / FP8 | 自动识别，无需显式 `--quantization` | ✅ 唯一推荐 |
| **GPTQModel**（AutoGPTQ 替代） | GPTQ INT4 / INT8 | W4A16 | `--quantization gptq` 或 `gptq_marlin` | ✅ GLM 5/5.1 已支持，AWQ 走不通时备选 |
| **AutoAWQ**（已废弃） | AWQ INT4 | W4A16 | `--quantization awq` / `awq_marlin` | ❌ 不再维护 |
| **AMD Quark** | OCP MX（MXFP4/MXFP6）、FP8 | MXFP4/FP8 | `--quantization quark` | ⚠️ ROCm 优先；MXFP4 在 Hopper 也可推理 |
| **NVIDIA ModelOpt** | FP8 / NVFP4 / INT8 | FP8/NVFP4 | `--quantization modelopt` 或 `modelopt_fp4` | ⚠️ 校准依赖 NVIDIA 工具链；Hopper/B200 友好 |
| **Intel Neural Compressor（INC）/ AutoRound** | INT4 GPTQ 风格 | W4A16 | `--quantization auto-round` / `gptq` | ⚠️ 校准更快，Intel 系优化 |
| **bitsandbytes** | NF4 / FP4 / INT8 | W4A16 / W8A8 | `--quantization bitsandbytes` | ⚠️ 易上手但精度低于 AWQ/GPTQ，常用于 LoRA 训练后推理 |
| **GGUF**（llama.cpp 生态） | Q2_K~Q8_0 等 | W2~W8 | `--model <path>.gguf`（自动识别） | ⚠️ vLLM 0.14 已支持 GGUF 推理；CPU 友好，GPU 性能比专用内核略低 |
| **TorchAO** | AffineQuantized / INT4 / INT8 / FP8 | 多种 | `--quantization torchao` | ⚠️ PyTorch 官方实验性，生态在快速演进 |
| **DeepSpeedFP** | FP6 / FP8 | FP6/FP8 | `--quantization deepspeedfp` | ⚠️ 小众，仅特定 ZeRO 推理场景 |
| **vLLM 在线量化** | FP8 W8A8（动态） | FP8 | `--quantization fp8`（直接对 BF16 ckpt 在加载时量化） | ✅ 不需要离线量化产物，加载即可；精度无校准，对大 MoE 也好用 |

### 8.1 关键替代方案

针对当前任务（GLM-5.2、Qwen3.6-35B-A3B 等本机推理），可作为 AWQ 之外的备选：

1. **vLLM 在线 FP8（强推荐尝试）**
   - 直接拿 BF16 模型加载时即量化，**不需要离线产物，跳过 CPU OOM 风险**
   - 命令：`vllm serve /media/llm/<model> --quantization fp8 --tensor-parallel-size 8`
   - 限制：BF16 仍需先在 8 张卡上一次性加载，所以**总显存是上限**：
     - H100 机 640 GiB → 只适合 ≤ 470 GiB BF16
     - H20 机 768 GiB → 只适合 ≤ 565 GiB BF16
   - Qwen3.6-35B-A3B 70 GiB BF16 → FP8 ~35 GiB，单卡直跑 ✅
   - GLM-5.2 1.4 TiB BF16 → ❌ 任一台都装不下，仍需先做离线 INT4 量化

2. **GPTQModel W4A16**
   - GLM 5/5.1 已支持，AWQ 在本机走不通时可作 GPTQ 备选；产物同样能被 vLLM 用 `awq_marlin`/`gptq_marlin` 内核加速
   - 校准与量化流程与 LLM-Compressor 类似，量化阶段 CPU 峰值相近，对 GLM-5.2 仍有 OOM 风险

3. **AMD Quark MXFP4 / NVIDIA ModelOpt NVFP4**
   - 4-bit 浮点，相比 INT4 在 MoE 精度上更接近 BF16，Hopper/B200 有专用内核
   - 产物体积与 INT4 同量级，本机 H100 推理可行
   - 量化流程与 AWQ 类似但工具链更新更快

### 8.2 推理时的"零量化"路径

如果不想做离线量化，**vLLM 还支持运行原始 BF16/FP16 模型**（无 `--quantization` 参数）：

| 模型 | BF16 总占用 | H100 机（640 GiB） | H20 机（768 GiB） |
|---|---|---|---|
| Qwen3.6-35B-A3B | 70 GiB | ✅ 单卡即可 | ✅ 单卡即可 |
| Qwen3-MoE 235B | 470 GiB | ✅ TP=8 余 ~170 GiB | ✅ TP=8 余 ~298 GiB |
| MiniMax-M3 | 855 GiB | ❌ 超总显存 | ❌ 仍超 ~87 GiB |
| GLM-5.2 | 1.4 TiB | ❌ | ❌ |

> 本机 BF16 直跑显存上限：H100 机 **~470 GiB**、H20 机 **~565 GiB**
> （留 25~30% 给 KV cache 与中间激活）。超过这条线就必须量化，否则只能多节点。

### 8.3 选型快速结论

| 场景 | 推荐 |
|---|---|
| 中小模型（≤ 200 B），追求最稳精度 | LLM-Compressor AWQ W4A16 + `awq_marlin` |
| 中小模型，不想做离线量化 | vLLM `--quantization fp8`（在线 FP8） |
| 大 MoE（400~700 B），LLM-Compressor AWQ 失败 | GPTQModel W4 / vLLM 在线 FP8 |
| 想用最新 4-bit 浮点格式（MXFP4/NVFP4） | AMD Quark 或 NVIDIA ModelOpt |
| 只想快速验证、对精度要求低 | bitsandbytes / GGUF |

---

## 9. AWQ vs GPTQ 可行性深度对比

AWQ 与 GPTQ 是当前生产 INT4 量化的两条主流路径。算法原理、工具链、精度、量化耗时、对 MoE 的鲁棒性都不同。

### 9.1 算法原理对比

| 维度 | AWQ | GPTQ |
|---|---|---|
| 核心思想 | 找出 **显著权重通道**（激活幅度大的 1% 通道），通过 `(scale, clip)` 缩放保护其精度 | 用 Hessian 矩阵（基于校准数据二阶信息）逐列贪心量化，最小化层输出误差 |
| 量化粒度 | per-group（典型 group_size=128） | per-group（同） |
| 是否需校准 | 是（128~512 条样本，激活分布） | 是（128~512 条样本，Hessian 计算） |
| 单层耗时 | 较快（grid search 20 个 scale × N 通道） | 较慢（每列要解线性方程） |
| 对激活 outlier 鲁棒性 | ✅ 显式处理 | ⚠️ 依赖校准数据覆盖 |
| 对低 bit（≤ 3-bit）扩展 | 一般 | ✅ 更稳，因为有显式误差补偿 |

### 9.2 工具链与 vLLM 支持

| 维度 | AWQ | GPTQ |
|---|---|---|
| 已废弃工具 | AutoAWQ（2025-05 归档） | AutoGPTQ（2025-04 归档） |
| 现役工具 | **LLM-Compressor**（推荐）/ AutoRound（INC） | **GPTQModel**（推荐）/ LLM-Compressor（也支持 GPTQModifier） |
| vLLM 内核 | `awq`、**`awq_marlin`**（H100/H20 推荐） | `gptq`、**`gptq_marlin`**（H100/H20 推荐） |
| 启动命令 | `vllm serve <path> --quantization awq_marlin` | `vllm serve <path> --quantization gptq_marlin` |
| KV cache 量化 | 通过 LLM-Compressor 额外配置 | 通过 LLM-Compressor / KV cache modifier |
| 模型架构覆盖 | Qwen2/3、Llama3/4、Mixtral、DeepSeek-V3、GLM-4 等；新架构需要适配 | 同等覆盖；GPTQModel 6.1+ 显式支持 GLM 5/5.1 |

### 9.3 精度对比（典型 W4A16，wikitext-2 PPL）

> 数据来自 LLM-Compressor 与 GPTQModel 官方 benchmark、社区报告（典型 dense 与 MoE 模型）。

| 模型 | BF16 | AWQ W4A16 | GPTQ W4A16 | 差距 |
|---|---|---|---|---|
| Llama 3 8B | 6.10 | 6.22 | 6.18 | 几乎相同 |
| Qwen2.5 72B | 4.05 | 4.13 | 4.12 | 相同 |
| Mixtral 8x7B | 3.84 | 3.95 | 3.92 | 相同 |
| DeepSeek-V3 671B（典型 MoE） | 2.85 | 2.92 | 2.95 | AWQ 略胜（激活分布更宽） |
| 3-bit 极端压缩 | — | 明显劣化 | 仍可用 | **GPTQ 在 ≤3-bit 更稳** |

**结论**：在 W4A16 标准设置下，AWQ 与 GPTQ 精度基本相当；
对 MoE 模型 AWQ 略有优势（专家间激活分布差异大，AWQ 的 scale 搜索更贴合）；
对 ≤3-bit 极端压缩 GPTQ 更优。

### 9.4 量化耗时（H100 单卡 sequential offload，模式 A）

| 体量 | AWQ 耗时 | GPTQ 耗时 | 差异 |
|---|---|---|---|
| 70 B dense | 2~4 h | 3~5 h | GPTQ 略慢（Hessian 计算开销） |
| 235 B MoE | 5~8 h | 7~10 h | 同上 |
| 671 B MoE | 10~16 h | 14~20 h | 同上 |

> GPTQ 单层比 AWQ 多花约 20~30%；对超大 MoE 累计影响 3~5 h。

### 9.5 CPU 内存峰值差异

CPU RAM 峰值在两条路径上**几乎一致**，主导因素是模型大小 + MoE 解包，
而非量化算法本身。GPTQ 的 Hessian 矩阵在 GPU 侧分配，对 CPU 不构成额外压力。

### 9.6 当前任务的具体取舍

| 模型 | AWQ 路径 | GPTQ 路径 | 推荐 |
|---|---|---|---|
| **Qwen3.6-35B-A3B** | ✅ LLM-Compressor，2~4 h | ✅ GPTQModel/LLM-Compressor，3~5 h | **AWQ**（精度略优，耗时短） |
| **MiniMax-M3** | ⚠️ 2 TB 临界，6~10 h | ⚠️ 2 TB 临界，8~12 h | **AWQ**（耗时短，省 swap 暴露窗口） |
| **GLM-5.2** | ❌ 2 TB 实测 OOM；4 TB 可行 | ❌ 2 TB 同样 OOM；4 TB 可行（GPTQModel 6.1+ 显存优化更激进） | 扩 4 TB 后**优先试 AWQ**；若仍失败切 GPTQModel |
| **DeepSeek-V3 671B** | ✅ AWQ，10~16 h | ✅ GPTQ，14~20 h | **AWQ** |
| **DeepSeek-V4-Pro** | ❌ 无 BF16 源 | ❌ 无 BF16 源 | 两条路径都不适用 |

### 9.7 一句话结论

> **优先 AWQ**（LLM-Compressor）—— 精度与 GPTQ 持平、对 MoE 略优、耗时短 20~30%、vLLM `awq_marlin` 内核成熟。
> **GLM-5.2 这类超大 MoE**：根本性 CPU OOM 必须靠扩 RAM 解决（推荐 4 TB），算法选择是次要的；
> 真要在 AWQ 走不通时切 GPTQModel 6.1+ 当备胎，它针对 GLM 5/5.1 做过专门显存优化。

---

## 10. 参考资料（补充）

- [vLLM 支持的量化方法总表](https://docs.vllm.ai/en/stable/features/quantization/)
- [vLLM 在线 FP8 量化](https://docs.vllm.ai/en/stable/features/quantization/online)
- [GPTQModel 仓库](https://github.com/ModelCloud/GPTQModel)
- [AMD Quark MXFP4/MXFP6](https://docs.vllm.ai/en/stable/features/quantization/quark)
- [NVIDIA ModelOpt](https://docs.vllm.ai/en/stable/features/quantization/modelopt)
- [Intel AutoRound (INC)](https://docs.vllm.ai/en/stable/features/quantization/inc)
- [TorchAO 量化](https://docs.vllm.ai/en/stable/features/quantization/torchao)
