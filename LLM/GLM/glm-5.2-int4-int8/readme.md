# GLM-5.2-Int4-Int8Mix vLLM 部署

模型权重与说明：

- ModelScope: https://modelscope.cn/models/tclf90/GLM-5.2-Int4-Int8Mix

混合精度量化（关键层 INT8 + MoE 专家 INT4），权重大小约 **405.52 GB**，显存需求与 [cyankiwi GLM-5.2-AWQ-INT4](../glm-5.2-awq/readme.md) 接近，精度理论上略好于纯 INT4。

**权重路径（宿主机）**：`/media/llm/tclf90/GLM-5.2-Int4-Int8Mix`  
**服务端口**：`30002`  
**容器名**：`GLM-5.2-Int4-Int8Mix-vLLM`  
**API 模型名**：`GLM-5.2`  
**镜像**：`model.vnet.com/sjhl/vllm-openai:glm52`

---

## 硬件要求

| GPU | 单卡 | 8 卡总显存 | 权重 TP=8 单卡 | 结论 |
|-----|------|------------|----------------|------|
| H100 | 80 GB | 640 GB | ~50.7 GB | ✅ 可行 |
| H20 | 96 GB | 768 GB | ~50.7 GB | ✅ 更宽裕（KV cache 余量更大） |

> 纯 INT8（~586 GB）在 H100 上单卡装不下；Int4-Int8Mix（~405 GB）与本目录方案匹配。

---

## 前置条件

1. 已安装 Docker、NVIDIA Container Toolkit，`docker compose` 可用。
2. 宿主机已下载并挂载模型：`/media/llm/tclf90/GLM-5.2-Int4-Int8Mix`。
3. 8× GPU（与 `tensor-parallel-size` 一致）。
4. 内网需能拉取镜像 `model.vnet.com/sjhl/vllm-openai:glm52`。
5. 与 `glm-5.2-awq`（端口 30001）**不可同时占用同一组 GPU**。

### 下载权重

```bash
modelscope download --model tclf90/GLM-5.2-Int4-Int8Mix \
  --local_dir /media/llm/tclf90/GLM-5.2-Int4-Int8Mix
```

```bash
cd /media/source/model_deploy/LLM/GLM/glm-5.2-int4-int8
make help
```

---

## 启动

### 拉取镜像

```bash
make pull
```

### 启动服务

```bash
make up
```

---

## 运维命令

| 操作 | 命令 |
|------|------|
| 停止并移除容器 | `make down` |
| 重启当前容器 | `make restart` |
| 跟踪日志 | `make logs` |
| 查看运行状态 | `make ps` |
| 健康检查 | `curl -f http://127.0.0.1:30002/health` |

---

## 运行参数

`docker-compose.yml` 对齐 [ModelScope 模型页](https://modelscope.cn/models/tclf90/GLM-5.2-Int4-Int8Mix) 官方 vLLM 启动命令，关键配置：

- `--served-model-name GLM-5.2`：API 调用时使用的模型名。
- `--quantization compressed-tensors`：混合 INT4+INT8 量化格式。
- `--dtype bfloat16`：激活 dtype。
- `--tensor-parallel-size 8` + `--enable-expert-parallel`：8 卡 MoE 并行（必须）。
- `--max-model-len 65536`：64K 上下文（H100 8×80GB 稳妥值）。
- `--kv-cache-dtype fp8`：KV cache FP8，节省显存。
- `--max-num-seqs 32`：并发序列上限。
- `--speculative-config.method mtp` + `--num_speculative_tokens 1`：MTP 投机解码。
- `VLLM_USE_MODELSCOPE=true`：启用 ModelScope 集成。
- 服务端口使用 **30002**（官方示例为 8000，此处与 awq 服务区分）。

### 思考模式说明

GLM-5.2 默认开启 Thinking（Think Max）。通过 `chat_template_kwargs` 控制：

| 模式 | 请求方式 |
|------|---------|
| Think Max（默认） | 不传 `reasoning_effort` |
| Think High | `"chat_template_kwargs": {"reasoning_effort": "high"}` |
| 关闭思考 | `"chat_template_kwargs": {"enable_thinking": false}` |

### OOM 时调参

1. 将 `--max-model-len auto` 改为固定值（如 `65536`）
2. 降低 `--max-num-seqs`（如 16）
3. 降低 `--gpu-memory-utilization`（如 0.85）
4. H100 上 KV 余量较 H20 小，长上下文场景优先用 H20

---

## 与 AWQ INT4 对比

| | Int4-Int8Mix（本目录） | AWQ INT4（glm-5.2-awq） |
|--|--|--|
| 来源 | [tclf90/GLM-5.2-Int4-Int8Mix](https://modelscope.cn/models/tclf90/GLM-5.2-Int4-Int8Mix) | cyankiwi/GLM-5.2-AWQ-INT4 |
| 权重大小 | ~405 GB | ~400 GB |
| 精度 | 混合 INT4+INT8，略好 | AWQ INT4 |
| 端口 | 30002 | 30001 |
| 特殊参数 | `compressed-tensors` + `--enable-expert-parallel` + MTP | AWQ compressed-tensors |

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `Makefile` | 拉取镜像、启动、停止等统一入口 |
| `docker-compose.yml` | vLLM 服务编排 |
