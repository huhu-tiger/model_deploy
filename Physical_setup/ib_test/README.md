# IB 连通性测试工具

用于验证两台服务器之间 InfiniBand 网卡的链路状态与跨节点通信是否正常。

## 环境说明

| 角色 | 主机名 | 管理网 IP |
|------|--------|-----------|
| 本机（发起方） | bjdb-h20-node-044 | 172.31.0.44 |
| 对端（接收方） | bjdb-h20-node-043 | 172.31.0.43 |

**本机 IB 卡（ConnectX-7，4X NDR，400 Gbps）：**

| 设备 | LID | 状态 |
|------|-----|------|
| mlx5_0 | 261 (0x105) | Active |
| mlx5_3 | 267 (0x10b) | Active |
| mlx5_4 | 273 (0x111) | Active |
| mlx5_7 | 279 (0x117) | Active |
| mlx5_5/6 | — | Down（ConnectX-6，未接线） |

---

## 目录结构

```
ib_test/
├── config.sh          # 公共配置（IP、设备、测试参数）
├── common.sh          # 公共函数库（预检、检测、工具函数）
├── local/             # 在本机 (172.31.0.44) 运行
│   ├── run.sh         # 入口脚本
│   ├── check.sh       # 本机 IB 链路检查
│   ├── check_all.sh   # 双端检测主脚本
│   ├── client.sh      # 跨节点 IB 通信测试（客户端）
│   └── sync_peer.sh   # 同步 peer/ 脚本到对端
└── peer/              # 在对端 (172.31.0.43) 运行
    ├── run.sh         # 入口脚本
    ├── check.sh       # 对端 IB 链路检查
    └── server.sh      # 跨节点 IB 通信测试（服务端监听）
```

---

## 前提条件

1. 本机到对端管理网可达（ping 172.31.0.43）
2. SSH 免密配置完成（`ssh root@172.31.0.43` 无需输入密码）
3. 两端均有 `sudo` 权限（脚本会自动安装缺失的 apt 包）

配置 SSH 免密示例：

```bash
ssh-keygen -t ed25519 -N ""
ssh-copy-id root@172.31.0.43
```

---

## 快速开始

所有操作均在**本机** (172.31.0.44) 执行。

### 1. 一键双端检测（推荐）

```bash
cd /media/source/model_deploy/Physical_setup/ib_test/local
bash run.sh check-all
```

自动完成以下步骤：
- 检查本机 apt 依赖（缺失则自动安装）
- 检查 SSH 连通性
- 检查对端 apt 依赖
- 同步脚本到对端 `/tmp/ib_test_peer`
- 本机 IB 链路检查（端口状态、ibstat、rdma link、ibping 自测）
- SSH 到对端执行相同链路检查

### 2. 跨节点 IB 通信测试

需要两个终端：

```bash
# 终端 1：在对端启动 IB 监听（自动同步脚本）
bash run.sh start-peer

# 终端 2：本机向对端发起测试
bash run.sh client
```

`client` 会依次测试：
- **ibping**：IB 层 ping，验证 IB 子网可达性
- **ib_write_bw**：RDMA 写带宽测试（需安装 `perftest`）

---

## 子命令说明

```bash
bash local/run.sh <命令>
```

| 命令 | 说明 | 预检模式 |
|------|------|---------|
| `check` | 仅检查本机 IB 链路 | 本机 apt + IB 模块 |
| `check-all` | 双端链路检查（推荐） | 本机 + SSH + 对端 apt |
| `sync` | 同步脚本到对端 | 本机 + SSH |
| `start-peer` | 同步并在对端启动 IB 监听 | 本机 + SSH + 对端 apt |
| `client` | 本机向对端发起通信测试 | 本机 + SSH |

对端单独运行：

```bash
bash /tmp/ib_test_peer/run.sh check    # 对端链路检查
bash /tmp/ib_test_peer/run.sh server   # 启动 IB 监听
```

---

## 环境变量

可通过环境变量覆盖配置，无需修改脚本：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `IB_DEV` | `mlx5_0` | 使用的 IB 设备 |
| `IB_PORT` | `1` | IB 端口号 |
| `IBPING_COUNT` | `10` | ibping 发包数 |
| `BW_DURATION` | `5` | ib_write_bw 测试时长（秒） |
| `PEER_LID` | 自动获取 | 手动指定对端 LID（SSH 不可用时） |
| `PEER_DEPLOY_DIR` | `/tmp/ib_test_peer` | 对端脚本部署路径 |

示例：

```bash
# 使用 mlx5_3 设备测试
IB_DEV=mlx5_3 bash run.sh check-all

# 手动指定对端 LID（不依赖 SSH 自动获取）
PEER_LID=260 bash run.sh client

# 延长带宽测试时长为 30 秒
BW_DURATION=30 bash run.sh client
```

---

## 预检机制

每个子命令运行前会自动完成对应层级的预检，确保依赖满足后再执行测试：

```
run_preflight local      →  本机 apt 包 + ib_umad 模块 + IB 设备存在性
run_preflight peer       →  以上 + SSH 连通性检查
run_preflight start-peer →  以上 + 对端 apt 包（可自动安装）
```

**apt 依赖包：**

```
infiniband-diags   提供 ibstat、ibping、ibnetdiscover 等工具
ibutils            提供 ibdiagnet 等诊断工具
rdmacm-utils       提供 rping 等 RDMA CM 测试工具
```

带宽测试额外需要（不在自动安装列表，需手动安装）：

```bash
sudo apt install -y perftest    # 提供 ib_write_bw、ib_read_bw、ib_send_bw
```

---

## 检测项说明

### 链路检查（`check` / `check-all`）

| 检测项 | 工具 | 说明 |
|--------|------|------|
| 所有 IB 端口状态 | sysfs | 列出全部设备，Down 端口标注 `*** DOWN ***` |
| 指定设备详情 | `ibstat` | 固件版本、LID、SM LID、速率等 |
| RDMA 链路 | `rdma link show` | 子网前缀、LID、物理链路状态 |
| IB 本机自测 | `ibping` | 自发自收，验证本机 IB 协议栈 |

### 通信测试（`start-peer` + `client`）

| 测试项 | 工具 | 说明 |
|--------|------|------|
| IB 可达性 | `ibping` | 跨节点 IB 层 ping |
| RDMA 写带宽 | `ib_write_bw` | 测试实际 RDMA 写带宽（需 perftest） |

---

## 常见问题

### ibping 100% 丢包

对端没有启动监听，先运行：

```bash
bash run.sh start-peer   # 终端 1
bash run.sh client       # 终端 2
```

### SSH 连接失败

```bash
ssh-copy-id root@172.31.0.43
```

### IB 设备不存在（ERROR: IB 设备 mlx5_0 不存在）

查看当前可用设备：

```bash
ls /sys/class/infiniband/
```

然后指定正确设备：

```bash
IB_DEV=mlx5_3 bash run.sh check
```

### ib_write_bw 跳过（未安装 perftest）

```bash
sudo apt install -y perftest
```

### mlx5_5 / mlx5_6 显示 Down

这两张是 ConnectX-6（MT4123），物理上未接 IB 线缆，属于正常现象，不影响其他 4 张 ConnectX-7 的使用。
