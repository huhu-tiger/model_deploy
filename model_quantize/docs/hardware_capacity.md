# 本机量化容量评估

> 在当前服务器（**两套硬件配置**：8 × H100 80GB 或 8 × H20 96GB，CPU RAM 当前 2 TB）上，
> 不同体量的模型在 BF16 → INT4（AWQ / GPTQ）量化流程中的可行性、推荐路径与上限。
> 适用于 `llmcompressor` 0.12+，量化算法以 AWQ W4A16 为主，兼顾 GPTQ。
> 文档同时给出 **CPU RAM 扩到 3 TB / 4 TB 后的能力变化**（见第 3 节）。

---

## 1. 本机硬件清单

| 组件 | H100 机 | H20 机 |
|---|---|---|
| CPU | 2 × Intel Xeon Platinum 8468（96C/192T，2 NUMA） | 同级配置 |
| 内存 | **2015 GiB**（系统可用 ~1980 GiB），DDR5，swap 仅 8 GiB | 同 |
| GPU | 8 × NVIDIA H100 80GB HBM3 | 8 × NVIDIA H20 96GB HBM3 |
| 单卡显存 | 80 GiB | **96 GiB** |
| 总显存（TP=8） | 640 GiB | **768 GiB** |
| FP16/BF16 算力 | ~989 TFLOPS/卡 | ~148 TFLOPS/卡（**约 H100 的 15%**） |
| HBM 带宽 | 3.35 TB/s | 4.0 TB/s（**略胜**） |
| GPU 互联 | NVLink（H100 集成） | NVLink 900 GB/s（同级） |
| 数据盘 | `/media`：21 TB，可用 ~16 TB | 通常 ≥ 16 TB |
| 容器运行时 | Docker + NVIDIA Runtime | 同 |

> **H100 vs H20**：算力 H100 远胜；显存与带宽 H20 更优；CPU/磁盘相同。
> 量化阶段瓶颈在 CPU RAM 与 PCIe，两者表现一致；推理阶段差异明显（见第 4 节）。

---

## 2. 量化路径的资源消耗模型

`llmcompressor` AWQ / GPTQ 在本机的标准路径是 **模式 A：单卡 sequential offload**：

> 全量 BF16 模型一次性加载到 CPU RAM，
> 量化时逐层将权重从 CPU 搬到 GPU，
> 校准 → 量化 → 写回 CPU/磁盘，
> 同一时刻 GPU 只持有 1~2 层权重。

下面的估算都基于这一路径（多卡 `device_map="auto"` 在 MoE 上有
公开未修复 bug，且 CPU RAM 占用并不下降，不在本机推荐范围内 — 见第 5 节）。

### 2.1 BF16 模型大小与权重文件总大小的关系

权重文件大小 ≈ 参数量 × 2 字节（BF16）。例如：
- 70 B 参数 → ~140 GiB（70 × 2）
- 235 B（Qwen3.6-A22B）→ ~470 GiB
- 671 B（DeepSeek-V3）→ ~1.3 TiB
- 1 T+（GLM-5.2 / Llama 4 Behemoth-class）→ ~1.4~2 TiB

> 实际下载到磁盘的 shard 数量（`model-*.safetensors`）只决定 I/O 时间，**不影响内存峰值**。

### 2.2 三个内存峰值（按 GiB 计）

| 峰值类型 | 公式 | 说明 |
|---|---|---|
| **CPU 常驻** | `model_size × 1.0` | from_pretrained 后全量留在 CPU |
| **MoE 解包瞬时** | `+ moe_layers × 1.0 × expert_dim`（典型 +18~36 GiB/层峰值） | 仅 MoE，3D 专家张量 → 逐专家 Linear 拆分时的双缓冲 |
| **AWQ 校准激活** | `+ batch × seq × hidden × 4 字节 × layers / N_seq_blocks`（一般 < 30 GiB） | sequential pipeline 已逐层释放，可忽略 |
| **GPU 单层** | `max_layer ≈ model_size / num_layers × 3`（MoE 大层经验值） | sequential offload 同一时刻 GPU 持有 1~2 层 |

> 安全余量：CPU 至少留 200 GiB 给 OS / Docker / PyTorch caching allocator 滞留，
> 否则在 MoE 解包后期触发主机级 `global_oom`（实测 GLM-5.2 在 ~2080 GiB RSS 处被杀）。

