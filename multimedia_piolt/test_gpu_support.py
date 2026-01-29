#!/usr/bin/env python3
"""
GPU支持检测和测试脚本
用于检测系统是否支持GPU视频编码，并测试CPU和GPU两种模式
"""
import os
import sys
import subprocess
from pathlib import Path

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from moviepy.editor import ColorClip
from utils.video_processor import process_video_task, _load_ffmpeg_config, _validate_nvenc


def check_nvidia_gpu():
    """检查系统是否有NVIDIA GPU"""
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print("✅ 检测到NVIDIA GPU:")
            # 提取GPU信息
            lines = result.stdout.split('\n')
            for line in lines:
                if 'NVIDIA' in line or 'GeForce' in line or 'Tesla' in line or 'Quadro' in line:
                    print(f"   {line.strip()}")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass
    return False


def check_ffmpeg_nvenc(ffmpeg_bin: str = None):
    """检查ffmpeg是否支持NVENC编码器"""
    if ffmpeg_bin is None:
        ffmpeg_bin = os.getenv("FFMPEG_BIN", "/usr/bin/ffmpeg")
    
    try:
        result = subprocess.run(
            [ffmpeg_bin, "-encoders"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            if "h264_nvenc" in result.stdout:
                print(f"✅ ffmpeg ({ffmpeg_bin}) 支持 h264_nvenc 编码器")
                return True
            else:
                print(f"❌ ffmpeg ({ffmpeg_bin}) 不支持 h264_nvenc 编码器")
                print("   提示: 需要安装支持NVENC的ffmpeg版本")
                return False
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
        print(f"❌ 无法检查ffmpeg编码器: {e}")
        return False


def create_test_video(path: Path, duration: int = 3):
    """创建测试用的视频文件"""
    print(f"创建测试视频: {path}")
    clip = ColorClip(size=(640, 360), color=(50, 120, 200), duration=duration)
    clip = clip.set_fps(24)
    clip.write_videofile(str(path), codec="libx264", audio=False, verbose=False, logger=None)
    print(f"✅ 测试视频创建成功")


def test_cpu_mode():
    """测试CPU模式"""
    print("\n" + "="*60)
    print("测试 CPU 模式")
    print("="*60)
    
    # 设置环境变量为CPU模式
    os.environ["USE_GPU"] = "false"
    os.environ["VIDEO_CODEC"] = "libx264"
    
    base_dir = Path(__file__).resolve().parent
    input_dir = base_dir / "data" / "video" / "temp"
    output_dir = base_dir / "data" / "video" / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    input_video = input_dir / "cpu_test_input.mp4"
    output_video = output_dir / "cpu_test_output.mp4"
    
    # 清理旧文件
    if input_video.exists():
        input_video.unlink()
    if output_video.exists():
        output_video.unlink()
    
    try:
        # 创建测试视频
        create_test_video(input_video)
        
        # 处理视频
        print("开始处理视频（CPU模式）...")
        result_path = process_video_task(
            text_content="CPU编码测试",
            input_video_path=str(input_video),
            input_audio_path=None,
            output_path=str(output_video),
        )
        
        if os.path.exists(result_path):
            file_size = os.path.getsize(result_path)
            print(f"✅ CPU模式测试成功!")
            print(f"   输出文件: {result_path}")
            print(f"   文件大小: {file_size / 1024 / 1024:.2f} MB")
            return True
        else:
            print("❌ CPU模式测试失败: 输出文件不存在")
            return False
    except Exception as e:
        print(f"❌ CPU模式测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_gpu_mode():
    """测试GPU模式"""
    print("\n" + "="*60)
    print("测试 GPU 模式")
    print("="*60)
    
    # 设置环境变量为GPU模式
    os.environ["USE_GPU"] = "true"
    os.environ["VIDEO_CODEC"] = "h264_nvenc"
    
    base_dir = Path(__file__).resolve().parent
    input_dir = base_dir / "data" / "video" / "temp"
    output_dir = base_dir / "data" / "video" / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    input_video = input_dir / "gpu_test_input.mp4"
    output_video = output_dir / "gpu_test_output.mp4"
    
    # 清理旧文件
    if input_video.exists():
        input_video.unlink()
    if output_video.exists():
        output_video.unlink()
    
    try:
        # 创建测试视频
        create_test_video(input_video)
        
        # 检查GPU配置
        ffmpeg_bin, use_gpu, video_codec, video_preset, video_threads, audio_codec, gpu_device = _load_ffmpeg_config()
        print(f"配置信息:")
        print(f"  FFMPEG_BIN: {ffmpeg_bin}")
        print(f"  USE_GPU: {use_gpu}")
        print(f"  VIDEO_CODEC: {video_codec}")
        print(f"  VIDEO_PRESET: {video_preset}")
        print(f"  GPU_DEVICE: {gpu_device}")
        cuda_visible = os.getenv('CUDA_VISIBLE_DEVICES')
        if cuda_visible:
            print(f"  CUDA_VISIBLE_DEVICES: {cuda_visible}")
            print(f"    注意: 将使用可见设备列表中的设备 {gpu_device}")
        
        # 验证NVENC
        try:
            _validate_nvenc(video_codec, ffmpeg_bin)
            print("✅ NVENC编码器验证通过")
        except RuntimeError as e:
            print(f"❌ NVENC编码器验证失败: {e}")
            return False
        
        # 处理视频
        print("开始处理视频（GPU模式）...")
        result_path = process_video_task(
            text_content="GPU编码测试",
            input_video_path=str(input_video),
            input_audio_path=None,
            output_path=str(output_video),
        )
        
        if os.path.exists(result_path):
            file_size = os.path.getsize(result_path)
            print(f"✅ GPU模式测试成功!")
            print(f"   输出文件: {result_path}")
            print(f"   文件大小: {file_size / 1024 / 1024:.2f} MB")
            return True
        else:
            print("❌ GPU模式测试失败: 输出文件不存在")
            return False
    except Exception as e:
        error_msg = str(e)
        print(f"❌ GPU模式测试失败: {e}")
        if "unsupported device" in error_msg.lower() or "no capable devices found" in error_msg.lower():
            print("\n可能的原因:")
            print("  1. CUDA_VISIBLE_DEVICES指定的GPU设备不可用")
            print("  2. GPU设备被其他进程占用")
            print("  3. ffmpeg无法访问指定的GPU设备")
            print("  4. 需要检查GPU驱动和CUDA版本兼容性")
            print("\n建议:")
            cuda_visible = os.getenv('CUDA_VISIBLE_DEVICES')
            if cuda_visible:
                print(f"  - 检查CUDA_VISIBLE_DEVICES={cuda_visible}指定的GPU是否可用")
                print(f"  - 运行: nvidia-smi 查看GPU状态")
            else:
                print("  - 尝试设置CUDA_VISIBLE_DEVICES来指定GPU设备")
                print("  - 例如: export CUDA_VISIBLE_DEVICES=0")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("="*60)
    print("GPU支持检测和测试")
    print("="*60)
    
    # 1. 检查NVIDIA GPU
    print("\n1. 检查NVIDIA GPU硬件...")
    has_gpu = check_nvidia_gpu()
    if not has_gpu:
        print("❌ 未检测到NVIDIA GPU硬件")
        print("   提示: GPU模式需要NVIDIA GPU硬件支持")
    
    # 2. 检查ffmpeg NVENC支持
    print("\n2. 检查ffmpeg NVENC支持...")
    ffmpeg_bin = os.getenv("FFMPEG_BIN", "/usr/bin/ffmpeg")
    has_nvenc = check_ffmpeg_nvenc(ffmpeg_bin)
    
    # 3. 显示当前环境变量配置
    print("\n3. 当前环境变量配置:")
    print(f"   USE_GPU: {os.getenv('USE_GPU', '未设置')}")
    print(f"   VIDEO_CODEC: {os.getenv('VIDEO_CODEC', '未设置')}")
    print(f"   FFMPEG_BIN: {os.getenv('FFMPEG_BIN', '未设置')}")
    print(f"   CUDA_VISIBLE_DEVICES: {os.getenv('CUDA_VISIBLE_DEVICES', '未设置')}")
    print(f"   GPU_DEVICE: {os.getenv('GPU_DEVICE', '未设置（将使用默认值0）')}")
    
    if os.getenv('CUDA_VISIBLE_DEVICES'):
        print(f"   提示: CUDA_VISIBLE_DEVICES已设置，ffmpeg将使用可见设备列表中的第一个设备（索引0）")
    
    # 4. 测试CPU模式
    cpu_success = test_cpu_mode()
    
    # 5. 测试GPU模式（如果支持）
    gpu_success = False
    if has_gpu and has_nvenc:
        gpu_success = test_gpu_mode()
    else:
        print("\n" + "="*60)
        print("跳过GPU模式测试（硬件或编码器不支持）")
        print("="*60)
    
    # 6. 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    print(f"CPU模式: {'✅ 通过' if cpu_success else '❌ 失败'}")
    print(f"GPU模式: {'✅ 通过' if gpu_success else '❌ 不支持或失败'}")
    
    if gpu_success:
        print("\n✅ 系统支持GPU加速视频编码!")
        print("   可以通过设置环境变量 USE_GPU=true 来启用GPU模式")
    elif has_gpu and not has_nvenc:
        print("\n⚠️  检测到GPU硬件，但ffmpeg不支持NVENC")
        print("   建议: 安装支持NVENC的ffmpeg版本")
    elif not has_gpu:
        print("\n⚠️  未检测到GPU硬件，将使用CPU模式")
    
    print("\n环境变量使用说明:")
    print("  - 启用GPU: export USE_GPU=true")
    print("  - 使用CPU: export USE_GPU=false (或取消设置)")
    print("  - 指定ffmpeg路径: export FFMPEG_BIN=/path/to/ffmpeg")


if __name__ == "__main__":
    main()
