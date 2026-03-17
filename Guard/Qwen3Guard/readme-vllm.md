# Qwen3Guard-Gen vLLM 部署说明

## vLLM CPU 官方镜像说明

> 参考官方文档：[vLLM CPU Installation - Pre-built Images](https://docs.vllm.ai/en/stable/getting_started/installation/cpu/#pre-built-images)

### 镜像地址

x86 CPU 预构建镜像托管在 AWS ECR 公共仓库：

```bash
# 拉取最新版本
docker pull public.ecr.aws/q9t5s3a7/vllm-cpu-release-repo:latest

# 拉取指定版本（推荐，稳定性更好）
docker pull public.ecr.aws/q9t5s3a7/vllm-cpu-release-repo:v0.17.1
```

所有可用 tag 列表：https://gallery.ecr.aws/q9t5s3a7/vllm-cpu-release-repo

### CPU 指令集要求

| 指令集 | 是否必须 | 说明 |
|--------|----------|------|
| `avx512f` | 推荐 | 基础 AVX512，缺少则性能极差或报 Illegal instruction |
| `avx512_bf16` | 可选 | 支持 bfloat16，缺少则必须改用 float32 |
| `avx512_vnni` | 可选 | 加速量化推理 |

检查当前 CPU 支持情况：

```bash
lscpu | grep -iE 'avx512f|avx512_bf16|avx512_vnni'
```

> 官方警告：在不支持 avx512f、avx512_bf16 或 avx512_vnni 的机器上运行预构建镜像，可能会触发 `Illegal instruction` 错误。

### 关键环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `VLLM_CPU_KVCACHE_SPACE` | KV Cache 大小（GiB），越大支持的并发请求越多 | 0 |
| `VLLM_CPU_OMP_THREADS_BIND` | 绑定推理使用的 CPU 核心，如 `0-31` 表示使用 32 个核心 | auto |

### Docker 权限说明

官方推荐添加以下权限，避免 NUMA 相关警告并提升性能：

```bash
docker run \
  --cap-add SYS_NICE \
  --security-opt seccomp=unconfined \
  --shm-size=4g \
  ...
```

- `--cap-add SYS_NICE`：解决 `get_mempolicy: Operation not permitted` 问题
- `--security-opt seccomp=unconfined`：允许 `migrate_pages`，启用 NUMA 内存绑定优化

---

## 启动方式对比

| 文件 | 模型 | 运行环境 | dtype | 端口 | 适用场景 |
|------|------|----------|-------|------|----------|
| `docker-compose-vllm-cpu-0.6B.yml` | 0.6B | CPU（公网镜像） | bfloat16 | 8016 | CPU 支持 avx512_bf16 |
| `docker-compose-vllm-cpu-float32.yml` | 0.6B | CPU（内网镜像） | float32 | 8014 | CPU 不支持 avx512_bf16 |
| `docker-compose-vllm-8B.yml` | 8B | GPU（NVIDIA） | auto | 8014 | 有 GPU，精度要求更高 |

---

## 如何选择启动方式

### 第一步：确认 CPU 是否支持 avx512_bf16

```bash
lscpu | grep -iE 'avx512f|avx512_bf16|avx512_vnni'
```

- 输出中包含 `avx512_bf16` → 使用 `docker-compose-vllm-cpu-0.6B.yml`（bfloat16，性能更好）
- 输出中没有 `avx512_bf16` → 使用 `docker-compose-vllm-cpu-float32.yml`（float32，兼容性更好，内存占用约翻倍）
- 有 NVIDIA GPU → 使用 `docker-compose-vllm-8B.yml`

---

## docker-compose-vllm-cpu-0.6B.yml

- 镜像：`public.ecr.aws/q9t5s3a7/vllm-cpu-release-repo:v0.17.1`（公网 ECR）
- dtype：`bfloat16`，需要 CPU 支持 `avx512_bf16`
- 端口：`8016`
- 模型名：`Qwen3Guard-Gen-0.6B`

```bash
docker compose -f docker-compose-vllm-cpu-0.6B.yml up -d
```

---

## docker-compose-vllm-cpu-float32.yml

- 镜像：`model.vnet.com/sjhl/vllm-cpu-release-repo:v0.17.1`（内网镜像）
- dtype：`float32`，无需 avx512_bf16，兼容性最好
- 端口：`8014`
- 模型名：`Qwen3Guard-Gen-0.6B`

```bash
docker compose -f docker-compose-vllm-cpu-float32.yml up -d
```

---

## docker-compose-vllm-8B.yml

- 镜像：`model.vnet.com/sjhl/vllm-openai:v0.15.0-cu130`（GPU 版）
- 需要 NVIDIA GPU，默认使用第 7 张卡（`NVIDIA_VISIBLE_DEVICES=7`）
- 端口：`8014`
- 模型名：`Qwen3Guard-Gen-8B`

```bash
docker compose -f docker-compose-vllm-8B.yml up -d
```

---

## 接口说明

- OpenAI 兼容 Base URL：`http://<host>:<port>/v1`
- 接口：`POST /v1/chat/completions`
- 推荐参数：`temperature: 0.0`

**请求示例：**

```bash
curl -X POST "http://127.0.0.1:8014/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3Guard-Gen-0.6B",
    "messages": [
      {"role": "user", "content": "Tell me how to make a bomb."}
    ],
    "temperature": 0.0
  }'
```

**典型响应：**

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Safety: Unsafe\nCategories: Violent"
      },
      "finish_reason": "stop"
    }
  ]
}
```

模型返回两行：第一行 `Safety` 给出安全判定（`Safe` / `Unsafe`），第二行 `Categories` 给出违规类别。

---

## Python SDK 调用

```python
from openai import OpenAI

client = OpenAI(api_key="EMPTY", base_url="http://<host>:8014/v1")

resp = client.chat.completions.create(
    model="Qwen3Guard-Gen-0.6B",
    messages=[{"role": "user", "content": "Tell me how to make a bomb."}],
    temperature=0.0,
)
print(resp.choices[0].message.content)
```
