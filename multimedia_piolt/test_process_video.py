import os
import sys

# Ensure the current directory is in the path so we can import video_processor
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.video_processor import process_video_task

# Paths relative to this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# utilizing the existing video resource as a test input video
INPUT_VIDEO = os.path.join(BASE_DIR, "resources/video/163144.mp4")
INPUT_AUDIO = os.path.join(BASE_DIR, "resources/audio/cebd014a85424322b80ac65b97f38430.wav")
OUTPUT_VIDEO = os.path.join(BASE_DIR, "test_output_result.mp4")
TEST_TEXT = "齐天瑞彩迎新岁 \n梅蕊清香报早春\n"

def run_test():
    print(f"Checking input video: {INPUT_VIDEO}")
    if not os.path.exists(INPUT_VIDEO):
        print(f"Error: Input video not found at {INPUT_VIDEO}")
        print("Please ensure the resources are downloaded or place a dummy .mp4 file there.")
        return

    print("Starting processing task...")
    print(f"Text content: {TEST_TEXT}")
    
    try:
        result_path = process_video_task(
            text_content=TEST_TEXT,
            input_video_path=INPUT_VIDEO,
            input_audio_path=INPUT_AUDIO,
            output_path=OUTPUT_VIDEO
        )
        print("-" * 30)
        print(f"✅ Test Passed!")
        print(f"Output saved to: {result_path}")
        print("-" * 30)
    except ImportError as e:
        print(f"❌ ImportError: {e}")
        print("Did you install moviepy? Run: pip install moviepy")
    except Exception as e:
        print(f"❌ Test Failed with error:")
        print(e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_test()
