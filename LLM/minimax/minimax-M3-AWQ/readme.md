# MiniMax-M3-AWQ-INT4 vLLM 部署

模型权重与说明：

- ModelScope: https://modelscope.cn/models/cyankiwi/MiniMax-M3-AWQ-INT4
- HuggingFace: https://huggingface.co/cyankiwi/MiniMax-M3-AWQ-INT4

本目录提供三种 Docker 镜像构建方案，均基于 [toncao/vllm](https://github.com/toncao/vllm) 的 `minimax-m3-compressed-tensors` 分支（补丁 commit `8f1350eb`），用于在 vLLM 上推理 AWQ INT4 量化版 MiniMax-M3。

**权重路径（宿主机）**：`/media/llm/cyankiwi/MiniMax-M3-AWQ-INT4`  
**服务端口**：`30001`  
**容器名**：`MiniMax-M3-AWQ-INT4-vLLM`

---

## 方案对比

| 方案 | Dockerfile | 镜像 tag | 构建耗时 | 稳定性 | 说明 |
|------|------------|----------|----------|--------|------|
| **A（默认/推荐）** | `Dockerfile.minimax-m3` | `minimax-m3-awq` | ~5–10 min | 高 | `minimax-m3` 底座 + git diff 补丁，保留 M3 CUDA 算子 |
| **B** | `Dockerfile` | `minimax-m3-awq-source` | ~1–3 h | 中 | 全量源码编译，与 a7fdfeef 严格同源；需 GitHub 代理 |
| **precompiled** | `Dockerfile.precompiled` | `minimax-m3-awq-precompiled` | ~30 min | 低 | 官方 README 流程；预编译 wheel **不含 M3 算子**，不建议生产 |

> **生产环境请用方案 A。** 方案 B 适合必须本地全量编译的场景；precompiled 仅作对照实验。

---

## 前置条件

1. 已安装 Docker、NVIDIA Container Toolkit，`docker compose` 可用。
2. 宿主机已挂载模型目录：`/media/llm/cyankiwi/MiniMax-M3-AWQ-INT4`。
3. 8× H100（或与 `docker-compose.yml` 中 `tensor-parallel-size` / GPU 列表一致）。
4. 内网构建需能拉取基础镜像；git clone 默认走代理（见下方「可调参数」）。

进入目录：

```bash
cd /media/source/model_deploy/LLM/minimax/minimax-M3-AWQ
```

查看所有 Make 目标：

```bash
make help
```

---

## 方案 A — minimax-m3 底座 + 补丁（推荐）

**Dockerfile**：`Dockerfile.minimax-m3`  
**镜像**：`model.vnet.com/sjhl/vllm-openai:minimax-m3-awq`  
**基础镜像**：`model.vnet.com/sjhl/vllm-openai:minimax-m3`

### 拉取基础镜像

```bash
make pull-base-a
```

### 仅构建镜像

```bash
make build
# 或
make build-a
```

### 构建并启动

```bash
make up
# 或
make up-a
```

### 停止

```bash
make down
```

### 重启 / 日志 / 状态

```bash
make restart
make logs
make ps
```

---

## 方案 B — 源码编译

**Dockerfile**：`Dockerfile`  
**镜像**：`model.vnet.com/sjhl/vllm-openai:minimax-m3-awq-source`  
**基础镜像**：`model.vnet.com/sjhl/vllm-openai:v0.23.0`

全量 `pip install -e .` 编译 CUDA kernel；cmake 会经代理拉取 cutlass 等 GitHub 依赖。

### 拉取基础镜像

```bash
make pull-base-b
```

### 仅构建镜像

```bash
make build-b
```

可调编译并行度（默认 `MAX_JOBS=64`，`NVCC_THREADS=4`）：

```bash
make build-b MAX_JOBS=64 NVCC_THREADS=4
# 更保守
make build-b MAX_JOBS=32 NVCC_THREADS=2
```

### 构建并启动

```bash
make up-b
```

### 停止

```bash
make down
```

### 重启 / 日志 / 状态

```bash
make restart
make logs
make ps
```

---

## 方案 precompiled — uv + 预编译 wheel（不推荐生产）

**Dockerfile**：`Dockerfile.precompiled`  
**镜像**：`model.vnet.com/sjhl/vllm-openai:minimax-m3-awq-precompiled`  
**基础镜像**：默认 `nvidia/cuda:13.0.2-devel-ubuntu22.04`（`make` 通过 `CUDA_BASE` 传入）

预编译包来自 vLLM 主线，**不包含** `fused_minimax_m3_qknorm_rope_kv_insert` 等 M3 算子，构建验证步骤通常会失败。

内网请指定镜像仓库：

```bash
make build-precompiled CUDA_BASE=model.vnet.com/sjhl/cuda:13.0.2-devel-ubuntu22.04
```

### 拉取基础镜像

```bash
make pull-base-precompiled
# 内网示例
make pull-base-precompiled CUDA_BASE=model.vnet.com/sjhl/cuda:13.0.2-devel-ubuntu22.04
```

### 仅构建镜像

```bash
make build-precompiled
```

### 构建并启动

```bash
make up-precompiled
```

### 停止

```bash
make down
```

### 重启 / 日志 / 状态

```bash
make restart
make logs
make ps
```

---

## 运维命令（三方案通用）

`docker-compose.yml` 通过环境变量 `IMAGE` 选择镜像；各方案的 `make up*` 会自动设置对应 `IMAGE`。

| 操作 | 命令 |
|------|------|
| 停止并移除容器 | `make down` |
| 重启当前容器 | `make restart` |
| 跟踪日志 | `make logs` |
| 查看运行状态 | `make ps` |
| 健康检查 | `curl -f http://127.0.0.1:30001/health` |

**切换方案时**：先 `make down`，再用目标方案的 `make up` / `make up-b` / `make up-precompiled` 启动，避免旧容器占用 GPU。

---

## 可调参数（Make 变量）

| 变量 | 默认值 | 适用方案 | 说明 |
|------|--------|----------|------|
| `HTTP_PROXY` | `http://172.31.0.55:20171` | A / B / precompiled | git clone 与 cmake 拉子模块；直连 GitHub 时置空 |
| `HTTPS_PROXY` | 同 `HTTP_PROXY` | 同上 | |
| `MAX_JOBS` | `64` | B / precompiled | vLLM 源码编译并行度 |
| `NVCC_THREADS` | `4` | B / precompiled | 单个 nvcc 进程线程数 |
| `BASE_IMAGE_A` | `.../minimax-m3` | A | 方案 A 基础镜像 |
| `BASE_IMAGE_B` | `.../v0.23.0` | B | 方案 B 基础镜像 |
| `CUDA_BASE` | `nvidia/cuda:13.0.2-devel-ubuntu22.04` | precompiled | 方案 precompiled 基础镜像 |
| `IMAGE` | 方案 A 镜像 | compose | `make up-b` 等目标会自动覆盖 |

示例：

```bash
# 禁用 git 代理
make build-a HTTP_PROXY= HTTPS_PROXY=

# 方案 B 保守编译
make build-b MAX_JOBS=32 NVCC_THREADS=2

# 手动指定 compose 镜像（已构建好的方案 B 镜像）
IMAGE=model.vnet.com/sjhl/vllm-openai:minimax-m3-awq-source docker compose up -d
```

---

## 运行参数要点

`docker-compose.yml` 中关键配置（**请勿随意修改**）：

- `--block-size 128`：MSA 稀疏注意力硬性要求，不可改为 `16`。
- `--tensor-parallel-size 8`：8 卡张量并行；AWQ INT4 权重约 240GB，单卡约 30GB。
- `--max-model-len 131072`：可按显存与业务调低。
- `--tool-call-parser minimax_m3` / `--reasoning-parser minimax_m3`：MiniMax-M3 工具调用与推理格式。

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `Makefile` | 构建、启动、停止等统一入口 |
| `docker-compose.yml` | vLLM 服务编排 |
| `Dockerfile.minimax-m3` | 方案 A |
| `Dockerfile` | 方案 B |
| `Dockerfile.precompiled` | precompiled 方案 |
