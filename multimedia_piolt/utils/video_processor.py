import os
import logging
import subprocess
from pathlib import Path
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips

# Configure logger
logger = logging.getLogger(__name__)

# Configuration paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_PATH = os.path.join(BASE_DIR, "resources/audio/cebd014a85424322b80ac65b97f38430.wav")
ENDING_VIDEO_PATH = os.path.join(BASE_DIR, "resources/video/163150.mp4")
# FONT_PATH = "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"
FONT_PATH = "resources/ttf/演示春风楷.ttf"

def _load_ffmpeg_config():
    """Load ffmpeg config from current environment and update related vars."""
    ffmpeg_bin = os.getenv("FFMPEG_BIN", "/usr/bin/ffmpeg")
    os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_bin
    os.environ["FFMPEG_BINARY"] = ffmpeg_bin
    ffmpeg_dir = str(Path(ffmpeg_bin).parent)
    os.environ["PATH"] = f"{ffmpeg_dir}:{os.environ.get('PATH','')}"

    use_gpu = os.getenv("USE_GPU", "false").lower() == "true"
    # Get video codec from env, but respect USE_GPU setting
    env_video_codec = os.getenv("VIDEO_CODEC", "")
    if use_gpu:
        # GPU mode: use h264_nvenc by default, or use env value if set
        video_codec = env_video_codec if env_video_codec else "h264_nvenc"
    else:
        # CPU mode: force libx264, ignore VIDEO_CODEC if it's set to any GPU codec (nvenc)
        # Check for any NVENC codec (h264_nvenc, hevc_nvenc, etc.)
        if env_video_codec and "_nvenc" in env_video_codec.lower():
            logger.warning(
                f"USE_GPU=false but VIDEO_CODEC={env_video_codec} is a GPU codec. "
                "Forcing libx264 for CPU mode. Set USE_GPU=true to use GPU encoding."
            )
            video_codec = "libx264"
        else:
            video_codec = env_video_codec if env_video_codec else "libx264"
    video_preset = os.getenv("VIDEO_PRESET", "fast")    # nvenc preset when using GPU
    video_threads = int(os.getenv("VIDEO_THREADS", "0")) # 0 lets ffmpeg decide
    audio_codec = os.getenv("AUDIO_CODEC", "aac")
    # GPU device selection: use CUDA_VISIBLE_DEVICES if set, otherwise default to 0
    cuda_visible_devices = os.getenv("CUDA_VISIBLE_DEVICES")
    if cuda_visible_devices is not None:
        # If CUDA_VISIBLE_DEVICES is set, use the first device (index 0 in the visible set)
        gpu_device = "0"
    else:
        # If not set, use GPU 0 by default
        gpu_device = os.getenv("GPU_DEVICE", "0")
    return ffmpeg_bin, use_gpu, video_codec, video_preset, video_threads, audio_codec, gpu_device


def _validate_nvenc(codec: str, ffmpeg_bin: str):
    """Ensure NVENC encoder exists when GPU path is requested."""
    if codec != "h264_nvenc":
        return
    out = subprocess.check_output([ffmpeg_bin, "-encoders"], stderr=subprocess.STDOUT, text=True)
    if "h264_nvenc" not in out:
        raise RuntimeError(f"ffmpeg at {ffmpeg_bin} missing h264_nvenc; check FFMPEG_BIN or install NVENC build")


