# DeepSeek-V4-Flash-0731 双节点 IB（vLLM）

vLLM 镜像 `vllm/vllm-openai:v0.25.0`，权重 `DeepSeek-V4-Flash-0731`，两台 8×H20，**DP=2 + TP=8 + EP**，NCCL 走 InfiniBand。

启动参数对齐官方 recipe（H200 / FP8 0731 / TEP / tool+reasoning）。镜像用 **0.25.0**（Hopper 上 0.26/0.27 会乱码）。  
https://recipes.vllm.ai/deepseek-ai/DeepSeek-V4-Flash

编排对齐 [`minimax-M3-AWQ-IB`](../../minimax/minimax-M3-AWQ-IB)。本目录只负责双节点编排。

**权重路径**：`/media/llm/deepseek-ai/DeepSeek-V4-Flash-0731`  
**对外模型名**：`WanWu/Deepseek-Auto`（`--served-model-name`）  
**镜像**：`vllm/vllm-openai:v0.25.0`  
**对外**：nginx `:30001` → vLLM `:30003`  
**rendezvous**：`172.31.0.43:29501`

---

## 拓扑

| 角色 | 机器 | compose | 职责 |
|------|------|---------|------|
| master (rank 0) | **172.31.0.43（本机）** | `node-43/docker-compose.yml` | nginx `:30001` + vLLM API `:30003` + rendezvous `:29501` |
| worker (rank 1, `--headless`) | 172.31.0.44 | `node-44/docker-compose.yml` | 纯计算，不对外提供 HTTP |

**必须在 master `172.31.0.43` 上执行** `make restart`。不要与 `minimax-M3-IB` / `minimax-M3-AWQ-IB` / `deepseek-v4-flash-IB` 同时跑（抢 GPU / IB / 端口）。

两端都需要：同一镜像、同一权重目录、IB 卡（`mlx5_0,mlx5_3,mlx5_4,mlx5_7`）。

---

## 启动

```bash
# 1) IB 连通性
#    跨节点检测请在 44 上跑（脚本默认 LOCAL=44 / PEER=43）：
#    ssh 172.31.0.44
#    cd /media/source/model_deploy/Physical_setup/ib_test/local && bash run.sh check-all
#    仅查本机 43 链路：
cd /media/source/model_deploy/Physical_setup/ib_test/peer && bash run.sh check

# 2) 两端准备镜像
#    docker pull vllm/vllm-openai:v0.25.0
# 3) 在本机 43 上启动双节点
cd /media/source/model_deploy/LLM/DeepSeek/deepseek-v4-flash-IB-vllm
make check
make restart
make logs
curl -f http://127.0.0.1:30003/health
curl -f http://127.0.0.1:30001/health
```

`cluster.env` 已填好 master=43 / worker=44。改 IP 后执行 `make config-check`。

worker 是 `--headless`，44 没有 HTTP，用 `make status` 和 `ssh 172.31.0.44 docker ps` 看 worker。

---

## 运维

| 操作 | 命令 |
|------|------|
| 重启双节点 | `make restart` |
| 停止双节点 | `make stop` |
| 环境预检 | `make check` |
| 跟踪本机日志 | `make logs` |
| 双节点状态 | `make status` |
| 健康检查 | `curl -f http://127.0.0.1:30001/health` |

也可 `./run.sh <命令>`。

---

## 运行参数（官方 recipe）

官方默认是**单机 8 卡 TEP**（`--tensor-parallel-size 8`）。双节点不能改成 TP=16：Flash 权重 `o_groups=8`，attention TP > 8 会切出空分片，加载时 DeepGEMM `wq.size(0) // g` 除零。

双节点按官方 8 卡命令再加 `--data-parallel-size 2` / `--nnodes 2` / `--node-rank` / `--master-addr` / `--master-port` / `--headless` / `--distributed-executor-backend mp`。

```
vllm serve deepseek-ai/DeepSeek-V4-Flash-0731 \
  --trust-remote-code \
  --kv-cache-dtype fp8 \
  --block-size 256 \
  --enable-expert-parallel \
  --tensor-parallel-size 8 \
  --data-parallel-size 2 \
  --tokenizer-mode deepseek_v4 \
  --tool-call-parser deepseek_v4 \
  --enable-auto-tool-choice \
  --reasoning-parser deepseek_v4 \
  --reasoning-config '{"reasoning_parser":"deepseek_v4","reasoning_start_str":"","reasoning_end_str":""}'
```

