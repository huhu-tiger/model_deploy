import os
from pathlib import Path
from moviepy.editor import ColorClip

# Set env before importing process_video_task so video_processor picks CPU options (Scheme 1)
os.environ.setdefault("USE_GPU", "false")
os.environ.setdefault("VIDEO_CODEC", "libx264")
os.environ.setdefault("VIDEO_PRESET", "fast")
os.environ.setdefault("VIDEO_THREADS", "0")
os.environ.setdefault("AUDIO_CODEC", "aac")
os.environ.setdefault("FFMPEG_BIN", "/usr/bin/ffmpeg")

from utils.video_processor import process_video_task  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
input_dir = BASE_DIR / "data" / "video" / "temp"
output_dir = BASE_DIR / "data" / "video" / "output"
input_dir.mkdir(parents=True, exist_ok=True)
output_dir.mkdir(parents=True, exist_ok=True)

input_video = input_dir / "gpu_test_input.mp4"
output_video = output_dir / "gpu_test_output.mp4"


def create_dummy_clip(path: Path):
    clip = ColorClip(size=(640, 360), color=(50, 120, 200), duration=3)
    clip = clip.set_fps(24)
    clip.write_videofile(str(path), codec="libx264", audio=False)


def main():
    if input_video.exists():
        input_video.unlink()
    if output_video.exists():
        output_video.unlink()

    create_dummy_clip(input_video)
    print(f"Created dummy input: {input_video}")

    out_path = process_video_task(
        text_content="GPU encode test",
        input_video_path=str(input_video),
        input_audio_path=None,
        output_path=str(output_video),
    )
    print(f"GPU test finished. Output: {out_path}")


if __name__ == "__main__":
    main()