---

## 3. 本机量化能力上限

> 安全阈值：`CPU 可用 ≥ model_size × 1.2 + max_moe_layer_peak`。
> 当前 2 TB → 系统可用 ~1980 GiB，扣除 200 GiB OS 余量 ≈ **1780 GiB 可用预算**
> 扩到 3 TB → ~2750 GiB 预算；**扩到 4 TB → ~3760 GiB 预算**

| 模型体量 | 典型代表 | 权重磁盘 | CPU 峰值（含 MoE 解包） | 当前 2 TB | 扩到 3 TB | 扩到 4 TB | 推荐量化路径 |
|---|---|---|---|---|---|---|---|
| ≤ 70 B（dense） | Llama 3.3 70B、Qwen2.5 72B | ~140 GiB | ~180 GiB | ✅ 轻松 | ✅ 余 2570 GiB | ✅ 余 3580 GiB | 模式 A 单卡，2~4 h |
| 100~200 B（dense / 小 MoE） | Mixtral-8x22B、Command R+ | ~280~400 GiB | ~330~470 GiB | ✅ 轻松 | ✅ 余 2280 GiB | ✅ 余 3290 GiB | 模式 A 单卡，3~6 h |
| 200~400 B（中 MoE） | Qwen3-235B-A22B、Llama 4 Scout | ~470~800 GiB | ~580~960 GiB | ✅ 充裕 | ✅ 余 1790 GiB | ✅ 余 2800 GiB | 模式 A 单卡，6~10 h |
| 400~700 B（大 MoE） | DeepSeek-V3 671B、MiniMax-M3 | ~855~1.3 TiB | ~1.25~1.65 TiB | ⚠️ 临界（建议 swap 64 GiB） | ✅ 余 1100~1500 GiB | ✅ 余 2110~2510 GiB | 模式 A 单卡，6~16 h |
| 700~900 B（超大 MoE） | DeepSeek R1-class、Kimi K2 | ~1.5~1.8 TiB | ~1.8~2.0 TiB | ❌ 不推荐（极易 OOM） | ⚠️ 余 750 GiB（紧） | ✅ 余 1760 GiB | 模式 A 单卡，12~18 h |
| ≥ 1 T（如 GLM-5.2） | GLM-5.2 | ~1.4 TiB | ~1.65 TiB（修复 MoE 解包强引用后） | ❌ **实测 OOM** | ⚠️ **勉强够**（余 1100 GiB） | ✅ 余 2110 GiB（**完全可行**） | 模式 A 单卡，10~14 h |
| 1.5~2 TiB BF16 | 假设的 1.5T MoE、下一代大模型 | ~1.5~2.0 TiB | ~1.8~2.4 TiB | ❌ | ❌ | ✅ 余 1360~1960 GiB | 模式 A 单卡，14~20 h |
| ≥ 2.5 TiB BF16 | Llama 4 Behemoth（~4 TiB） | ≥ 2.5 TiB | ≥ 3.0 TiB | ❌ | ❌ | ⚠️ 临界或不够（4 TiB 模型仍超 4 TB 预算） | 需 6~8 TB RAM 或多节点 |

> 上限边界来自实测：GLM-5.2（1.4 TiB BF16）在 2 TB 机器上 MoE 解包到 30/75 层时
> `anon-rss` 达到 ~2080 GiB，触发 `global_oom` 杀掉容器。
> **修复 `glm_moe_calibration.py` 的 pending 强引用问题后**（已 commit），峰值理论值降到 ~1.65 TiB，
> 但仍超 2 TB 机器的 1780 GiB 可用预算 → **必须扩 CPU RAM 才能量化**。
>
> **CPU RAM 选型结论**：
> - 当前 **2 TB 不够** 量化 GLM-5.2（实测 OOM）
> - **3 TB 是勉强够**：理论余量 1100 GiB，但 PyTorch caching allocator 滞留 + AWQ 校准激活
>   叠加后仍可能触顶；建议同时扩 swap 到 64~128 GiB 兜底
> - **4 TB 是稳的**：余量 2110 GiB，无需特殊优化，并为未来 1.5~2 TiB BF16 模型预留空间

