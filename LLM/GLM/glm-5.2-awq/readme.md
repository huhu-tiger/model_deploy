# GLM-5.2-AWQ-INT4 vLLM 部署

模型权重与说明：

- ModelScope: https://modelscope.cn/models/cyankiwi/GLM-5.2-AWQ-INT4

**权重路径（宿主机）**：`/media/llm/cyankiwi/GLM-5.2-AWQ-INT4`  
**对外端口**：`30002`  
**容器名**：`GLM-5.2-AWQ-INT4-vLLM`  
**API 模型名**：`WanWu/GLM-Auto`  
**镜像**：`model.vnet.com/sjhl/vllm-openai:glm52`

---

## 前置条件

1. 已安装 Docker、NVIDIA Container Toolkit，`docker compose` 可用。
2. 宿主机已挂载模型目录：`/media/llm/cyankiwi/GLM-5.2-AWQ-INT4`。
3. 8× GPU（与 `docker-compose.yml` 中 `tensor-parallel-size` / GPU 列表一致）。
4. 内网需能拉取镜像 `model.vnet.com/sjhl/vllm-openai:glm52`。
5. 直连模式与 nginx 代理模式**不可同时启动**（同容器名、同对外端口 30002）。

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

### 直连模式（vLLM 监听 :30002）

```bash
make up
```

### nginx 代理模式（宿主机:30002 → nginx:80 → 内网 vLLM:30003，记录请求日志）

若当前已是直连模式，先停再切：

```bash
make down
make nginx-up
```

---

## 运维命令

### 直连模式

| 操作 | 命令 |
|------|------|
| 停止并移除容器 | `make down` |
| 重启当前容器 | `make restart` |
| 跟踪日志 | `make logs` |
| 查看运行状态 | `make ps` |
| 健康检查 | `curl -f http://127.0.0.1:30002/health` |

### nginx 代理模式

| 操作 | 命令 |
|------|------|
| 停止 nginx + vLLM | `make nginx-down` |
| 仅停止 nginx（vLLM 继续运行） | `make nginx-stop` |
| 仅重建 nginx（不重启 vLLM） | `make nginx-restart` |
| 跟踪日志 | `make nginx-logs` |
| 查看运行状态 | `make nginx-ps` |
| 健康检查 | `curl -f http://127.0.0.1:30002/health` |

请求日志目录：`./logs/`

- `access.log` / `error.log`：nginx 访问与错误
- `llm_proxy.log`：`/v1/chat/completions` 请求日志（≤10KB 内联请求体，>10KB 落盘 `logs/bodies/`）

---

## 运行参数

`docker-compose.yml` / `docker-compose-nginx.yml` 中关键配置：

- `--served-model-name WanWu/GLM-Auto`：API 调用时使用的模型名。
- `--tensor-parallel-size 8`：8 卡张量并行。
- `--max-model-len 131072`：上下文长度上限。
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
| `docker-compose.yml` | vLLM 直连编排（:30002） |
| `docker-compose-nginx.yml` | nginx 映射 30002:80，vLLM 仅 compose 内网 :30003 |
| `nginx.conf` | OpenResty 主配置（请求体日志、滚动） |
| `conf.d/default.conf` | 反代 `/llm/`、`/v1/`、`/health` |
| `logs/` | nginx 访问 / 错误 / 请求体日志 |
