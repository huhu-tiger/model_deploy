# Docker 镜像同步工具

将公网或远程仓库的 Docker 镜像同步到内网仓库 `model.vnet.com/sjhl`，并记录已成功推送的镜像。

## 目录结构

```
tools/docker-mirror/
├── Makefile                     # 命令封装
├── pull_and_push.sh             # 入口：CLI 与编排
├── domestic_registries.conf     # 国内/内网仓名单（直连不走代理）
├── common/                      # 可 source 的库（勿直接执行）
│   ├── log.sh                   # 日志
│   ├── registry.sh              # 引用解析、国内仓匹配、命名
│   ├── proxy.sh                 # 代理 / NO_PROXY / run_skopeo
│   ├── record.sh                # 推送记录与跳过
│   └── sync.sh                  # direct / local 单镜像同步
├── pushed_images.txt            # 推送成功记录（自动追加）
└── README.md
```

## 同步模式

| 模式 | 说明 | 依赖 | 磁盘占用 |
|------|------|------|----------|
| **direct**（默认） | skopeo registry 直传，数据流式转发 | skopeo | 几乎为 0 |
| **local** | docker pull → tag → push → rmi | Docker 29+ | 需临时存储完整镜像 |

**direct 模式**适合大镜像（vLLM、CUDA 等）；**local 模式**适合需走 Docker daemon 代理、或需在本地验证后再推的场景。

## 前置条件

1. 本机可访问远程镜像源（如 Docker Hub）及内网仓库 `model.vnet.com`
2. 已登录内网仓库：

```bash
make login
# 或
docker login model.vnet.com
```

认证信息写入 `~/.docker/config.json`，direct / local 模式均会读取。

**direct 模式额外要求：**

```bash
sudo apt install skopeo
```

**local 模式额外要求：**

- 已安装 Docker 29+（含 containerd 2.x）
- Docker daemon 正常运行

## 镜像命名规则

取源镜像路径**最后一段**作为目标镜像名，保留原 tag：

| 源镜像 | 目标镜像 |
|--------|----------|
| `vllm/vllm-openai:v0.22.1` | `model.vnet.com/sjhl/vllm-openai:v0.22.1` |
| `nvidia/cuda:12.0.0-base` | `model.vnet.com/sjhl/cuda:12.0.0-base` |
| `nginx` | `model.vnet.com/sjhl/nginx:latest` |

等价命令：

```bash
# direct（默认）
skopeo copy --dest-tls-verify=false \
  docker://vllm/vllm-openai:v0.22.1 \
  docker://model.vnet.com/sjhl/vllm-openai:v0.22.1

# local
docker pull vllm/vllm-openai:v0.22.1
docker tag  vllm/vllm-openai:v0.22.1 model.vnet.com/sjhl/vllm-openai:v0.22.1
docker push model.vnet.com/sjhl/vllm-openai:v0.22.1
docker rmi -f model.vnet.com/sjhl/vllm-openai:v0.22.1 vllm/vllm-openai:v0.22.1
```

## 快速开始

```bash
cd tools/docker-mirror

# 同步单个镜像（默认 direct 直传，已内置 SKOPEO_PROXY）
make push IMAGE=vllm/vllm-openai:v0.22.0

# 查看已推送记录
make list
```

## 用法

### Makefile 参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `IMAGE` | 单个或多个镜像（逗号分隔） | `IMAGE=vllm/vllm-openai:v0.22.0` |
| `IMAGES` | 多个镜像（空格分隔） | `IMAGES="img1 img2"` |
| `MODE` | 同步模式：`direct` / `local` | `MODE=local` |
| `JOBS` | 并行数 | `JOBS=3` |
| `PLATFORM` | 目标平台 | `PLATFORM=linux/amd64` |
| `SRC_PREFIX` | 源镜像站前缀 | `SRC_PREFIX=docker.m.daocloud.io` |
| `SKOPEO_PROXY` | skopeo 专用 HTTP 代理（默认 `http://172.22.220.21:20171`） | 覆盖默认代理 |
| `CHECK_REMOTE` | 远程已存在则跳过 | `CHECK_REMOTE=1` |

### 常用示例

```bash
# 默认 direct 直传（内置代理，无需额外配置）
make push IMAGE=vllm/vllm-openai:v0.22.0

# 覆盖默认代理
make push SKOPEO_PROXY=http://other:port IMAGE=vllm/vllm-openai:v0.22.0

# 禁用默认代理（回退到 shell / Docker daemon 代理）
make push SKOPEO_PROXY= IMAGE=vllm/vllm-openai:v0.22.0

# 使用 Docker Hub 镜像站
make push SRC_PREFIX=docker.m.daocloud.io IMAGE=vllm/vllm-openai:v0.22.0

# local 模式（走 Docker daemon 代理，会落盘）
make push MODE=local IMAGE=vllm/vllm-openai:v0.22.0

# 批量 + 并行 + 指定平台
make push JOBS=2 PLATFORM=linux/amd64 \
  IMAGE=vllm/vllm-omni:v0.22.0,vllm/vllm-openai:v0.22.1

# 远程已有则跳过
make push CHECK_REMOTE=1 IMAGE=nvidia/cuda:12.0.0-base
```