### 3.1 GPU 侧从未是瓶颈

模式 A 同一时刻 GPU 只持有 1~2 层权重；最大单层（MoE 256 专家）约
54 GiB（H100 80 GiB 留余量 26 GiB；H20 96 GiB 留余量 42 GiB）。
**所有上述模型都能在 1 张 H100 / H20 上 sequential offload 量化**，
其余 7 张卡空闲。多卡的意义只在推理阶段（TP）。

> **H20 单卡 96 GiB 比 H100 多 16 GiB，量化阶段用不上**——sequential offload 同一时刻只装 1~2 层，
> H100 的 80 GiB 已绰绰有余。H100 与 H20 的量化吞吐基本一致（瓶颈在 PCIe / CPU↔GPU 搬运，
> 不在 GPU 算力）。

### 3.2 磁盘空间

量化产物体积 ≈ BF16 × 0.30（INT4 W4A16）。
本机可用 16 TiB，对任意上述模型都不构成约束。

---

## 4. 推理（vLLM）阶段的容量

量化产物在本机推理永远不是瓶颈。两套硬件总显存差 128 GiB（H100 机 640 GiB / H20 机 768 GiB），
单卡也差 16 GiB（80 GiB / 96 GiB），对长上下文 KV cache 容量差异明显：

| 模型体量 | INT4 体积 | 单卡占用（TP=8） | H100 机 (640 GiB) | H20 机 (768 GiB) |
|---|---|---|---|---|
| 70 B | ~35 GiB | 4~5 GiB | ✅ TP=2 即可 | ✅ TP=2 即可 |
| 235 B | ~120 GiB | ~15 GiB | ✅ TP=4 或 TP=8 | ✅ KV cache 余量更足 |
| 671 B（DeepSeek-V3） | ~340 GiB | ~43 GiB | ✅ TP=8 | ✅ 余 ~428 GiB 给 KV cache |
| 1 T+（GLM-5.2） | ~400~500 GiB | ~50~62 GiB | ✅ 余 ~140 GiB | ✅ 余 ~268 GiB |

**BF16 直跑能力**（无量化、`vllm serve` 不带 `--quantization`）：

| 模型 | BF16 总占用 | H100 机 | H20 机 |
|---|---|---|---|
| Qwen3.6-35B-A3B | 70 GiB | ✅ 单卡即可 | ✅ 单卡即可 |
| Qwen3-MoE 235B | 470 GiB | ✅ TP=8 余 ~170 GiB | ✅ TP=8 余 ~298 GiB |
| MiniMax-M3 | 855 GiB | ❌ 超总显存 | ❌ 超总显存（仍差 87 GiB） |
| GLM-5.2 | 1.4 TiB | ❌ | ❌ |

> 启动命令模板：
> ```
> vllm serve <path> --quantization awq_marlin --tensor-parallel-size 8
> ```
> H100 / H20 + `awq_marlin` 内核都已生产可用。

### 4.1 H100 vs H20 推理性能差异

| 场景 | 瓶颈 | H100 vs H20 |
|---|---|---|
| **decode 阶段**（生成 token） | HBM 带宽主导 | H20 略胜（4.0 vs 3.35 TB/s） |
| **prefill 阶段**（处理输入） | FP16/BF16 算力主导 | **H100 快 5~6×**（989 vs 148 TFLOPS） |
| **长上下文（128k+）KV cache** | 显存容量主导 | **H20 明显更优**（单卡 +16 GiB → KV cache ~翻倍） |
| **大并发** | 显存容量主导 | H20 更优 |

**选型建议**：
- 长上下文推理、大并发、decode 主导（聊天）→ **H20 机更优**
- 大批量短输入、prefill 主导（RAG、批处理）→ **H100 机更优**
- 仅做量化 → 任一台皆可，吞吐看 PCIe

---

## 5. 关于多卡（`device_map="auto"`）

社区现状（参考 `vllm-project/llm-compressor` issue #1939、#2068）：

- AWQ + MoE + `device_map="auto"` 在 sequential pipeline 上有未修复 bug
  （autowrapped forward 与 sequential_targets 不匹配）。
