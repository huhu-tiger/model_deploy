# 视频模块部署说明（CPU / GPU）

# 视频模块部署说明（CPU / GPU）

## 目录
- [0. 基本信息](#0-基本信息)
- [1. 系统依赖](#1-系统依赖)
	- [CPU 安装示例](#cpu-安装示例)
	- [GPU 安装示例（NVENC）](#gpu-安装示例nvenc)
- [2. Python 环境](#2-python-环境)
- [3. .env 关键配置](#3-env-关键配置)
- [4. 启动与验证](#4-启动与验证)

## 0. 基本信息
- 代码目录：`multimedia_piolt`
- 服务端口：`8003`
- 路由前缀：`/multimedia_piolt/video_edit/v1`
- 环境变量文件：`.env`（启动时自动加载）

## 1. 系统依赖
- 必需：ImageMagick、字体（如 `fonts-droid-fallback`），ffmpeg。
- GPU 模式需 ffmpeg 支持 NVENC。

### CPU 安装示例
```bash
apt-get update
apt-get install -y ffmpeg imagemagick fonts-droid-fallback
```

### GPU 安装示例（NVENC）
```bash
apt-get update
apt-get install -y imagemagick fonts-droid-fallback
conda install -c conda-forge ffmpeg
ffmpeg -encoders | grep nvenc   # 确认有 h264_nvenc
```

## 2. Python 环境
```bash
conda create -n multimedia_piolt python=3.12 -y
conda activate multimedia_piolt
pip install -r requirements.txt
```

## 3. .env 关键配置
- CPU 模式示例：
```
USE_GPU=false
VIDEO_CODEC=libx264
FFMPEG_BIN=/usr/bin/ffmpeg
```
- GPU 模式示例（第 3 张卡）：
```
USE_GPU=true
VIDEO_CODEC=h264_nvenc
VIDEO_PRESET=fast
VIDEO_THREADS=0
CUDA_VISIBLE_DEVICES=2
FFMPEG_BIN=/media/conda/envs/multimedia_piolt/bin/ffmpeg
```
其他目录、MinIO、日志配置已在 `.env` 给出默认值，可按需调整。

## 4. 启动与验证
```bash
conda activate multimedia_piolt
python api.py
# 或 uvicorn api:app --host 0.0.0.0 --port 8003
```

### 自检（可选）
```bash
python test_gpu_video_encode.py   # 将按 .env 选择 CPU/GPU 编码
```

日志输出默认在 `logs/api.log`。