官方 Advanced：

| 参数 | 值 | 说明 |
|------|----|------|
| `--max-num-batched-tokens` | `8192` | recipe 默认 batch budget |
| `--no-enable-flashinfer-autotune` | on | 跳过启动 autotune |
| `--enable-ep-weight-filter` | on | 本 EP rank 不加载无关专家，加快加载 |
| `--no-enable-prefix-caching` | on | V1 默认开 prefix cache；关掉对应 SGLang `--disable-radix-cache`，减轻长上下文提前 EOS |
| `--max-model-len` | `393216`（384K） | 硬限制窗口；超长请求会被拒。Think Max 需要 ≥384K |

镜像选 **0.25.0**（不要 0.26 / 0.27）。升级前按 [`UPGRADE.md`](UPGRADE.md) 核对 PR / 实测，不要只看 changelog。

| Tag | Hopper 0731 | 说明 |
|-----|-------------|------|
| **v0.25.0** | 输出正确 | 官方 recipe / H200 示例；[#51326](https://github.com/vllm-project/vllm/issues/51326) A/B 通过 |
| v0.26.0 | 乱码 / H20 FlashMLA 崩 | [#51326](https://github.com/vllm-project/vllm/issues/51326) [#50660](https://github.com/vllm-project/vllm/issues/50660) |
| v0.27.1 | 乱码复发；DSpark 加载失败 | [#51326](https://github.com/vllm-project/vllm/issues/51326) [#51916](https://github.com/vllm-project/vllm/issues/51916) |

不开 DSpark：双节点 IB 先求稳。0.25.0 上 DSpark 可用，稳定后再加 `--speculative-config`。

0731 无 Jinja chat template，必须 `--tokenizer-mode deepseek_v4`。客户端 reasoning 走 `chat_template_kwargs.reasoning_effort`（`low` / `high` / `max`）。

---

## 客户端默认参数（sitecustomize 补丁）

不改官方镜像。镜像是 Debian，真正加载的是 `/usr/lib/python3.12/sitecustomize.py`（空文件），`dist-packages/sitecustomize.py` **不会跑**。补丁同时挂到 stdlib sitecustomize 和 `vllm_long_ctx.pth`（`import long_ctx_defaults`）。启动日志应有 `[vllm.long_ctx_defaults] enabled`。客户端**显式传的字段优先**。

| 客户端未传 | 自动补 | 范围 |
|------------|--------|------|
| `temperature` | `0` | 全部请求（否则落到 HF `generation_config` 的 1.0） |
| `top_p` | `1.0` | 全部请求 |
| `thinking` / `enable_thinking` | `false` | 未传且未设 `reasoning_effort` |
| `min_tokens` | `32` | **仅** prompt ≥ 32K、客户端未设（字段默认 0）、且未开 `ignore_eos`；不超过该请求已解析的 `max_tokens`。客户端传了非零 `min_tokens`（哪怕比 32 小）一律保留 |

不补 `max_tokens`：512 会截断思考 / 长回答；不传则按引擎窗口剩余长度，靠 EOS 收尾。需要上限由客户端自己写。

环境变量（compose 已写）：`VLLM_LONG_CTX_DEFAULTS=0` 关闭；`VLLM_LONG_CTX_MIN_TOKENS_THRESHOLD` / `VLLM_LONG_CTX_MIN_TOKENS` / `VLLM_DEFAULT_TEMPERATURE` 可改。启动日志有 `installed chat defaults`；长文命中时有 `long-ctx auto min_tokens=...`。

短问答不受 `min_tokens` 影响，仍可正常 EOS。

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `Makefile` / `run.sh` | 双节点编排入口 |
| `cluster.env` | master/worker IP、端口、镜像 |
| `node-43/docker-compose.yml` | **master**：nginx + vLLM rank 0 |
| `node-44/docker-compose.yml` | **worker**：vLLM rank 1（`--headless`） |
| `nginx.conf` / `conf.d/default.conf` | nginx（`network_mode: host`）`:30001` → `127.0.0.1:30003` |
| `UPGRADE.md` | 换镜像时的 issue/PR 核对与实测清单 |
| `vllm-patches/` | sitecustomize：默认 T=0 / 长文 `min_tokens` |
| `lib/` | 预检、hosts、ufw、master/worker SSH |