- 即使加载成功，BF16 全权重仍需先在 CPU 物化再分发，**CPU 峰值不下降**。
- 本仓库 `Glm-5.2-AWQ-H100/README.md` 已记录：模式 B 在 transformers 5.10.1
  + GLM-5.2 上 `MergeModulelist` 峰值 36 GiB/层 > 单卡剩余 25 GiB，
  导致 1202 个参数停留在 `meta` 设备无法前向。

**结论**：本机量化路径锁定模式 A 单卡 sequential offload，
不要花精力在 device_map / torchrun 分布式上。

---

## 6. 实操检查清单

启动量化前先核对：

```bash
# 1. CPU 可用内存（必须 ≥ model_size × 1.2 + 200 GiB OS 余量）
free -g

# 2. swap 容量（超大模型建议临时扩到 64 GiB 兜底）
cat /proc/swaps

# 3. GPU 空闲
nvidia-smi --query-gpu=index,memory.used --format=csv

# 4. 磁盘可用（INT4 产物约 model_size × 0.30）
df -h /media

# 5. 权重 shard 完整
ls /media/llm/.../<model>/model-*.safetensors | wc -l
```

各量化项目目录下的 `quantize_llmcompressor.py` 已内置
`run_resource_preflight()`，会在开跑前打印这套检查，
若 ❌ 项存在请先扩资源再继续。

---

## 7. 量化时长经验值（H100 / H20 单卡，模式 A）

| 体量 | 校准样本 | 预计耗时 | 主要瓶颈 | CPU RAM 要求 |
|---|---|---|---|---|
| 70 B dense | 256 | 2~4 h | PCIe（CPU↔GPU 逐层搬运） | 当前 2 TB ✅ |
| 235 B MoE | 384 | 5~8 h | PCIe + MoE 解包 | 当前 2 TB ✅ |
| 671 B MoE | 512 | 10~16 h | PCIe + MoE 解包 | 当前 2 TB ⚠️ 临界 |
| 855 GiB MoE（MiniMax-M3） | 384 | 6~10 h | PCIe + MoE 解包 | 当前 2 TB ⚠️；3 TB+ ✅ |
| 1 T+ MoE（GLM-5.2） | 512 | 10~14 h | PCIe + MoE 解包 | 当前 2 TB ❌；3 TB ⚠️ 勉强；4 TB ✅ |

> 校准样本数对耗时是线性影响；超过 512 条对精度提升非常有限。
> **H100 与 H20 量化耗时基本相同**——sequential offload 阶段 GPU 算力不饱和，
> 瓶颈在 PCIe 搬运（CPU RAM ↔ GPU），H20 算力削弱不影响量化吞吐。

---

## 8. 如果一定要量化超过本机上限的模型

按优先级排：

1. **扩 CPU RAM** —— 一劳永逸；GLM-5.2 推荐 4 TB，DeepSeek R1-class 推荐 3 TB
2. **借用更大内存的临时机器做量化**，量化产物拷回本机推理（产物仅 ~400 GiB）
3. **改流式 from_pretrained**：边加载边逐层 `to(dtype=torch.uint8) + AWQ scale`
   写回磁盘，避免全量 BF16 常驻 CPU。需要改 `glm_moe_calibration.py`
   的解包流程并接管 `from_pretrained`，工作量较大且容错性差，仅作为最后手段
4. **临时扩 swap 到 256 GiB** —— 能让临界模型勉强跑完，
   但速度被 swap 拖慢一个量级，且仍可能在解包高峰被 OOM-killer 击中，**不推荐**

---

## 9. 一句话总结

> **当前 2 TB 机器**：本机适合量化 **权重 ≤ ~900 GiB（参数 ≤ ~450 B BF16）** 的模型。
> 超过 1 TiB 的模型（如 GLM-5.2）请勿在本机量化，避开 CPU OOM。
>
> **扩到 3 TB**：可勉强量化 GLM-5.2、DeepSeek R1-class（建议扩 swap 兜底）。
>
> **扩到 4 TB**：可稳定量化 ≤ 2 TiB BF16 的模型，并为下一代 1.5~2 TiB 大 MoE 预留空间。
>
> 推理阶段：8 × H100（640 GiB 显存）或 8 × H20（768 GiB 显存）对 INT4 产物都游刃有余；
> 超过总显存的 BF16 直跑则需要 H200/B200 或多节点。

