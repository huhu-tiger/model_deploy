# Docker 镜像同步工具

从公网或远程仓库拉取 Docker 镜像，打标签后推送到内网仓库 `model.vnet.com/sjhl`，并记录已成功推送的镜像。

## 目录结构

```
tools/docker-mirror/
├── Makefile            # 命令封装
├── pull_and_push.sh    # 主脚本
├── pushed_images.txt   # 推送成功记录（自动追加）
└── README.md
```

## 前置条件

- 已安装 Docker，且 `docker` 命令可用
- 当前环境可访问远程镜像源（如 Docker Hub）
- 已登录内网仓库 `model.vnet.com`（`docker login model.vnet.com`）

## 镜像命名规则

脚本会将源镜像映射到内网仓库，规则为：**取镜像路径最后一段作为镜像名，保留原 tag**。

| 源镜像 | 目标镜像 |
|--------|----------|
| `vllm/vllm-openai:v0.22.1` | `model.vnet.com/sjhl/vllm-openai:v0.22.1` |
| `nvidia/cuda:12.0.0-base` | `model.vnet.com/sjhl/cuda:12.0.0-base` |
| `nginx` | `model.vnet.com/sjhl/nginx:latest` |

等价于手动执行：

```bash
docker pull vllm/vllm-openai:v0.22.1
docker tag vllm/vllm-openai:v0.22.1 model.vnet.com/sjhl/vllm-openai:v0.22.1
docker push model.vnet.com/sjhl/vllm-openai:v0.22.1
docker rmi -f model.vnet.com/sjhl/vllm-openai:v0.22.1 vllm/vllm-openai:v0.22.1
```

推送成功后会强制删除本地的源镜像与目标镜像标签（`-f`），释放磁盘空间；若镜像被运行中容器占用则仍会删除失败。

## 用法

### Makefile（推荐）

```bash
cd tools/docker-mirror

# 查看帮助
make help

# 同步单个镜像
make push IMAGE=vllm/vllm-openai:v0.22.1

# 同步多个镜像（逗号分隔）
make push IMAGE=vllm/vllm-omni:v0.22.0,vllm/vllm-openai:v0.22.1

# 同步多个镜像（空格分隔）
make push IMAGES="vllm/vllm-openai:v0.22.1 nvidia/cuda:12.0.0-base"

# 查看已推送记录
make list

# 登录内网仓库
make login
```

### 直接调用脚本

```bash
# 进入脚本目录
cd tools/docker-mirror

# 同步单个镜像
./pull_and_push.sh vllm/vllm-openai:v0.22.1

# 同步多个镜像（逗号分隔）
./pull_and_push.sh vllm/vllm-omni:v0.22.0,vllm/vllm-openai:v0.22.1

# 同步多个镜像（空格分隔）
./pull_and_push.sh \
  vllm/vllm-openai:v0.22.1 \
  nvidia/cuda:12.0.0-base \
  sglang/sglang:v0.5.12
```

也可从项目根目录直接调用：

```bash
./tools/docker-mirror/pull_and_push.sh vllm/vllm-openai:v0.22.1
```

## 推送记录

每个镜像推送成功后，目标地址会追加写入 `pushed_images.txt`，每行一条。
再次同步时会先检查该文件，**按目标镜像地址**判断是否跳过（不检查批次中的前一个镜像），避免重复拉取和推送：

> 例如 `vllm/vllm-openai:v0.22.1` 映射为 `model.vnet.com/sjhl/vllm-openai:v0.22.1`，仅当该目标地址已在记录中时才跳过。

```
model.vnet.com/sjhl/vllm-openai:v0.22.1
model.vnet.com/sjhl/cuda:12.0.0-base
```

## 错误处理

- 支持空格或逗号分隔多个镜像
- 推送前检查 `pushed_images.txt`，仅当**当前镜像的目标地址**已存在时跳过（与批次中其他镜像无关）
- 若记录文件中有误写入（如推送失败但曾写入记录），需手动删除对应行后重新同步
- 某一步（pull/tag/push）失败时立即停止当前镜像的后续步骤，不会写入推送记录
- 批量同步时，某个镜像失败不会中断后续镜像的处理
- 若存在失败项，脚本最终以非零状态码退出，并输出 `部分镜像处理失败`
- 推送成功但删除本地镜像失败时仅输出警告，不影响推送结果
- 暂不支持带 digest 的镜像引用（如 `image@sha256:...`）

## 查看帮助

```bash
./pull_and_push.sh
```

不带参数运行时会打印用法说明。
