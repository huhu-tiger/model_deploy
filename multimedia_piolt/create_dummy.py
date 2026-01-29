from moviepy.editor import ColorClip
import os

def create_dummy_video(filename="dummy.mp4", duration=5, color=(255, 0, 0)):
    print(f"Generating dummy video: {filename} ({duration}s)")
    clip = ColorClip(size=(640, 480), color=color, duration=duration)
    clip.fps = 24
    clip.write_videofile(filename, codec='libx264', audio_codec='aac')
    print("Done.")

if __name__ == "__main__":
    create_dummy_video("multimedia_piolt/resources/video/dummy_test.mp4", duration=5, color=(0, 0, 255))
