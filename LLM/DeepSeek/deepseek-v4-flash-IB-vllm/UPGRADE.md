# vLLM 镜像升级核对（DeepSeek-V4-Flash-0731 / H20 双节点）

升级 `vllm/vllm-openai` 之前按本文核对。目标：新镜像在 **8×H20 × 2 + IB、DP=2 TP=8 EP、不开 DSpark** 上，输出正确、长上下文不 silent 损坏、启动不崩。

当前生产钉死：**`v0.25.0`**。不要只看 changelog 里的 DSv4 性能 PR 就升 0.26 / 0.27。

官方 recipe：https://recipes.vllm.ai/deepseek-ai/DeepSeek-V4-Flash  
本目录部署说明：[`readme.md`](readme.md)

---

## 1. 当前基线

| 项 | 值 |
|----|----|
| 权重 | `/media/llm/deepseek-ai/DeepSeek-V4-Flash-0731` |
| 对外名 | `WanWu/Deepseek-Auto` |
| 硬件 | 两台 8×H20，IB `mlx5_0,mlx5_3,mlx5_4,mlx5_7` |
| 并行 | DP=2 + TP=8 + EP（不能 TP=16，`o_groups=8`） |
| 投机 | **不开 DSpark** |
| prefix cache | `--no-enable-prefix-caching` |
| 窗口 | `--max-model-len 393216`（384K） |
| 镜像 | `vllm/vllm-openai:v0.25.0` |