def process_video_task(text_content: str, input_video_path: str, input_audio_path: str = None, output_path: str = "output.mp4"):
    """
    1. Adds text to input video (starts at 2s, bottom-center).
    2. Merges specific audio (starts at 2s).
    3. Concatenates with a specific ending video.
    """
    if not os.path.exists(input_video_path):
        raise FileNotFoundError(f"Input video not found: {input_video_path}")

    video_clip = VideoFileClip(input_video_path)
    video_duration = video_clip.duration

    # Add text overlay
    try:
        txt_clip = TextClip(
            text_content,
            fontsize=120,
            color='white',
            font=FONT_PATH,
            method='caption',
            size=(int(video_clip.w * 0.8), None)
        )
        txt_clip = txt_clip.set_position(('center', 0.4), relative=True).set_start(2).set_duration(video_duration - 2)
        video_with_text = CompositeVideoClip([video_clip, txt_clip])
    except Exception as e:
        logger.warning(f"Failed to create TextClip. Ensure ImageMagick is configured correctly. Error: {e}")
        video_with_text = video_clip

    # Handle Audio
    target_audio_path = input_audio_path if input_audio_path else AUDIO_PATH
    if target_audio_path and os.path.exists(target_audio_path):
        try:
            audio_clip = AudioFileClip(target_audio_path)
            audio_clip = audio_clip.set_start(2).volumex(1.8)
            original_audio = video_with_text.audio
            if original_audio:
                original_audio = original_audio.volumex(0.3)
                final_audio = CompositeAudioClip([original_audio, audio_clip])
            else:
                final_audio = CompositeAudioClip([audio_clip])
            final_audio = final_audio.set_duration(video_duration)
            video_with_text.audio = final_audio
        except Exception as e:
            logger.warning(f"Failed to process audio. Error: {e}")
    else:
        logger.warning(f"Audio file not found at {target_audio_path}")

    # Concatenate with ending video
    final_clip = video_with_text
    if os.path.exists(ENDING_VIDEO_PATH):
        try:
            ending_clip = VideoFileClip(ENDING_VIDEO_PATH)
            final_clip = concatenate_videoclips([video_with_text, ending_clip], method="compose")
        except Exception as e:
            logger.warning(f"Failed to load ending video. Error: {e}")
    else:
        logger.warning(f"Ending video file not found at {ENDING_VIDEO_PATH}")

    # Refresh ffmpeg config (env may be loaded after module import)
    ffmpeg_bin, use_gpu, video_codec, video_preset, video_threads, audio_codec, gpu_device = _load_ffmpeg_config()
    
    # Log CUDA_VISIBLE_DEVICES if set
    cuda_visible = os.getenv("CUDA_VISIBLE_DEVICES")
    logger.info(
        "FFMPEG_BIN=%s USE_GPU=%s VIDEO_CODEC=%s GPU_DEVICE=%s CUDA_VISIBLE_DEVICES=%s",
        ffmpeg_bin,
        use_gpu,
        video_codec,
        gpu_device,
        cuda_visible if cuda_visible else "not set",
    )
    try:
        from moviepy.config import change_settings
        change_settings({"FFMPEG_BINARY": ffmpeg_bin})
    except Exception as e:
        logger.warning(f"Failed to set MoviePy FFMPEG_BINARY: {e}")
    if use_gpu and video_codec == "h264_nvenc":
        try:
            _validate_nvenc(video_codec, ffmpeg_bin)
        except Exception as e:
            logger.warning(f"NVENC unavailable, falling back to libx264. Reason: {e}")
            video_codec = "libx264"

    # Write Output
    try:
        ffmpeg_params = []
        if video_codec == "h264_nvenc":
            # For NVENC, specify GPU device using -gpu parameter
            ffmpeg_params.extend(["-gpu", gpu_device, "-preset", video_preset, "-pix_fmt", "yuv420p"])
        if video_threads > 0:
            ffmpeg_params.extend(["-threads", str(video_threads)])

        final_clip.write_videofile(
            output_path,
            codec=video_codec,
            audio_codec=audio_codec,
            ffmpeg_params=ffmpeg_params or None,
        )
        logger.info(f"Successfully created video: {output_path}")
        return output_path
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error writing output file: {e}")
        # If NVENC fails at runtime (unsupported device), fallback to CPU encoding
        if video_codec == "h264_nvenc":
            if "unsupported device" in error_msg.lower() or "no capable devices found" in error_msg.lower():
                logger.warning(
                    f"NVENC runtime failure: GPU device {gpu_device} is not accessible. "
                    f"This may be due to CUDA_VISIBLE_DEVICES={cuda_visible} or GPU permissions. "
                    "Falling back to CPU encoding (libx264)."
                )
            else:
                logger.warning(f"NVENC runtime failure; retrying with libx264. Error: {error_msg}")
            try:
                final_clip.write_videofile(
                    output_path,
                    codec="libx264",
                    audio_codec=audio_codec,
                    ffmpeg_params=["-pix_fmt", "yuv420p"],
                )
                logger.info(f"Successfully created video with libx264 fallback: {output_path}")
                return output_path
            except Exception as fallback_error:
                logger.error(f"Fallback libx264 failed: {fallback_error}")
                raise fallback_error
        raise e
