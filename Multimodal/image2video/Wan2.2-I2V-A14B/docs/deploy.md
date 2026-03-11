# Wan2.2-I2V-A14B 部署文档

## Docker Compose 配置说明

### 基础配置

```yaml
services:
  wan22-i2v-a14b:
    image: model.vnet.com/sjhl/vllm-omni:v0.16.0
    container_name: vllm-wan22-i2v-a14b
    runtime: nvidia
```

- **镜像**: `model.vnet.com/sjhl/vllm-omni:v0.16.0`
- **容器名称**: `vllm-wan22-i2v-a14b`
- **运行时**: nvidia (GPU 支持)

### 环境变量

```yaml
environment:
  - NVIDIA_VISIBLE_DEVICES=0,1,2,3
  - NVIDIA_DRIVER_CAPABILITIES=compute,utility
  - NVIDIA_DISABLE_REQUIRE=1
  - LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:/usr/local/nvidia/lib64:/usr/local/cuda/lib64
```

- `NVIDIA_VISIBLE_DEVICES=0,1,2,3`: 指定容器内可见的 GPU 设备（逻辑设备 ID）
- `NVIDIA_DRIVER_CAPABILITIES=compute,utility`: 启用计算和工具功能
- `NVIDIA_DISABLE_REQUIRE=1`: 跳过驱动版本白名单检查（宿主机驱动 590.44 超出镜像声明的兼容范围）
- `LD_LIBRARY_PATH`: 修复 CUDA 驱动兼容性问题（Error 803），优先加载宿主机真实驱动库

**CUDA 驱动兼容性说明**：
- 宿主机驱动版本 590.44 高于镜像内置的 compat 库版本（575.57）
- 通过 `LD_LIBRARY_PATH` 优先加载真实驱动库，避免版本不匹配错误

### 卷挂载

```yaml
volumes:
  - /media/llm:/media/llm
  - ./cache:/root/.cache/huggingface
```

- `/media/llm:/media/llm`: 模型文件目录挂载
- `./cache:/root/.cache/huggingface`: HuggingFace 缓存目录

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
command:
  - --model
  - /media/llm/Wan-AI/Wan2.2-I2V-A14B-Diffusers
  - --port
  - "8091"
  - --omni
  - --host
  - "0.0.0.0"
  - --tensor-parallel-size
  - "4"
  - --served-model-name
  - Wan2.2-I2V-A14B
  - --gpu-memory-utilization
  - "0.9"
  - --trust-remote-code
  - --enforce-eager
  - --boundary-ratio
  - "0.875"
  - --flow-shift
  - "12.0"
  - --enable-cache-dit-summary
```

#### 参数说明

| 参数 | 值 | 说明 |
|------|-----|------|
| `--model` | `/media/llm/Wan-AI/Wan2.2-I2V-A14B-Diffusers` | 模型文件路径 |
| `--omni` | - | 启用 vLLM Omni 多模态功能 |
| `--port` | `8091` | 容器内服务端口 |
| `--host` | `0.0.0.0` | 监听所有网络接口 |
| `--tensor-parallel-size` | `4` | 张量并行大小，使用 4 张 GPU |
| `--served-model-name` | `Wan2.2-I2V-A14B` | API 服务中的模型名称 |
| `--gpu-memory-utilization` | `0.9` | GPU 内存使用率（90%） |
| `--trust-remote-code` | - | 信任远程代码执行 |
| `--enforce-eager` | - | 强制使用 eager 模式（兼容性） |
| `--boundary-ratio` | `0.875` | DiT 模型低/高层分割比例，控制计算分配 |
| `--flow-shift` | `12.0` | 调度器流量调整参数，影响生成质量 |
| `--enable-cache-dit-summary` | - | 启用 Cache-DiT 优化，提升推理速度 |

### GPU 资源配置

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          capabilities: [gpu]
          device_ids: ["4", "5", "6", "7"]
```

- 使用物理 GPU 设备 ID: `4, 5, 6, 7`
- 注意：`NVIDIA_VISIBLE_DEVICES` 中的 `0,1,2,3` 是容器内的逻辑设备 ID，对应物理设备 `4,5,6,7`

### 健康检查

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8091/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

- 每 30 秒检查一次服务健康状态
- 启动后允许 60 秒的初始化时间

## 部署步骤

### 1. 准备工作