钉 0.25.0 的原因：Hopper 上 0.26 输出乱码、0.27.1 乱码复发（[#51326](https://github.com/vllm-project/vllm/issues/51326)）；0.26 + DSpark 在 H20 上 FlashMLA TMA assert（[#50660](https://github.com/vllm-project/vllm/issues/50660)）。

---

## 2. 升级前：在 GitHub 核实这些条目

把候选 tag / nightly SHA 填进「是否包含」列。未合入或未验证的项，**不要升生产**。

### 2.1 必须通过（正确性）

| 条目 | 现象 | 状态（填日期 / SHA） | 我们是否踩过 |
|------|------|----------------------|--------------|
| [#51326](https://github.com/vllm-project/vllm/issues/51326) | H100/H20 TP8+EP，0.26 输出乱码，0.25 正常；0.26.1rc 一度好，**0.27.1 又坏**，怀疑 DeepGEMM | | 是，故钉 0.25 |
| [#50660](https://github.com/vllm-project/vllm/issues/50660) [#49922](https://github.com/vllm-project/vllm/issues/49922) | 0.26 + DSpark，H20 `phase1.cuh` TMA assert。修：[#49302](https://github.com/vllm-project/vllm/pull/49302) | | 未开 DSpark，升 0.26 后若要开投机必须先核 |
| [#51318](https://github.com/vllm-project/vllm/pull/51318) 2026-08-16 | 撤回 C128A 自适应 packing。CUDA Graph 回放时 metadata 行步长和 capture 不一致 → **高并发 / 长上下文 silent 坏输出**、thinking/tool 标签乱 | | 0.25 无这条路径；升 0.26+ 必须带 |
| [#52401](https://github.com/vllm-project/vllm/pull/52401) 2026-08-16 | [#51430](https://github.com/vllm-project/vllm/pull/51430) 收窄 eager CUDA Graph 区，MRV1 输出损坏；#51768 禁 MRV1+PIECEWISE。#52401 按 runner 选区域：MRV1 宽区、MRV2 窄区 | | 0.25 无；升 nightly 才有 |

### 2.2 建议通过（协议 / 附属功能）

| 条目 | 现象 | 我们是否用得到 |
|------|------|----------------|
| [#51296](https://github.com/vllm-project/vllm/pull/51296) | tokenizer 默认 thinking、parser 默认 content → reasoning / tool-call 漏进 `content` | 是（`--reasoning-parser` / `--tool-call-parser`） |
| [#51727](https://github.com/vllm-project/vllm/pull/51727) | tokenizer `__len__` 多算 vocab，guided decoding bitmask 4040 vs 4041 | 仅 structured output / JSON schema |
| [#51538](https://github.com/vllm-project/vllm/pull/51538) | DSV4 sparse MLA 在 decode / MTP / DSpark 跑通 | 未开 DSpark，收益有限 |

### 2.3 可忽略（非本硬件）

ROCm / gfx942 AITER indexer 损坏、SM120/SM121 DeepGEMM 加载失败、MRV2 在 ROCm 上回退。H20 CUDA 不用跟。

### 2.4 版本速查（截至 2026-08-16）

| Tag | Hopper 0731 输出 | H20 + DSpark | 备注 |
|-----|------------------|--------------|------|
| **v0.25.0** | 正确 | 可用（未作为生产） | 当前生产 |
| v0.26.0 | 乱码 / FlashMLA 崩 | 崩 | 不要 |
| v0.26.1rc（部分 SHA） | 一度正常 | 视是否含 #49302 | 以实测为准 |
| v0.27.1 | 乱码复发 | DSpark 加载失败 | 不要 |
| main @ #52401+#51318 之后 | **未在本集群实测** | 未知 | 升之前必须走第 3 节 |

查某个 tag 是否含 PR：

```bash
# 本地有 vllm 仓库时
git merge-base --is-ancestor <pr-merge-sha> <tag> && echo yes || echo no
```

或打开 PR 页看 `merged` 日期是否早于该 tag 的 release 日期。

---

## 3. 升级后实测（本集群）

两端 pull 同一新镜像，改 `cluster.env` 的 `DOCKER_IMAGE`，**不要先改生产 compose 默认值**。在 43 上 `make restart`，等 `/health` 200。

### 3.1 冒烟（必须全过）

```bash
# 模型名
curl -sS http://127.0.0.1:30001/v1/models | python3 -c \
  "import sys,json; d=json.load(sys.stdin)['data'][0]; print(d['id'], d.get('max_model_len'))"
# 期望: WanWu/Deepseek-Auto  且 max_model_len >= 393216

# 短问答（关 thinking）
curl -sS -m 60 http://127.0.0.1:30001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "WanWu/Deepseek-Auto",
    "messages": [{"role":"user","content":"法国的首都是哪里？只答城市名。"}],
    "max_tokens": 32,
    "temperature": 0,
    "chat_template_kwargs": {"enable_thinking": false}
  }'
```

**失败信号（立刻回退 0.25.0）**

- 短问答乱码、中英夹杂无意义符号（#51326 典型）
- HTTP 200 但语义完全不对
- EngineCore / worker CUDA assert（`phase1.cuh` / TMA）
- `/v1/models` 不是 `WanWu/Deepseek-Auto`

### 3.2 长上下文（建议）

```bash
cd /media/source/model_deploy/model_test/context_bench
API_BASE=http://127.0.0.1:30001 \
MODEL_NAME=WanWu/Deepseek-Auto \
CONTEXT_LEVELS=32,16,8 \
PARALLEL=1 NUMBER_MULT=1 NUMBER_MAX=2 \
./test_context_sweep.sh
```

再视情况补 128K / 256K / 384K。对照目录：`outputs/<stamp>/context_sweep/report.html`。

**失败信号**

- 长文 TTFT 后无输出或一直 hang
- 回答与 prompt 无关、提前 EOS 明显加重
- 并发 >1 时 thinking / tool 标签错乱（#51318）

### 3.3 协议（用了 tool / reasoning 再测）

- 不传 `thinking` 时：不应把 `<think>` / DSML 整段漏进 `content`（#51296）
- 需要 JSON schema 时：EngineCore 不应再报 bitmask 尺寸不匹配（#51727）

### 3.4 对照记录

每次试升级填一行，方便下次判断：

| 日期 | 镜像 tag / SHA | 短问答 | 32K | 128K+ | 备注 | 结论 |
|------|----------------|--------|-----|-------|------|------|
| 2026-08 | `v0.25.0` | 通过 | 通过 | 压测中 | 生产基线 | **采用** |
| | | | | | | |

---

## 4. 决策

- **短问答乱码** → 立刻回退 0.25.0，不要用该 tag。
- **短问答过、长上下文 / 并发损坏** → 确认是否缺 #51318 / #52401；缺则继续钉 0.25.0。
- **上述全过，且 #51326 在该 tag 上关闭或有明确「Hopper 0731 已修」评论** → 可以改 `cluster.env` + compose 默认镜像，并更新下面「当前基线」和 `readme.md` 版本表。

回退：

```bash
# cluster.env
DOCKER_IMAGE=vllm/vllm-openai:v0.25.0
make restart
```

---

## 5. 文档维护

新发现 DSv4 + Hopper/H20 的 issue / PR，补进第 2 节表格，并写清：

- 是否只在 0.26+ / DSpark / ROCm 上出现
- 合入 SHA 与日期
- 本集群是否已实测

核对日期写在第 2.4 节标题旁，避免后人把过期结论当现状。
