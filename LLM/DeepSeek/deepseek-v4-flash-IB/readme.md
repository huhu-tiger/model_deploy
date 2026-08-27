# DeepSeek-V4-Flash-0731 双节点 IB（SGLang）

SGLang `v0.5.18`，权重 `DeepSeek-V4-Flash-0731`（`expert_dtype=fp4` → `--moe-runner-backend marlin`），两台 8×H20，采用 **TP=8 + PP=2**，NCCL 走 InfiniBand。目标负载为 300K 输入 + 2K 输出；冷前缀需要完整 prefill，TTFT <10 秒仅作为高命中率 Radix 公共前缀的目标。

| 项 | 值 |
|----|----|
| 权重 | `/media/llm/deepseek-ai/DeepSeek-V4-Flash-0731`（`max_position_embeddings=1048576`，`dspark_block_size=5`） |
| 镜像 | `model.vnet.com/sjhl/sglang:v0.5.18` |
| 对外 | nginx `:30001` → SGLang `:30003` |
| rendezvous | `--dist-init-addr 172.31.0.43:20000`（标准 distributed rendezvous） |

官方 cookbook（[DeepSeek-V4](https://docs.sglang.io/cookbook/autoregressive/DeepSeek/DeepSeek-V4)）：H100 + Flash Official + FP4 走 **marlin**（不是 `flashinfer_mxfp4`），KV 用 **fp8_e4m3**，`--swa-full-tokens-ratio 0.1`，保留 hybrid SWA。双节点长上下文对齐官方 **high-throughput** 格子：**不开 DSPARK**（只加速 decode）。

---

## 拓扑

| 角色 | 机器 | compose | 职责 |
|------|------|---------|------|
| PP stage 0 (rank 0) | **172.31.0.43（本机）** | `node-43/docker-compose.yml` | nginx `:30001` + SGLang API `:30003` + rendezvous `:20000` |
| PP stage 1 (rank 1) | 172.31.0.44 | `node-44/docker-compose.yml` | 纯计算，不对外提供服务 |

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

# 2) 两端 docker pull model.vnet.com/sjhl/sglang:v0.5.18

# 3) 在本机 43 上启动双节点
cd /media/source/model_deploy/LLM/DeepSeek/deepseek-v4-flash-IB
make check
make restart
make logs
curl -f http://127.0.0.1:30003/health
curl -f http://127.0.0.1:30001/health
```

`cluster.env` 已填好 master=43 / worker=44。改 IP 后执行 `make config-check`。

启动顺序：预检 → 严格停止 worker → 停 master → scp `node-44` compose + `cluster.env` 到 44 → 起 master → 等 distributed rendezvous `:20000` → 起 worker → 确认双端容器持续运行并等待 `/health`。任一步失败会返回非零并清理残留容器。

v0.5.18 已内置 DeepSeek V4 tool/reasoning parser、DP gather、fused kernel 和 multi-stream 优化。部署不再挂载本地 Python 补丁，避免旧逻辑覆盖或修改镜像行为。

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

配置采用 `tp=8 + pp=2 + nnodes=2`：每台机器完成一个流水线 stage，避免 TP16 每层都跨 IB 通信；v0.5.18 的动态 chunking 将 300K prefill 切成微批并流水执行。不开 DSPARK、DP attention、prefill CP 或 `--disable-hybrid-swa-memory`。

| 参数 | 值 | 说明 |
|------|----|------|
| `--tp` / `--pp-size` / `--nnodes` | `8` / `2` / `2` | 每节点 TP8，跨节点 PP2；43 层自动切为 21/22 层 |
| `--node-rank` | `0`（43）/ `1`（44） | |
| `--dist-init-addr` | `${MASTER_IP}:20000` | 标准 distributed rendezvous |
| `--context-length` | `327680` | 320Ki tokens，覆盖 300K 输入 + 2K 输出并留余量 |
| `--mem-fraction-static` | `0.85` | 先保守保留 DSV4 indexer 工作区；实测显存充足后再逐步升至 0.88 |
| `--kv-cache-dtype` / `--page-size` | `fp8_e4m3` / `256` | v0.5.18 DSV4 官方默认路径 |
| `--moe-runner-backend` / `--attention-backend` | `marlin` / `dsv4` | H20 + Flash Official FP4 |
| `--swa-full-tokens-ratio` | `0.1` | 保留 hybrid SWA |
| `--chunked-prefill-size` | `12288` | PP 微批初始上限，兼顾 stage 利用率与首请求调度 |
| `--enable-dynamic-chunking` | on | v0.5.18 根据拟合耗时动态调整 PP chunk |
| `--max-prefill-tokens` / `--prefill-max-requests` | `32768` / `1` | 避免并发长 prefill 抬高目标请求 TTFT |
| `--cuda-graph-max-bs-decode` / `--max-running-requests` | `8` / `8` | 面向低延迟而非大吞吐 |
| `--schedule-policy` | `lpm` | 优先最长前缀命中 |
| Radix cache | on（默认） | 复用公共 300K 前缀；这是热前缀 TTFT <10 秒的关键 |
| `--watchdog-timeout` | `900` | 冷 300K prefill 不被 watchdog 误杀 |
| `--skip-server-warmup` | on | ready 更快；正式压测前需主动预热模型与公共前缀 |
| `--tool-call-parser` / `--reasoning-parser` | `deepseekv4` / `deepseek-v4` | v0.5.18 内置 |

不开 `--speculative-algorithm DSPARK`：它主要改善 2K decode，不会缩短 300K 冷 prefill TTFT，且会占用额外显存。若后续重点转向总完成时延，可在 PP2 稳定后单独 A/B 测试。

环境变量：

| 变量 | 值 | 说明 |
|------|----|------|
| `SGLANG_JIT_DEEPGEMM_FAST_WARMUP` | `1` | DeepGEMM JIT 快速预热 |
| `SGLANG_JIT_DEEPGEMM_PRECOMPILE` | `0` | 跳过全量预编译，按需 JIT（缓存命中后重启几乎不编） |
| `SGLANG_SHARED_EXPERT_TP1` | `1` | 共享专家走 TP=1 |
| `SGLANG_DYNAMIC_CHUNKING_SMOOTH_FACTOR` | `0.75` | v0.5.18 动态 chunk 耗时拟合的平滑系数 |
| `SGLANG_INVARIANT_CHECK` | `1` | WARN：检测 NaN/Inf 只打日志不崩溃 |
| `SGLANG_SANITIZE_NAN_LOGITS` | `1` | 采样前把 NaN logits 洗成有限值 |
| `SGLANG_DSV4_COMPRESS_STATE_DTYPE` | `float32` | C4/C128 indexer 状态保持 fp32（默认更稳，不要改 bf16） |
| `NCCL_IB_HCA` | `mlx5_0,mlx5_3,mlx5_4,mlx5_7` | |
| `NCCL_IB_GID_INDEX` | `0` | 原生 IB；RoCE 才用 3 |
| `NCCL_SOCKET_IFNAME` / `GLOO_SOCKET_IFNAME` | `bond0` | |

容器当前为兼容 RDMA 使用 `privileged` + `/dev/infiniband` + `shm_size=32g`；正式上线前应实测移除 `privileged`、`SYS_PTRACE` 与 `seccomp:unconfined`。nginx 不读取或记录请求体，只记录状态码和耗时；长请求的 `proxy_read_timeout` 为 1800 秒。当前鉴权未启用，必须通过防火墙限制 `30003`，并在生产入口配置密钥鉴权。

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
| 旧 v0.5.17 配置：官方 fp8 + 384K + swa=0.1 + hybrid SWA + 无 radix | 1/1 过（换行领先 EOS 0.37 nats） | **1 过 / 2 停**（过的那条换行与 EOS 打平 -0.693；失败条 EOS 领先 ~7.5 nats；flush 后再测仍停） | 1/1 过（换行领先 0.38 nats，仍很近） |

结论：只删 `--kv-cache-dtype` **不会**改成 bf16。降到 384K 也没有消掉提前 EOS。同类上游：[sglang#33397](https://github.com/sgl-project/sglang/issues/33397)、[#33360](https://github.com/sgl-project/sglang/issues/33360)。

当前 `TP8 + PP2` 部署已移除 `sitecustomize.py` 与 `long_ctx_ignore_eos.py`，不再自动改写请求的 `ignore_eos`。如果 v0.5.18 + PP2 仍复现提前 EOS，应先保留请求、采样参数和 token 日志做回归定位，不默认恢复旧版 DP-attention 场景的症状补丁。业务确实需要忽略 EOS 时，由客户端按单个请求显式传入，并同时设置严格的 `max_tokens` 与 stop 条件。

---

## 并行方案选择

| 方案 | 最适合的场景 | 优点 | 主要代价/风险 |
|------|--------------|------|---------------|
| `TP8 + PP2`（当前） | 300K 超长上下文、并发 1～2、稳定性优先 | 节点内 TP 走 NVLink；跨节点只传 PP stage activation；可用动态 chunking 流水化长 prefill | 低并发有 pipeline bubble；逐 token decode 依次经过两级；极限吞吐不如充分调优的 DP/EP |
| `TP16 + DP Attention` | 短/中上下文、高并发、总体 token 吞吐优先 | 16 卡共同处理批次；大 batch 下可减少流水线空泡 | 每层可能跨节点 collective；强依赖 IB/NCCL；DSV4 DP attention 仍需严格做并发正确性回归 |
| `TP + EP` | 大规模 MoE、高并发、大 batch、4 节点以上扩展 | Expert 分布到不同 GPU，降低单卡权重压力；高负载时吞吐潜力高 | 每个 MoE 层都要 All-to-All；强依赖 IB、负载均衡和 DeepEP/MegaMoE；当前 FP4 Marlin 权重不是优先 EP 路径 |
| 两个独立 `TP8` | 多用户并发、模型和 KV 可在单节点容纳、可用性优先 | 两套服务近似水平扩展；无跨节点模型通信；故障隔离好 | 无法用两台机器共同降低单个 300K 冷请求 TTFT；两副本 Prefix Cache 不共享 |

当前目标是 300K 输入 + 2K 输出，建议保持 `TP8 + PP2`。冷请求耗时主要来自 43 层 MoE、C4 indexer、C4/C128 压缩及约 25 个 prefill chunk；增加 TP、EP 或 DSPARK都不能直接消除这些计算。热请求要接近 10 秒 TTFT，关键是让绝大部分公共前缀命中 Radix Cache。

## IB 现状及扩展到 8 张的判断

两台服务器实测拓扑一致：

- 8× NVIDIA H20 96GB，PCIe Gen5 ×16，GPU 间 `NV18` NVLink。
- 4× Active ConnectX-7 NDR 400Gb/s：`mlx5_0`、`mlx5_3`、`mlx5_4`、`mlx5_7`。
- NUMA 0 有 `mlx5_0`、`mlx5_3`，NUMA 1 有 `mlx5_4`、`mlx5_7`，布局均衡。
- `mlx5_5`、`mlx5_6` 是一张双口 ConnectX-6，当前 `Disabled/Down`，不能算作两张可用的 400G计算 IB。
- `mlx5_bond_0` 是 25GbE 管理/控制网络，不属于 NDR 计算 fabric。

当前每节点理论单向 IB 总带宽为：

\[
4 \times 400\ \mathrm{Gb/s} = 1600\ \mathrm{Gb/s} = 200\ \mathrm{GB/s}
\]

H20 本身不限制 HCA 数量；能否扩展到 8 张取决于服务器是否提供 8 个 PCIe Gen5 ×16/专用 mezzanine 通道、CPU PCIe lanes、PCIe switch、OSFP 接口、供电散热以及交换机 NDR400 端口。HGX H100/H200 参考平台存在“8 GPU + 8 ConnectX-7”的 1:1 rail 配置，因此技术上可行，但必须由当前服务器厂商确认机型支持。

对当前 `TP8 + PP2`，从 4×400G 扩到 8×400G 通常不会明显降低 300K 冷 TTFT：PP2 只在 stage 边界跨节点传 activation，主要瓶颈仍是 GPU 计算和 DSV4 indexer。只有实测发现 4 条 rail 已持续接近饱和、PP stage 明显等待网络时，新增 HCA 才可能改善吞吐。8 张 IB 对跨节点 TP16、DP attention 或 EP 的收益通常比对 PP2 更大。

扩卡前应先用 `nccl-tests` 的 `sendrecv_perf`、`all_reduce_perf`、`alltoall_perf` 测试 4-rail，并观察业务期间每张 HCA 的端口计数器、GPU 利用率和 PP stage idle time。若现有链路远未达到合计 200GB/s，则不建议仅为当前 PP2 采购额外 HCA。

## SGLang v0.5.18 社区优化与已知缺陷

当前镜像构建信息：

- 镜像：`model.vnet.com/sjhl/sglang:v0.5.18`
- SGLang commit：`71de97b264b04dcd514cf904003028aefe9775c8`
- 构建时间：2026-08-21

镜像已包含 DSV4 sparse prefill、C4/C128 压缩、FP8 KV、FP4 Marlin、fused norm/RoPE、multi-stream overlap、PP dynamic chunking，以及 [PR #31700](https://github.com/sgl-project/sglang/pull/31700) 的 DP-attention gather 语义修复。不要再用 v0.5.17 的 `deepseek_v4.py`、`deepseek_v4_nextn.py` 或 parser 文件覆盖镜像源码。

需要持续关注：

1. **长上下文 indexer 瞬时显存**：[Issue #35201](https://github.com/sgl-project/sglang/issues/35201) 指出 C4 indexer 的 FP32 logits workspace 随 `chunk_tokens × context` 增长，且未计入 `mem_fraction_static`。[PR #35217](https://github.com/sgl-project/sglang/pull/35217) 提供按可用显存切分 query rows 的修复，截至 2026-08-22 仍未合并，当前 v0.5.18 镜像不包含该实现。300K 压测若 OOM，优先把 `--chunked-prefill-size` 从 `12288` 降为 `8192`，必要时降到 `4096`；降低 `mem-fraction-static` 只能增加余量，不能根治随上下文增长的问题。
2. **DSPARK TP rank 分叉/死锁**：[Issue #33549](https://github.com/sgl-project/sglang/issues/33549) 在 8×H20、TP8、约 245K context 上复现长时间运行后 collective hang。[PR #33614](https://github.com/sgl-project/sglang/pull/33614) 尝试同步各 TP rank 的采样与接受状态，截至 2026-08-22 仍未合并。因此本部署保持 DSPARK 关闭。
3. **并发输出污染**：[Issue #33397](https://github.com/sgl-project/sglang/issues/33397) 报告 DSV4 + FP8 KV 在并发下输出逐渐损坏。当前 PP2 避开 DP attention 路径，但上线前仍必须执行并发 1/2/4/8 的确定性输出对照。
4. **HiCache/sparse prefill 稳定性**：[Issue #34235](https://github.com/sgl-project/sglang/issues/34235) 报告 H20 上 HiCache、DSPARK 与长上下文 sparse prefill 的 hang/NaN。当前阶段不要启用 HiCache；先验证纯 GPU Radix Cache。
5. **提前 EOS**：本部署已移除自动 `ignore_eos` 症状补丁。上线前应验证 300K+2K 请求是否正常以 EOS 或业务 stop 条件结束；若客户端显式启用 `ignore_eos`，必须同时传 `max_tokens=2048` 并设置业务 stop 条件。

建议上线顺序：先以并发 1 完成 300K 冷请求正确性和显存峰值测试；再测试同前缀第二次请求的 Radix 命中与 TTFT；之后逐级测试并发 2/4/8。保持 DSPARK 和 HiCache 关闭，直到相关社区修复合并并在 H20 环境完成回归。

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `Makefile` / `run.sh` | 双节点编排入口 |
| `cluster.env` | master/worker IP、dist 端口、模型/缓存路径、镜像 |
| `node-43/docker-compose.yml` | **master**：nginx + SGLang rank 0 |
| `node-44/docker-compose.yml` | **worker**：SGLang rank 1 |
| `nginx.conf` / `conf.d/default.conf` | host 网络 listen `30001` → `127.0.0.1:30003` |
| `lib/` | 预检、hosts、ufw、master/worker SSH |
