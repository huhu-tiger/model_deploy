# GLM-5.2-AWQ-INT4 vLLM 部署

模型权重与说明：

- ModelScope: https://modelscope.cn/models/cyankiwi/GLM-5.2-AWQ-INT4

**权重路径（宿主机）**：`/media/llm/cyankiwi/GLM-5.2-AWQ-INT4`  
**服务端口**：`30001`  
**容器名**：`GLM-5.2-AWQ-INT4-vLLM`  
**镜像**：`model.vnet.com/sjhl/vllm-openai:glm52`

---

## 前置条件

1. 已安装 Docker、NVIDIA Container Toolkit，`docker compose` 可用。
2. 宿主机已挂载模型目录：`/media/llm/cyankiwi/GLM-5.2-AWQ-INT4`。
3. 8× GPU（与 `docker-compose.yml` 中 `tensor-parallel-size` / GPU 列表一致）。
4. 内网需能拉取镜像 `model.vnet.com/sjhl/vllm-openai:glm52`。

```bash
cd /media/source/model_deploy/LLM/GLM/glm-5.2-awq
make help
```

---

## 启动

### 拉取镜像

```bash
make pull
# 等同于: docker pull model.vnet.com/sjhl/vllm-openai:glm52
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
| 健康检查 | `curl -f http://127.0.0.1:30001/health` |

---

## 运行参数

`docker-compose.yml` 中关键配置：

- `--served-model-name glm-5.2-awq`：API 调用时使用的模型名。
- `--tensor-parallel-size 8`：8 卡张量并行。
- `--max-model-len 116288`：受 KV cache 可用显存限制（10.04 GiB），低于模型原生 1M 上下文。
- `--gpu-memory-utilization 0.90`：GPU 显存利用率上限。
- `--tool-call-parser glm47`：GLM-5.2 工具调用解析器。
- `--reasoning-parser glm45`：启用思考模式（Thinking）解析。
- `--enable-auto-tool-choice`：允许模型自动决策是否调用工具。

### 思考模式说明

GLM-5.2 默认开启 Thinking（Think Max）。通过 `chat_template_kwargs` 控制：

| 模式 | 请求方式 |
|------|---------|
| Think Max（默认） | 不传 `reasoning_effort` |
| Think High | `"chat_template_kwargs": {"reasoning_effort": "high"}` |
| 关闭思考 | `"chat_template_kwargs": {"enable_thinking": false}` |

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `Makefile` | 拉取镜像、启动、停止等统一入口 |
| `docker-compose.yml` | vLLM 服务编排 |
