# Wan2.2-T2V-A14B 部署文档

## Docker Compose 配置说明

### 基础配置

```yaml
services:
  wan22-t2v-a14b:
    image: model.vnet.com/sjhl/vllm-omni:v0.16.0
    container_name: wan22-t2v-a14b
    runtime: nvidia
```

- **镜像**: `model.vnet.com/sjhl/vllm-omni:v0.16.0`
- **容器名称**: `wan22-t2v-a14b`
- **运行时**: nvidia (GPU 支持)

### 环境变量

```yaml
environment:
  - NVIDIA_VISIBLE_DEVICES=all
  - NVIDIA_DRIVER_CAPABILITIES=compute,utility
```

- `NVIDIA_VISIBLE_DEVICES=all`: 使用所有可用 GPU
- `NVIDIA_DRIVER_CAPABILITIES=compute,utility`: 启用计算和工具功能

### 卷挂载

```yaml
volumes:
  - /media/llm/Wan-AI/Wan2.2-T2V-A14B-Diffusers:/model
  - ./cache:/root/.cache
```

- `/media/llm/Wan-AI/Wan2.2-T2V-A14B-Diffusers`: 模型文件目录
- `./cache`: 缓存目录，用于存储运行时缓存

### 端口映射

```yaml
ports:
  - "9141:8091"
```

- 宿主机端口: `9141`
- 容器内端口: `8091`
- 访问地址: `http://localhost:9141`

### 启动参数

```yaml
command: >
  --model /model
  --omni
  --port 8091
  --host 0.0.0.0
  --boundary-ratio 0.875
  --flow-shift 5.0
  --enable-cache-dit-summary
```

#### 参数说明

| 参数 | 值 | 说明 |
|------|-----|------|
| `--model` | `/model` | 模型文件路径 |
| `--omni` | - | 启用 vLLM Omni 多模态功能 |
| `--port` | `8091` | 容器内服务端口 |
| `--host` | `0.0.0.0` | 监听所有网络接口 |
| `--boundary-ratio` | `0.875` | DiT 模型低/高层分割比例，控制计算分配 |
| `--flow-shift` | `5.0` | 调度器流量调整参数，影响生成质量 |
| `--enable-cache-dit-summary` | - | 启用 Cache-DiT 优化，提升推理速度 |

## 部署步骤

### 1. 准备工作

确保已安装：
- Docker
- Docker Compose
- NVIDIA Docker Runtime
- NVIDIA GPU 驱动

### 2. 启动服务

```bash
cd /media/source/model_deploy/Multimodal/text2video/Wan2.2-T2V-A14B
docker-compose up -d
```

### 3. 查看日志

```bash
docker-compose logs -f wan22-t2v-a14b
```

### 4. 检查服务状态

```bash
# 查看容器状态
docker-compose ps

# 健康检查
curl http://localhost:9141/health
```

### 5. 停止服务

```bash
docker-compose down
```

## 性能优化建议

### Cache-DiT 优化

已启用 `--enable-cache-dit-summary`，可显著提升推理速度。

### GPU 内存管理

如需调整 GPU 内存使用，可添加以下参数：

```yaml
command: >
  --model /model
  --omni
  --gpu-memory-utilization 0.9
  --max-model-len 8192
```

### 并发处理

调整并发请求数：

```yaml
command: >
  --model /model
  --omni
  --max-num-seqs 4
```

## 故障排查

### GPU 不可用

检查 NVIDIA Docker Runtime：
```bash
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

### 端口冲突

修改 `docker-compose.yml` 中的端口映射：
```yaml
ports:
  - "新端口:8091"
```

### 内存不足

减少 `--gpu-memory-utilization` 或 `--max-num-seqs` 参数值。
