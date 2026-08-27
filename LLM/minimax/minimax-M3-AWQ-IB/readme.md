# MiniMax-M3-AWQ-INT4 双节点 IB（vLLM）

vLLM 镜像 `minimax-m3-awq`，权重 `MiniMax-M3-AWQ-INT4`，两台 8×H20，**TP=16**，NCCL 走 InfiniBand。

镜像构建见 [`../minimax-M3-AWQ`](../minimax-M3-AWQ)（`make build`）。本目录只负责双节点编排。

**权重路径**：`/media/llm/cyankiwi/MiniMax-M3-AWQ-INT4`  
**镜像**：`model.vnet.com/sjhl/vllm-openai:minimax-m3-awq`  
**对外**：nginx `:30001` → vLLM `:30003`  
**rendezvous**：`172.31.0.43:29501`

---

## 拓扑

| 角色 | 机器 | compose | 职责 |
|------|------|---------|------|
| master (rank 0) | **172.31.0.43（本机）** | `node-43/docker-compose.yml` | nginx `:30001` + vLLM API `:30003` + rendezvous `:29501` |
| worker (rank 1, `--headless`) | 172.31.0.44 | `node-44/docker-compose.yml` | 纯计算，不对外提供 HTTP |

**必须在 master `172.31.0.43` 上执行** `make restart`。不要与 `minimax-M3-IB` / `deepseek-v4-flash-IB` 同时跑（抢 GPU / IB / 端口）。

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
# 3) 在本机 43 上启动双节点
cd /media/source/model_deploy/LLM/minimax/minimax-M3-AWQ-IB
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

## 运行参数要点

- `--block-size 128`：MSA 稀疏注意力硬性要求，不可改为 `16`。
- `--tensor-parallel-size 16`：双节点各 8 卡。不要加 `--enable-expert-parallel`（M3-IB 实测纯 TP 更好）。
- `--max-model-len 524288`（512K；模型上限 1M）。本镜像 MSA 核只支持 **bf16 KV**，不要加 `--kv-cache-dtype fp8`。
- `--max-num-seqs 16` / `--max-num-batched-tokens 8192`：长文并发与 prefill 分块；OOM 先降 seqs，再降 batched-tokens。
- `--distributed-executor-backend mp`：多机不用 Ray。
- `--no-async-scheduling`：跨节点 TP=16 必须关异步调度。默认开启时，首次请求 Triton JIT 会让 rank 不同步，NCCL allreduce 报 `remote process exited or there was a network error`。
- 本镜像不认 `VLLM_SKIP_WARMUP`（启动会打 Unknown env），不要设。
- worker 必须加 `--headless`，API 只在 master。
- `--tool-call-parser minimax_m3` / `--reasoning-parser minimax_m3`。

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `Makefile` / `run.sh` | 双节点编排入口 |
| `cluster.env` | master/worker IP、端口、镜像 |
| `node-43/docker-compose.yml` | **master**：nginx + vLLM rank 0 |
| `node-44/docker-compose.yml` | **worker**：vLLM rank 1（`--headless`） |
| `nginx.conf` / `conf.d/default.conf` | nginx（`network_mode: host`）`:30001` → `127.0.0.1:30003` |
| `minimax_m3_reasoning_parser.py` | 运行时挂载；`make sync` 会拷到 worker |
| `lib/` | 预检、hosts、ufw、master/worker SSH |
