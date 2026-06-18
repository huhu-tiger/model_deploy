# MiniMax-M3-AWQ-INT4 vLLM 部署

模型权重与说明：

- ModelScope: https://modelscope.cn/models/cyankiwi/MiniMax-M3-AWQ-INT4
- HuggingFace: https://huggingface.co/cyankiwi/MiniMax-M3-AWQ-INT4

基于 [toncao/vllm](https://github.com/toncao/vllm) 的 `minimax-m3-compressed-tensors` 分支（commit `8f1350eb`），在 `minimax-m3` 底座镜像上施加最小 Python 补丁，用于在 vLLM 上推理 AWQ INT4 量化版 MiniMax-M3。

**权重路径（宿主机）**：`/media/llm/cyankiwi/MiniMax-M3-AWQ-INT4`  
**服务端口**：`30001`  
**容器名**：`MiniMax-M3-AWQ-INT4-vLLM`

---

## 方案对比

| | 推荐：本地 patch | 备用：构建时 git clone |
|--|--|--|
| **Dockerfile** | `Dockerfile.minimax-m3-patch` | `Dockerfile.minimax-m3` |
| **构建耗时** | ~1 min | ~10 min |
| **构建时网络** | 零依赖 | 需 GitHub 代理 |
| **可离线构建** | 是 | 否 |
| **可重现性** | patch 文件版本控制，完全固定 | 依赖分支 HEAD |
| **镜像名** | `minimax-m3-awq` | `minimax-m3-awq-gitclone` |
| **Make 目标** | `make build` / `make up` | `make build-a` / `make up-a` |

> **推荐使用本地 patch 方案。** 仅在 patch 需更新时才需要网络（`make patch`）。

---

## 前置条件

1. 已安装 Docker、NVIDIA Container Toolkit，`docker compose` 可用。
2. 宿主机已挂载模型目录：`/media/llm/cyankiwi/MiniMax-M3-AWQ-INT4`。
3. 8× H100（与 `docker-compose.yml` 中 `tensor-parallel-size` / GPU 列表一致）。
4. 内网需能拉取基础镜像 `model.vnet.com/sjhl/vllm-openai:minimax-m3`。

```bash
cd /media/source/model_deploy/LLM/minimax/minimax-M3-AWQ
make help
```

---

## 推荐：本地 patch 方案（零网络，~1 min）

### 第一步：生成 patch 文件（仅需一次）

patch 文件生成后提交到仓库，后续构建无需重复执行。

```bash
# 默认走代理 http://172.31.0.55:20171
make patch

# 直连 GitHub（无代理）
make patch HTTP_PROXY= HTTPS_PROXY=
```

### 第二步：拉取基础镜像

```bash
make pull-base
```

### 第三步：构建镜像

```bash
make build
```

### 构建并直接启动

```bash
make up
```

---

## 备用：构建时 git clone（需 GitHub 代理，~10 min）

```bash
make build-a
# 或构建并启动
make up-a
```

---

## 运维命令

| 操作 | 命令 |
|------|------|
| 停止并移除容器 | `make down` |
| 重启当前容器 | `make restart` |
| 跟踪日志 | `make logs` |
| 查看运行状态 | `make ps` |
| 健康检查 | `curl -f http://127.0.0.1:30001/health` |

---

## 可调参数（Make 变量）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HTTP_PROXY` | `http://172.31.0.55:20171` | git 代理（`make patch` / `make build-a`）；置空禁用 |
| `HTTPS_PROXY` | 同 `HTTP_PROXY` | 同上 |
| `BASE_IMAGE_A` | `model.vnet.com/sjhl/vllm-openai:minimax-m3` | 基础镜像 |
| `PATCH_COMMIT` | `8f1350ebf25f188a77022c70b575731f0df6a61a` | toncao 分支 commit（用于 `make patch`） |
| `UPSTREAM_COMMIT` | `a7fdfeef72323eb3db6f0620e4ea200290d0ca5a` | upstream 基底 commit |

---

## 运行参数要点

`docker-compose.yml` 中关键配置（**请勿随意修改**）：

- `--block-size 128`：MSA 稀疏注意力硬性要求，不可改为 `16`。
- `--tensor-parallel-size 8`：8 卡张量并行；AWQ INT4 权重约 240 GB，单卡约 30 GB。
- `--max-model-len 131072`：可按显存与业务调低。
- `--tool-call-parser minimax_m3` / `--reasoning-parser minimax_m3`：工具调用与推理格式。

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `Makefile` | 构建、启动、停止等统一入口 |
| `docker-compose.yml` | vLLM 服务编排 |
| `Dockerfile.minimax-m3-patch` | **推荐**：COPY 本地 patch，零网络依赖 |
| `Dockerfile.minimax-m3` | 备用：构建时 git clone（需 GitHub 代理） |
| `minimax-m3-awq.patch` | 预生成的补丁文件（由 `make patch` 生成，提交到仓库） |
