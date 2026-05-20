# Qwen3-Coder-30B-A3B 部署说明

## 模型信息

| 项目 | 说明 |
|------|------|
| 模型 | Qwen3-Coder-30B-A3B-Instruct |
| 架构 | MoE（混合专家），30B 总参数，激活约 3B，共 48 层，8 个 KV 头 |
| GGUF 来源 | [unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF](https://huggingface.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF) |
| 当前量化文件 | `Qwen3-Coder-30B-A3B-Instruct-UD-Q8_K_XL.gguf`（36 GB） |
| 本地路径 | `/media/llm/Qwen/Qwen3-Coder-30B-A3B-Instruct-GGUF/` |

---

## 部署方案对比

| 方案 | 文件 | 端口 | 适用场景 |
|------|------|------|---------|
| **llama.cpp（推荐）** | `docker-compose-llamacpp.yml` | 30002 | GGUF 原生推理，支持 MoE，高并发 |
| vLLM + bitsandbytes | `docker-compose-vllm.yml` | 30001 | safetensors 格式，INT8 运行时量化 |

> **为什么 vLLM 无法加载 GGUF：**
> vLLM v0.20.2 的 GGUF 加载器不支持 MoE 架构的 `experts.gate_up_proj` 参数映射，
> 启动会报 `RuntimeError: Failed to map GGUF parameters (48)`。
> GGUF 文件必须通过 llama.cpp 加载；若使用 vLLM，需要 safetensors 格式的模型目录。

---

## 方案一：llama.cpp（docker-compose-llamacpp.yml）

### 启动 / 停止

```bash
# 启动
docker compose -f docker-compose-llamacpp.yml up -d

# 查看日志
docker logs -f Qwen3-Coder-30B-A3B-LlamaCpp

# 停止
docker compose -f docker-compose-llamacpp.yml down
```

### 启动参数说明

> `full-cuda` 镜像的入口是包装脚本，需先指定子命令 `--server`，参数使用短选项格式。
> `-fa` 必须显式写 `-fa on`，否则后面的参数（如 `-cb`）会被误解析为其值。

| 参数 | 值 | 说明 |
|------|----|------|
| `--server` | — | full-cuda 镜像子命令，以 HTTP 服务模式启动 |
| `-m` | `...UD-Q8_K_XL.gguf` | 模型文件路径 |
| `-ngl` | `99` | GPU 卸载层数，99 表示全部层加载到 GPU |
| `-c` | `32768` | 最大上下文长度（tokens），支持超长代码文件 |
| `-fa on` | `on` | Flash Attention：降低显存占用约 30%，提升推理速度，A800 Ampere 架构支持 |
| `-cb` | — | 连续批处理（Continuous Batching）：多请求并发无需等待前一个完成，大幅提升吞吐量 |
| `-np` | `8` | 并行处理槽数，最多同时处理 8 路请求，配合 `-cb` 使用 |
| `-b` | `4096` | Prompt 批处理大小（tokens），增大可提升长 prompt 的处理吞吐 |
| `-ub` | `2048` | Micro-batch 大小：decode 阶段每次 GPU 计算粒度，高并发时增大可提升利用率 |
| `-ctk` | `q4_0` | KV Cache Key 量化为 4-bit，节省约 75% KV Cache 显存 |
| `-ctv` | `q4_0` | KV Cache Value 量化为 4-bit |
| `--numa distribute` | — | NUMA 内存分配策略，将内存分散到所有节点，降低 CPU→GPU 传输延迟 |
| `--no-mmap` | — | 禁用内存映射，模型直接全量读入内存，避免 IO 抖动 |
| `--host` | `0.0.0.0` | 监听所有网络接口 |
| `--port` | `30002` | 服务端口 |

### 显存分配（A800 80GB）

```
模型权重 (UD-Q8_K_XL)         : ~36 GB
KV Cache (32768 × 8slots × q4_0): ~12 GB
合计                            : ~48 GB  ✅ 安全范围内，余量约 32GB
```

### 环境变量

| 变量 | 值 | 说明 |
|------|----|------|
| `NVIDIA_VISIBLE_DEVICES` | `2` | 指定使用第 3 张 GPU（从 0 开始编号） |

### API 调用示例

```bash
# 检查服务健康状态
curl http://localhost:30002/health

# 查看实际模型名称
curl http://localhost:30002/v1/models

# Chat Completions（默认开启思考模式）
curl http://localhost:30002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-Coder-30B-A3B-Instruct-UD-Q8_K_XL.gguf",
    "messages": [{"role": "user", "content": "用 Python 写一个快速排序"}]
  }'

# 关闭思考模式（响应速度提升 30-50%，适合代码补全等简单任务）
curl http://localhost:30002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-Coder-30B-A3B-Instruct-UD-Q8_K_XL.gguf",
    "messages": [
      {"role": "system", "content": "/no_think"},
      {"role": "user", "content": "解释 MoE 架构"}
    ]
  }'
```

---

## 方案二：vLLM + bitsandbytes（docker-compose-vllm.yml）

### 启动 / 停止

```bash
# 启动
docker compose -f docker-compose-vllm.yml up -d

# 查看日志
docker logs -f Qwen3-Coder-30B-A3B-GGUF

# 停止
docker compose -f docker-compose-vllm.yml down
```

### 启动参数说明

| 参数 | 值 | 说明 |
|------|----|------|
| 模型路径（位置参数） | `/media/llm/Qwen/Qwen3-Coder-30B-A3B-Instruct` | safetensors 格式模型目录 |
| `--served-model-name` | `Qwen3-Coder-30B-A3B-Instruct` | API 请求时使用的模型名称，未设置则默认为完整路径 |
| `--quantization` | `bitsandbytes` | 运行时 INT8 量化，无需预量化文件，A800 Ampere 原生支持 |
| `--load-format` | `bitsandbytes` | 配合 bitsandbytes 量化的加载格式 |
| `--dtype` | `auto` | 自动选择数据类型（A800 自动选 BF16） |
| `--gpu-memory-utilization` | `0.9` | GPU 显存使用上限比例，90% 用于模型权重 + KV Cache |
| `--max-model-len` | `8192` | 最大序列长度（prompt + 生成 tokens 之和） |
| `--host` | `0.0.0.0` | 监听所有网络接口 |
| `--port` | `30001` | 服务端口 |

### 各量化方式对 A800 的支持

| 量化方式 | A800 支持 | 说明 |
|---------|----------|------|
| `bitsandbytes` INT8 | ✅ | Ampere (8.0) 原生 INT8 Tensor Core，当前使用 |
| `fp8` | ❌ | 需要 Hopper (H800/H100) 或 Ada 架构 |
| `awq` / `gptq` | ✅ | 需预量化好的对应格式模型 |
| BF16 全精度 | ✅ | 需 ~60GB 显存，适合 80GB 卡 |

### 显存分配（A800 40GB）

```
模型权重 (INT8 bitsandbytes): ~30 GB
KV Cache (8192 ctx)         :  ~6 GB
合计                         : ~36 GB  ✅ 适用 40GB 显卡
```

### API 调用示例

```bash
# 检查服务健康状态
curl http://localhost:30001/health

# Chat Completions
curl http://localhost:30001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-Coder-30B-A3B-Instruct",
    "messages": [{"role": "user", "content": "用 Python 写一个快速排序"}]
  }'
```

---

## KV Cache 量化选择指南

> KV Cache 量化（`-ctk` / `-ctv`）与模型权重文件独立，控制运行时注意力缓存的精度。

### 核心原则：KV Cache 精度应 ≥ 模型权重精度

| 模型权重 | 推荐 KV Cache | 原因 |
|---------|-------------|------|
| Q8 / UD-Q8（8-bit） | `q4_0` 或 `q8_0` | 权重精度高，KV 可适当压缩节省显存 |
| Q4 / UD-Q4（4-bit） | `q8_0`（推荐） | 补偿权重量化误差，避免双重叠加 |
| Q4 / UD-Q4（4-bit） | `f16`（最佳） | 显存充裕时用全精度 KV，效果最好 |
| Q4 / UD-Q4（4-bit） | `q4_0`（不推荐） | 双重 4-bit 误差叠加，长上下文质量明显下降 |

### 不同 KV Cache 精度的显存对比

> 基于 Qwen3-Coder-30B-A3B：48 层，8 个 KV 头，head_dim=128

| KV Cache 精度 | ctx=32768 × 8 slots | ctx=32768 × 4 slots | 适用场景 |
|-------------|--------------------|--------------------|---------|
| `f16`（16-bit） | ~48 GB | ~24 GB | 最高质量，低并发 |
| `q8_0`（8-bit） | ~24 GB | ~12 GB | 质量与显存均衡 |
| `q4_0`（4-bit） | ~12 GB | ~6 GB | 节省显存，高并发 |

---

## 量化版本选择参考

### 标准量化（ggml-org 格式）

| 文件 | 大小 | 适用显存 | 质量 | 说明 |
|------|------|---------|------|------|
| `Q8_0.gguf` | 32.5 GB | 40GB+ | ★★★★★ | 标准 8-bit，近乎无损 |
| `Q6_K.gguf` | 25.1 GB | 40GB+ | ★★★★☆ | 接近 Q8 质量，更省显存 |
| `Q5_K_M.gguf` | 21.7 GB | 24GB+ | ★★★★☆ | 5-bit 推荐版 |
| `Q4_K_M.gguf` | 18.6 GB | 24GB+ | ★★★☆☆ | **4-bit 标准推荐** |
| `Q4_0.gguf` | 17.4 GB | 24GB+ | ★★★☆☆ | 早期格式，不推荐 |
| `Q3_K_M.gguf` | 14.7 GB | 16GB+ | ★★☆☆☆ | 质量一般 |
| `Q2_K.gguf` | 11.3 GB | 12GB+ | ★☆☆☆☆ | 极限压缩，质量差 |
| `IQ4_XS.gguf` | 16.4 GB | 24GB+ | ★★★★☆ | imatrix 量化，比 Q4_K_S 好 |

### UD 系列（Unsloth Dynamic 动态量化）

> 对每层动态分配精度：Attention、Embedding、首尾层等关键层保留更高精度，**同等大小下质量优于标准量化**。

| 文件 | 大小 | 适用显存 | 质量 | 说明 |
|------|------|---------|------|------|
| `UD-Q8_K_XL.gguf` | 36 GB | 80GB | ★★★★★ | **当前使用**，8-bit 最高质量 |
| `UD-Q6_K_XL.gguf` | 26.3 GB | 40GB+ | ★★★★★ | 6-bit 最佳，接近 Q8 |
| `UD-Q5_K_XL.gguf` | 21.7 GB | 24GB+ | ★★★★☆ | 5-bit 最佳 |
| `UD-Q4_K_XL.gguf` | 17.7 GB | 24GB+ | ★★★★☆ | **4-bit 首选**，优于 Q4_K_M |
| `UD-Q3_K_XL.gguf` | 13.8 GB | 16GB+ | ★★★☆☆ | 3-bit 最佳 |
| `UD-Q2_K_XL.gguf` | 11.8 GB | 12GB+ | ★★☆☆☆ | 2-bit 最佳 |
| `UD-IQ2_M.gguf` | 10.8 GB | 12GB+ | ★★☆☆☆ | 极限压缩 |
| `UD-TQ1_0.gguf` | 8.01 GB | 10GB+ | ★☆☆☆☆ | 三值量化，仅测试用 |

### 按显存快速选择

| 可用显存 | 推荐文件 | 推理速度 |
|---------|---------|---------|
| 80 GB | `UD-Q8_K_XL`（当前） | 基准 1× |
| 48 GB | `UD-Q6_K_XL` | ~1.4× |
| 40 GB | `Q8_0` 或 `UD-Q6_K_XL` | ~1.4× |
| 24 GB | `UD-Q4_K_XL` | ~2× |
| 16 GB | `UD-Q3_K_XL` | ~2.5× |

> 推理速度（token/s）受显存带宽限制，模型越小读取越快，单用户延迟越低。
> `UD-Q4_K_XL` 在 80GB 卡上速度约为 `UD-Q8_K_XL` 的 2 倍，适合对延迟敏感的代码补全场景。

---

## 换用 4-bit 模型的配置调整

将模型文件换为 `UD-Q4_K_XL.gguf` 后，建议同步调整以下参数：

```yaml
- "-m"
- "/media/llm/.../Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf"
- "-np"
- "12"       # 4-bit 模型仅占 ~18GB，显存充裕，可增加并发槽
- "-ctk"
- "q8_0"     # KV Cache 精度须高于模型权重精度，避免误差叠加
- "-ctv"
- "q8_0"
```

**4-bit vs 8-bit 综合对比（A800 80GB 单卡）：**

| 指标 | UD-Q8_K_XL | UD-Q4_K_XL |
|------|-----------|-----------|
| 模型大小 | 36 GB | 17.7 GB |
| 单用户推理速度 | 基准 | **~2×** |
| 最大并发槽（q8_0 KV） | 8 slots | **12-16 slots** |
| 输出质量（代码补全） | ★★★★★ | ★★★★☆ |
| 输出质量（复杂推理） | ★★★★★ | ★★★★☆ |
