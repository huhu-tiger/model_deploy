# DeepSeek-V4-Flash-0731 双节点 IB（SGLang）

SGLang `v0.5.17`，权重 `DeepSeek-V4-Flash-0731`（`expert_dtype=fp4` → `--moe-runner-backend marlin`），两台 8×H20，**TP=16**，NCCL 走 InfiniBand。

| 项 | 值 |
|----|----|
| 权重 | `/media/llm/deepseek-ai/DeepSeek-V4-Flash-0731`（`max_position_embeddings=1048576`，`dspark_block_size=5`） |
| 镜像 | `model.vnet.com/sjhl/sglang:v0.5.17` |
| 对外 | nginx `:30001` → SGLang `:30003` |
| rendezvous | `--dist-init-addr 172.31.0.43:20000`（DP handshake 实际听 `:20013`） |

官方 cookbook（[DeepSeek-V4](https://docs.sglang.io/cookbook/autoregressive/DeepSeek/DeepSeek-V4)）：H100 + Flash Official + FP4 走 **marlin**（不是 `flashinfer_mxfp4`），KV 用 **fp8_e4m3**，`--swa-full-tokens-ratio 0.1`，保留 hybrid SWA。双节点长上下文对齐官方 **high-throughput** 格子：**不开 DSPARK**（只加速 decode）。

---

## 拓扑

| 角色 | 机器 | compose | 职责 |
|------|------|---------|------|
| master (rank 0) | **172.31.0.43（本机）** | `node-43/docker-compose.yml` | nginx `:30001` + SGLang API `:30003` + DP handshake `:20013` |
| worker (rank 1) | 172.31.0.44 | `node-44/docker-compose.yml` | 纯计算；仍监听 `:30003`（SGLang 惯例），不对外提供服务 |

**必须在 master `172.31.0.43` 上执行** `make restart`。不要与 `minimax-M3-IB` / `minimax-M3-AWQ-IB` 同时跑（抢 GPU / IB / `:30001`）。

两端都需要：同一镜像、同一权重目录、IB 卡（`mlx5_0,mlx5_3,mlx5_4,mlx5_7`）。`mlx5_5/6` Down 正常。

---

## 启动

```bash
# 1) IB 连通性
#    脚本默认 LOCAL=44 / PEER=43，跨节点检测请在 44 上跑：
#    ssh 172.31.0.44
#    cd /media/source/model_deploy/Physical_setup/ib_test/local && bash run.sh check-all
#    仅查本机 43 链路：
cd /media/source/model_deploy/Physical_setup/ib_test/peer && bash run.sh check

# 2) 两端 docker pull model.vnet.com/sjhl/sglang:v0.5.17

# 3) 在本机 43 上启动双节点
cd /media/source/model_deploy/LLM/DeepSeek/deepseek-v4-flash-IB
make check
make restart
make logs
curl -f http://127.0.0.1:30003/health
curl -f http://127.0.0.1:30001/health
```

`cluster.env` 已填好 master=43 / worker=44。改 IP 后执行 `make config-check`。

启动顺序：预检 → 停 worker → 停 master → scp `node-44` compose + `cluster.env` + `sglang-patches` 到 44 → 起 master → 等 DP handshake `:20013`（`--dist-init-addr` 的 20000+13；`--enable-dp-attention` 不会 LISTEN 20000）→ 起 worker。

SGLang 补丁与单机 `deepseek-v4-flash-0731` 相同：`sglang-patches` 指向该目录。含 [PR #34600](https://github.com/sgl-project/sglang/pull/34600)（streaming tool-call / reasoning parser）和 [PR #31700](https://github.com/sgl-project/sglang/pull/31700)/[#32609](https://github.com/sgl-project/sglang/pull/32609)（DP attention gather，v0.5.17 未合入；不加则双节点输出乱码）。worker 同步时拷到 `/tmp/deepseek-v4-flash-IB/sglang-patches`。

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

## 启动参数（两端必须一致，仅 rank / hostname / nginx 不同）

对齐官方 H100 Flash Official FP4 + 本集群已验证能启动的项。KV 回 **fp8_e4m3**（官方路径；bf16 未跑通且更吃显存），SWA 比回 **0.1**（NVIDIA 格子；0.15 是 AMD）。双节点仍是 `tp=16 + nnodes=2 + dp=2 + enable-dp-attention`。不开 DSPARK / prefill-cp / `--disable-hybrid-swa-memory`。

| 参数 | 值 | 说明 |
|------|----|------|
| `--tp` / `--nnodes` | `16` / `2` | 两台各 8 卡 |
| `--dp-size` / `--enable-dp-attention` | `2` / on | **必须**。权重 `o_groups=8`，attention TP 不能超过 8；纯 TP=16 会 `n_local_groups=0` |
| `--node-rank` | `0`（43）/ `1`（44） | |
| `--dist-init-addr` | `${MASTER_IP}:20000` | rendezvous |
| `--dist-timeout` | `3600` | 跨节点加载超时 |
| `--context-length` | `393216` | 384K（比 512K 更稳；官方不写此项，模型上限 1M） |
| `--mem-fraction-static` | `0.85` | 官方常见 0.90；H20 上 0.90 会在 384K prefill 的 DSA indexer 再要 ~4.5GB 后 OOM |
| `--kv-cache-dtype` | `fp8_e4m3` | **官方路径**。不写也会被 hook 设成这个；不要写 `bfloat16` |
| `--page-size` | `256` | dsv4 后端会强制 256 |
| `--moe-runner-backend` | `marlin` | Hopper + Flash Official FP4（官方 H100 格子） |
| `--attention-backend` | `dsv4` | 官方 / 默认 |
| `--swa-full-tokens-ratio` | `0.1` | 官方 NVIDIA Flash Official；必须走 hybrid SWA，不要加 `--disable-hybrid-swa-memory` |
| `--chunked-prefill-size` | `32768` | DP attention 会 `/dp_size` → 有效 **16384**；64K 从 8 段变成 4 段 |
| `--max-prefill-tokens` | `65536` | ≈2× 有效 chunk |
| `--prefill-max-requests` | `2` | 同时 prefill 数 |
| `--disable-overlap-schedule` | on | 跨节点稳定性（单机 H100 无此项） |
| `--cuda-graph-max-bs-decode` | `32` | 需 ≥ `max-running-requests`；旧名 `--cuda-graph-max-bs` 已弃用 |
| `--max-running-requests` | `32` | 与 H100 单机一致 |
| `--max-queued-requests` | `64` | |
| `--schedule-conservativeness` | `0.5` | |
| `--watchdog-timeout` | `900` | 秒 |
| `--skip-server-warmup` | on | 跳过启动末尾 dummy `/generate`，ready 更快；首个真实请求略慢 |
| `--disable-flashinfer-autotune` | on | 跳过启动时按 shape 调 FlashInfer |
| `--disable-radix-cache` | on | 关 prefix cache |
| `--preferred-sampling-params` | `temperature=0.1,top_p=1.0` | **不会**在客户端省略 `temperature` 时生效。OpenAI 路径会先用模型 `generation_config.json`（本权重是 `1.0`）填进 `sampling_params`，再盖掉 preferred。要 0.1 必须请求里显式传 |
| `--tool-call-parser` / `--reasoning-parser` | `deepseekv4` / `deepseek-v4` | |
| `--host` / `--port` | `0.0.0.0` / `30003` | worker 也绑此端口，不对外 |

不开 `--speculative-algorithm DSPARK`（长上下文不需要；稳定后若要抬 decode 再加，并同时加 `--enable-dp-lm-head`）。

环境变量：

| 变量 | 值 | 说明 |
|------|----|------|
| `SGLANG_JIT_DEEPGEMM_FAST_WARMUP` | `1` | DeepGEMM JIT 快速预热 |
| `SGLANG_JIT_DEEPGEMM_PRECOMPILE` | `0` | 跳过全量预编译，按需 JIT（缓存命中后重启几乎不编） |
| `SGLANG_SHARED_EXPERT_TP1` | `1` | 共享专家走 TP=1 |
| `SGLANG_DP_SHARED_EXPERT_LOCAL` | `1` | 共享专家在 DP gather 前用本 rank token 计算，少做一部分重复 MLP |
| `SGLANG_INVARIANT_CHECK` | `1` | WARN：检测 NaN/Inf 只打日志不崩溃 |
| `SGLANG_SANITIZE_NAN_LOGITS` | `1` | 采样前把 NaN logits 洗成有限值 |
| `SGLANG_DSV4_COMPRESS_STATE_DTYPE` | `float32` | C4/C128 indexer 状态保持 fp32（默认更稳，不要改 bf16） |
| `SGLANG_LONG_CTX_IGNORE_EOS_TOKENS` | `32768` | prompt ≥ 此 token 数时自动 `ignore_eos`（症状补丁）。`0` 关闭 |
| `NCCL_IB_HCA` | `mlx5_0,mlx5_3,mlx5_4,mlx5_7` | |
| `NCCL_IB_GID_INDEX` | `0` | 原生 IB；RoCE 才用 3 |
| `NCCL_SOCKET_IFNAME` / `GLOO_SOCKET_IFNAME` | `bond0` | |

容器：`privileged` + `/dev/infiniband` + `shm_size=32g`。

OOM：先看日志 `available_gpu_mem`，建议留 5–8GB；不够再降 `--max-running-requests` / `--cuda-graph-max-bs-decode`。启动日志必须是 `kv_cache_dtype='fp8_e4m3'`。

不要加 `--disable-hybrid-swa-memory`：DSV4 仍会建 SWA 池，关 hybrid 后 `swa_size=None`，启动 `TypeError`（exit -3，不是 OOM）。也不要写 `--kv-cache-dtype bfloat16`（官方不用，H20 显存更紧）。

---

## 已知问题：长上下文提前 EOS

现象：计数任务先正确输出数字 `1`（token **19**），下一步采到 `eos_token_id=1`（`<｜end▁of▁sentence｜>`），`finish_reason=stop`，`matched_stop=1`，内容只有 `"1"`。不是解析器，也不是 id 配错。短请求正常；`SGLANG_INVARIANT_CHECK` 无 NaN。`ignore_eos` 后仍能继续往下数，说明任务没丢，只是 decode 第二步 EOS logit 被抬高。

对照（双节点 TP16 DP2、dsv4、hybrid SWA、mem=0.85；压测 `enable_thinking=false`）：

| 配置 | T=0 256K | T=0.1 256K | T=1.0 |
|------|----------|------------|-------|
| fp8 KV + 512K + radix | 1 过 / 2 停 | 会停 | — |
| fp8 KV + `--disable-radix-cache` | 3/3 过、384K 2/2 过 | 3/3 过 | 256K **2/2 停** |
| 窗口 384K + 去掉 `--kv-cache-dtype`（**仍被 hook 设成 fp8**）+ 无 radix | 2/2 过（换行只领先 0.13～0.63 nats） | **1 过 / 1 停**（失败条 EOS 领先 3.75 nats） | 256K 2/2 过（一条用了双空格换行，且 EOS 已领先普通换行）；360K **1 过 / 1 停** |
| **当前**：官方 fp8 + 384K + swa=0.1 + hybrid SWA + 无 radix | 1/1 过（换行领先 EOS 0.37 nats） | **1 过 / 2 停**（过的那条换行与 EOS 打平 -0.693；失败条 EOS 领先 ~7.5 nats；flush 后再测仍停） | 1/1 过（换行领先 0.38 nats，仍很近） |

结论：只删 `--kv-cache-dtype` **不会**改成 bf16。降到 384K 也没有消掉提前 EOS。同类上游：[sglang#33397](https://github.com/sgl-project/sglang/issues/33397)、[#33360](https://github.com/sgl-project/sglang/issues/33360)。

**本地症状补丁**（`sglang-patches/long_ctx_ignore_eos.py`，经 sitecustomize 注入 tokenizer）：prompt ≥ `SGLANG_LONG_CTX_IGNORE_EOS_TOKENS`（默认 32K）时自动 `ignore_eos=true`。短请求不受影响。长请求靠 `max_tokens` 收尾（客户端不传则 SGLang 默认 128）。日志会出现 `long-ctx auto ignore_eos: prompt_tokens=...`。设 `SGLANG_LONG_CTX_IGNORE_EOS_TOKENS=0` 可关。这不是根治，根治要等上游 dsv4 + DP attention 修复。

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `Makefile` / `run.sh` | 双节点编排入口 |
| `cluster.env` | master/worker IP、dist 端口、镜像 |
| `node-43/docker-compose.yml` | **master**：nginx + SGLang rank 0 |
| `node-44/docker-compose.yml` | **worker**：SGLang rank 1 |
| `nginx.conf` / `conf.d/default.conf` | host 网络 listen `30001` → `127.0.0.1:30003` |
| `sglang-patches/` | symlink → `../deepseek-v4-flash-0731/sglang-patches`（PR #34600 + #31700/#32609 + 长上下文 ignore_eos） |
| `lib/` | 预检、hosts、ufw、master/worker SSH |