---

## 10. 具体模型评估

下表把本机量化与推理上限套用到四个代表性模型。
"BF16 体积"按 `参数 × 2 字节` 估算，与 HuggingFace 实际 shard 总大小一致。
量化列按 2 TB / 3 TB / 4 TB 三档 CPU RAM 给出能力；推理列分别给出 H100 机（640 GiB）与 H20 机（768 GiB）。

| 模型 | 架构 / 参数 | BF16 体积 | 量化 CPU 峰值 | 2 TB | 3 TB | 4 TB | H100 机推理 | H20 机推理 |
|---|---|---|---|---|---|---|---|---|
| **Qwen3.6-35B-A3B** | MoE，35B/3B，40 层，256 专家+1 shared | ~70 GiB | ~120 GiB | ✅ 强烈推荐 | ✅ 过剩 | ✅ 过剩 | ✅ 单卡（INT4 ~20 GiB） | ✅ 单卡，KV cache 余量更足 |
| **MiniMax-M3** | MoE，427B/23~26B，60 层，128 专家+1 shared，MSA | ~855 GiB | ~1.25 TiB | ⚠️ 临界（扩 swap） | ✅ 余 ~1500 GiB | ✅ 余 ~2510 GiB | ✅ INT4 ~256 GiB | ✅ INT4，余量更足 |
| **GLM-5.2** | MoE，~700B，78 层，256 专家+1 shared，DSA | ~1.4 TiB | ~1.65 TiB（修 pending 强引用后） | ❌ 实测 OOM | ⚠️ 勉强（扩 swap） | ✅ 余 ~2110 GiB | ✅ TP=8 INT4 ~50 GiB/卡 | ✅ TP=8，KV cache 余 ~268 GiB |
| **DeepSeek-V4-Pro** | MoE，1.6T/49B，61 层，384 专家+1 shared，**原生 FP4+FP8**（无 BF16） | 磁盘 ~862 GiB；BF16 等价 ~3.2 TiB | 不适用（无 BF16 源） | ❌ 无入口 | ❌ 无入口 | ❌ 无入口 | ❌ 装不下 862 GiB | ❌ 仍超 ~94 GiB |

### 10.1 Qwen3.6-35B-A3B —— ✅ 最佳量化目标

- BF16 仅 ~70 GiB，CPU 峰值估算 ~120 GiB，任何 CPU 配置都绰绰有余
- MoE 解包 40 层、每层峰值 ~3 GiB（128 expert × dim=512），远低于 GLM-5.2 的 18 GiB/层
- 预计量化耗时 **2~4 小时**（H100 / H20 单卡 sequential offload，两机耗时基本相同）
- 校准建议：`HuggingFaceH4/ultrachat_200k(256) + cyankiwi/calibration(128)`，共 384 条
- 已有 `model_quantize/Qwen3.6-35B-A3B-AWQ/` 项目目录可直接用
- 推理：H100 / H20 单卡均可；H20 略胜在 decode 与长上下文

### 10.2 GLM-5.2 —— 量化需扩内存，推理可行

- BF16 1.4 TiB + MoE 解包瞬时 ~18 GiB/层（修 pending 强引用后逐层释放）→ 峰值估算 ~1.65 TiB
- **2 TB 机器实测 OOM**：MoE 解包到 30/75 层时 anon-rss ~2080 GiB > 2015 GiB
- **3 TB 勉强够**（余 ~1100 GiB，但 PyTorch caching allocator + AWQ 校准激活叠加仍可能触顶；建议扩 swap 到 64~128 GiB 兜底）
- **4 TB 是稳的**（余 ~2110 GiB，无需特殊优化）
- 推理路径不受 CPU RAM 影响：INT4 ~400 GiB，TP=8 每卡 50 GiB；H20 机 KV cache 余量比 H100 机多 ~128 GiB
- 启动命令：
  ```bash
  vllm serve /media/llm/ZhipuAI/GLM-5.2-AWQ-4bit-LC \
    --quantization awq_marlin --tensor-parallel-size 8
  ```