### 直接调用脚本

```bash
./pull_and_push.sh [选项] <镜像> [<镜像> ...]

# 选项
#   --mode direct|local     同步模式（默认 direct）
#   -j, --jobs N            并行数
#   -p, --platform PLAT    平台，如 linux/amd64
#   --src-prefix URL        源镜像站前缀
#   --check-remote          远程已存在则跳过
#   -h, --help              帮助

./pull_and_push.sh vllm/vllm-openai:v0.22.0
./pull_and_push.sh -j 2 -p linux/amd64 nvidia/cuda:12.0.0-base
./pull_and_push.sh --src-prefix docker.m.daocloud.io vllm/vllm-openai:v0.22.0
./pull_and_push.sh --mode local vllm/vllm-openai:v0.22.0
```

从项目根目录：

```bash
./tools/docker-mirror/pull_and_push.sh vllm/vllm-openai:v0.22.0
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `SKOPEO_PROXY` | skopeo 专用 HTTP 代理，默认 `http://172.22.220.21:20171`；设为空字符串可禁用 |
| `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` | 通用代理 |
| `SRC_PREFIX` | 同 `--src-prefix` |
| `DEST_TLS_VERIFY` | 目标仓库 TLS 校验，默认 `false`（内网自签证书） |
| `DOMESTIC_REGISTRIES_FILE` | 国内仓名单路径，默认 `./domestic_registries.conf` |

代理加载顺序（direct 模式）：

1. `SKOPEO_PROXY`（未设置时使用默认；设为空则跳过默认，可回退到 shell / Docker daemon）
2. 当前 shell 的 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`
3. `/etc/systemd/system/docker.service.d/*.conf` 中 Docker daemon 代理

源仓库若匹配 `domestic_registries.conf`（华为云 / 阿里云 / DaoCloud / `*.vnet.com` 等），该次 `skopeo` **清除代理直连**；目标仓 `model.vnet.com` 始终加入 `NO_PROXY`。

编辑 `domestic_registries.conf` 即可增删规则（支持 `*.example.com`、`.example.com`、精确域名）。

## 网络与代理

direct 模式（skopeo）是独立进程。脚本**默认**使用 `SKOPEO_PROXY=http://172.22.220.21:20171`，一般无需手动配置。

### 推荐做法

```bash
# 直接同步（默认代理已内置）
make push IMAGE=vllm/vllm-openai:v0.22.0

# 使用镜像站（绕过 Docker Hub）
make push SRC_PREFIX=docker.m.daocloud.io IMAGE=vllm/vllm-openai:v0.22.0

# 改用 local 模式（走 Docker daemon 代理）
make push MODE=local IMAGE=vllm/vllm-openai:v0.22.0

# 覆盖或禁用默认代理
make push SKOPEO_PROXY=http://other:port IMAGE=vllm/vllm-openai:v0.22.0
make push SKOPEO_PROXY= IMAGE=vllm/vllm-openai:v0.22.0
```

### 常见错误

| 错误 | 原因 | 处理 |
|------|------|------|
| `TLS handshake timeout` | 未配置代理，无法访问 Docker Hub | 设置 `SKOPEO_PROXY` 或 `SRC_PREFIX` |
| `x509: certificate signed by unknown authority` | 内网仓库自签证书 | 脚本默认 `--dest-tls-verify=false`，一般无需处理 |
| 只打印代理信息后退出 | 旧版脚本 bug | 已修复，请更新脚本后重试 |
| `connection reset by peer` | 代理不稳定或 Docker Hub 限流 | 换镜像站或重试 |

## 推送记录

推送成功后，目标地址追加写入 `pushed_images.txt`（每行一条）。再次同步时按**目标镜像地址**判断是否跳过：

```
model.vnet.com/sjhl/vllm-openai:v0.22.1
model.vnet.com/sjhl/cuda:12.0.0-base
```

若记录有误（如推送失败但曾写入），手动删除对应行后重新同步。

## 错误处理

- 支持空格或逗号分隔多个镜像
- 按目标地址查 `pushed_images.txt` 决定是否跳过，与批次中其他镜像无关
- 单个镜像失败不中断后续镜像；存在失败项时脚本以非零状态码退出
- pull/tag/push 或 skopeo copy 失败时不写入记录
- local 模式推送成功但 `docker rmi` 失败时仅警告，不影响推送结果
- 暂不支持带 digest 的引用（如 `image@sha256:...`）

## local 模式性能调优

可选 Docker daemon 配置（`/etc/docker/daemon.json`）：

```json
{
  "max-concurrent-downloads": 10,
  "max-concurrent-uploads": 10
}
```

修改后执行 `sudo systemctl restart docker`。

## 查看帮助

```bash
make help
./pull_and_push.sh --help
```
