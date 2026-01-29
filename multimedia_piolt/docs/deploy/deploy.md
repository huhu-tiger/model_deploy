# 安装部署（CPU 与 GPU）

## 0. 基础信息
- 代码目录：`multimedia_piolt`
- API 默认端口：`8003`
- 路由前缀：`/multimedia_piolt/video_edit/v1`
- 环境变量文件：`.env`（启动时由 `app_context` 自动加载）

## 1. 系统依赖

### CPU 模式（最小化安装）
```bash
apt-get update
apt-get install -y ffmpeg imagemagick fonts-droid-fallback
# 如需中文字体，额外安装字体或将字体放入 resources/ttf
```

### GPU 模式（NVENC 编码）
```bash
apt-get update
apt-get install -y imagemagick fonts-droid-fallback
# 建议通过 conda 安装带 NVENC 的 ffmpeg
conda install -c conda-forge ffmpeg
# 验证 NVENC 编码器可用
ffmpeg -encoders | grep nvenc
# 需看到 h264_nvenc / hevc_nvenc 等条目
```

**ImageMagick policy**：若出现 policy 限制，编辑 `/etc/ImageMagick-6/policy.xml` 按需放开（仅限受控环境）。

## 2. Python 环境
推荐使用 Conda：
```bash
# 注意：如果使用清华镜像源遇到 Python 3.12 不可用的问题，
# 可以临时恢复官方源或使用 Python 3.10/3.11
conda config --remove-key default_channels  # 恢复官方源（如果需要）
conda create -n multimedia_piolt python=3.10 -y  # 推荐使用 3.10，兼容性好
conda activate multimedia_piolt
```

## 3. 安装 Python 依赖
```bash
pip install -r requirements.txt
```

## 4. 环境变量配置（.env）
- CPU 示例：
```
USE_GPU=false
VIDEO_CODEC=libx264
FFMPEG_BIN=/usr/bin/ffmpeg
```
- GPU 示例（第 3 块卡，NVENC）：
```
USE_GPU=true
VIDEO_CODEC=h264_nvenc
VIDEO_PRESET=fast
CUDA_VISIBLE_DEVICES=2   # 0-based，第 3 张卡
FFMPEG_BIN=/media/conda/envs/multimedia_piolt/bin/ffmpeg
```
其他目录和 MinIO 配置已在 `.env` 给出默认值，可按需要修改。

**服务使用 NVENC 时的常见问题与排查**
- 确认 ffmpeg 路径：`FFMPEG_BIN` 应指向带 NVENC 的 ffmpeg（可用 `ffmpeg -encoders | grep nvenc` 验证）。
- 若报 “Unknown encoder 'h264_nvenc'”，多半是路径不对或 ffmpeg 未编译 NVENC。可临时改回 CPU：`USE_GPU=false`、`VIDEO_CODEC=libx264`。
- 进程需读取 `.env`：FastAPI 启动时由 `app_context` 自动加载本目录 `.env`。修改后需重启服务生效。

**GPU 是否支持 NVENC（硬件支持检查）**
- 查看显卡型号：`nvidia-smi -L`。很多计算卡（如 A100/A800 等）不带 NVENC。
- 查看 ffmpeg 是否编译 NVENC：`ffmpeg -encoders | grep -i nvenc`（需出现 `h264_nvenc`/`hevc_nvenc`）。
- 运行时报错 “unsupported device / No capable devices found” 说明当前可见 GPU 不支持 NVENC；请切换到支持 NVENC 的 GPU 或使用 CPU 编码（`libx264`）。

## 5. 运行与验证
```bash
conda activate multimedia_piolt
python api.py              # 或 uvicorn api:app --host 0.0.0.0 --port 8003
```

### 快速自检（可选）
```bash
python test_gpu_video_encode.py   # 根据 .env 使用 CPU 或 GPU 编码
```

日志输出在 `logs/api.log`（可通过 .env 调整）。