- 当前 2 TB 机器的替代方案：
  1. 借 ≥ 4 TB CPU RAM 的机器量化，产物拷回本机推理（~400 GiB 数据量）
  2. 改 `quantize_llmcompressor.py` 为流式 from_pretrained（逐 shard 加载 + 解包 + 卸载）
  3. 切换到 GPTQModel（6.1+ 已显式支持 GLM 5/5.1，CPU 峰值与 AWQ 接近，但 GLM 专项优化更激进）

### 10.3 MiniMax-M3 —— ⚠️ 2 TB 临界，3 TB+ 稳

- BF16 855 GiB，CPU 峰值预估 855 × 1.2 + ~36 GiB（128 expert MoE 解包峰值）≈ 1.25 TiB
- **2 TB 临界可行**：在 1780 GiB 安全预算内但留余量不大；建议：
  - 量化前 `free -g` 确认 used < 50 GiB
  - 扩 swap 到 64 GiB 兜底（命令：`fallocate -l 64G /swap2 && chmod 600 /swap2 && mkswap /swap2 && swapon /swap2`）
  - 校准样本数控制在 256~384，避免拉高激活缓存峰值
  - 关闭其他容器，释放 CPU caching
- **3 TB 充裕**（余 ~1500 GiB），**4 TB 过剩**
- 预计耗时 6~10 小时；产物 INT4 ~256 GiB
- 推理：H100 / H20 均可（INT4 256 GiB << 640 GiB）；H20 在长上下文场景更优
- **BF16 直跑：H100 机和 H20 机都装不下**（855 > 768 GiB），必须量化

### 10.4 DeepSeek-V4-Pro —— ❌ 量化无源、推理超本机能力

- **官方未发布 BF16 权重**。ModelScope / HuggingFace 上只发布两个版本：
  - **Base**：FP8 Mixed
  - **Instruct**：FP4 + FP8 Mixed（MoE 专家 FP4，其余 FP8）
- 磁盘体积 ~862 GiB（Instruct），不是 BF16 的 3.2 TiB
- 量化路径不存在：llm-compressor / AutoAWQ / GPTQModel 的 AWQ/GPTQ 入口都要求 BF16/FP16 源；从 FP4/FP8 反量化到 BF16 再 INT4 信息损失叠加，得不偿失
- 推理：
  - H100 机 640 GiB < 862 GiB，**装不下**
  - H20 机 768 GiB < 862 GiB，**仍差 ~94 GiB 装不下**
  - 需要 8 × B200 NVLink、8 × H200 141GB 或多节点
- 兄弟版本 **DeepSeek V4-Flash（284B-A13B）**：FP4+FP8 ~158 GiB，可在单 H200 节点跑；如果官方提供 BF16 版（~568 GiB），本机量化也可行
- **结论**：V4-Pro 量化和推理都不在本机能力范围内；用 V4-Flash 或退回 V3.2-Exp/R1

### 10.5 选型快速决策树

```
量化能力（按 CPU RAM 切分；GPU 型号无关）：
  当前 2 TB：
    BF16 ≤ 200 GiB     → ✅ 推荐（Qwen3.6-35B-A3B）
    200~800 GiB         → ✅ 可行
    800 GiB~1.3 TiB     → ⚠️ 临界（MiniMax-M3、DeepSeek-V3）
    > 1.3 TiB           → ❌ 不要量化（GLM-5.2 等）

  扩到 3 TB：
    ≤ 1.4 TiB           → ⚠️ 勉强（GLM-5.2，需 swap 兜底）
    1.4~1.8 TiB         → ❌（DeepSeek R1-class、Kimi K2）
    > 1.8 TiB           → ❌

  扩到 4 TB：
    ≤ 2.0 TiB           → ✅ 稳的（覆盖 GLM-5.2、R1-class）
    2.0~2.5 TiB         → ⚠️ 临界
    > 2.5 TiB           → ❌（Llama 4 Behemoth 需 6~8 TB）

推理能力（按总显存切分）：
  ≤ 640 GiB 权重 → H100 / H20 均可
  640~768 GiB 权重 → 仅 H20 机可行
  > 768 GiB 权重 → 都不够，需 H200/B200 或多节点

H100 vs H20 二选一：
  长上下文 / 大并发 / decode 主导（聊天）       → H20 机
  短输入大批量 / prefill 主导（RAG、批处理）    → H100 机
  仅做量化                                      → 任一台均可
```