确保已安装：
- Docker
- Docker Compose
- NVIDIA Docker Runtime
- NVIDIA GPU 驱动（推荐 590+）

### 2. 启动服务

```bash
cd /media/source/model_deploy/Multimodal/image2video/Wan2.2-I2V-A14B
docker-compose -f docker-compose.yml up -d
```

### 3. 查看日志

```bash
# 查看容器日志
docker logs -f vllm-wan22-i2v-a14b

# 或使用 docker-compose
docker-compose -f docker-compose.yml logs -f
```

### 4. 检查服务状态

```bash
# 查看容器状态
docker ps | grep vllm-wan22-i2v-a14b

# 或使用 docker-compose
docker-compose -f docker-compose.yml ps

# 健康检查
curl http://localhost:9141/health

# 查看模型信息
curl http://localhost:9141/v1/models
```

### 5. 停止服务

```bash
docker-compose -f docker-compose.yml down
```

## 性能优化建议

### Cache-DiT 优化

已启用 `--enable-cache-dit-summary`，可显著提升推理速度。

### GPU 内存管理

当前配置 `--gpu-memory-utilization=0.9` 已优化，如需调整：

```yaml
- --gpu-memory-utilization
- "0.85"  # 降低到 85% 以预留更多显存
```

### 多 GPU 并行

当前使用 4 张 GPU (`--tensor-parallel-size=4`)，如需调整：

```yaml
- --tensor-parallel-size
- "2"  # 使用 2 张 GPU
```

同时需要修改 `device_ids` 和 `NVIDIA_VISIBLE_DEVICES`。

### 并发处理

如需调整并发请求数，可添加：

```yaml
- --max-num-seqs
- "4"  # 最大并发序列数
```

## 故障排查

### CUDA 驱动兼容性错误 (Error 803)

**错误信息**：
```
RuntimeError: Unexpected error from cudaGetDeviceCount(). Error 803: system has unsupported display driver / cuda driver combination
```

**解决方案**：
1. 确保环境变量中包含 `LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:/usr/local/nvidia/lib64:/usr/local/cuda/lib64`
2. 确保 `NVIDIA_DISABLE_REQUIRE=1` 已设置
3. 检查宿主机驱动版本：`nvidia-smi`
4. 重启容器：`docker-compose restart`

### GPU 不可用

检查 NVIDIA Docker Runtime：
```bash
docker run --rm --gpus all nvidia/cuda:12.9.0-base-ubuntu22.04 nvidia-smi
```

检查容器内 GPU 可见性：
```bash
docker exec vllm-wan22-i2v-a14b nvidia-smi
```

### 端口冲突

修改 `docker-compose.yml` 中的端口映射：
```yaml
ports:
  - "新端口:8091"
```

### 内存不足

1. 减少 `--gpu-memory-utilization` 值（如 `0.85`）
2. 减少 `--tensor-parallel-size`（使用更少的 GPU）
3. 减少 `--max-num-seqs`（如果已设置）

### 模型路径错误

确保模型路径正确：
```bash
ls -la /media/llm/Wan-AI/Wan2.2-I2V-A14B-Diffusers
```

注意路径中的 `Diffusers` 是复数形式。

### 容器启动失败

查看详细日志：
```bash
docker logs vllm-wan22-i2v-a14b 2>&1 | tail -100
```

检查容器状态：
```bash
docker inspect vllm-wan22-i2v-a14b
```

## API 使用示例

### 基本调用

参考官方示例：https://github.com/vllm-project/vllm-omni/tree/main/examples/online_serving/image_to_video

```bash
curl -X POST http://localhost:9141/v1/videos \
  -H "Accept: application/json" \
  -F "prompt=A bear playing with yarn, smooth motion" \
  -F "negative_prompt=low quality, blurry, static" \
  -F "input_reference=@/path/to/image.png" \
  -F "width=832" \
  -F "height=480" \
  -F "num_frames=33" \
  -F "fps=16" \
  -F "boundary_ratio=0.875" \
  -F "flow_shift=12.0" \
  -F "seed=42"
```

## 参考资源

- [vLLM-Omni 官方文档](https://github.com/vllm-project/vllm-omni)
- [Image-to-Video 示例](https://github.com/vllm-project/vllm-omni/tree/main/examples/online_serving/image_to_video)
- [Wan2.2 模型文档](https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B-Diffusers)
