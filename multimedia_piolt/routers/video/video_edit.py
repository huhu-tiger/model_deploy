import os
import shutil
import uuid
import traceback
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

# Load env/logging first so video_processor sees the correct settings (FFMPEG_BIN, USE_GPU, etc.)
from app_context import (
    logger,
    download_file_via_http,
    minio_handler,
    TEMP_DIR,
    OUTPUT_DIR,
    DOWNLOAD_DIR,
)
from utils.video_processor import process_video_task


class VideoProcessRequest(BaseModel):
    text: str
    video_path: str


class VideoProcessUrlRequest(BaseModel):
    video_url: str
    text: str
    audio_url: str


router = APIRouter(prefix="/multimedia_piolt/video_edit/v1")


@router.post("/process_video_by_url/")
async def process_video_url_endpoint(request: VideoProcessUrlRequest):
    """Process video by downloading media from provided URLs."""
    logger.info(f"Received request for URL processing. Video URL: {request.video_url}")
    video_temp_path = None
    audio_temp_path = None
    video_downloaded = None
    audio_downloaded = None
    try:
        if download_file_via_http is None:
            raise HTTPException(status_code=500, detail="Function download_file_via_http is not available")

        task_id = str(uuid.uuid4())
        video_target_path = os.path.join(DOWNLOAD_DIR, f"{task_id}_video.mp4")
        audio_target_path = os.path.join(DOWNLOAD_DIR, f"{task_id}_audio.wav")

        try:
            logger.info("Downloading video...")
            video_downloaded = download_file_via_http(request.video_url)
            shutil.move(video_downloaded, video_target_path)
            video_temp_path = video_target_path
            logger.info("Video downloaded successfully.")
        except Exception as e:
            logger.error(f"Failed to download video: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to download video: {e}")

        try:
            logger.info("Downloading audio...")
            audio_downloaded = download_file_via_http(request.audio_url)
            shutil.move(audio_downloaded, audio_target_path)
            audio_temp_path = audio_target_path
            logger.info("Audio downloaded successfully.")
        except Exception as e:
            logger.error(f"Failed to download audio: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to download audio: {e}")

        output_filename = f"processed_{task_id}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        logger.info(f"Starting video processing. Output: {output_path}")
        result_path = process_video_task(request.text, video_temp_path, audio_temp_path, output_path)

        minio_url = None
        if minio_handler and os.path.exists(result_path):
            try:
                logger.info("Uploading result to MinIO...")
                upload_res = minio_handler.upload_file(result_path, upload_dir="ai_video_processor/output")
                if not upload_res['error']:
                    minio_url = minio_handler.generate_download_url(upload_res['minio_put_path'])
                    logger.info(f"Uploaded to MinIO: {minio_url}")
                else:
                    logger.error(f"MinIO upload error: {upload_res.get('error_str')}")
            except Exception as e:
                logger.error(f"Failed to upload to MinIO: {e}")

        return {
            "status": "success",
            "output_path": result_path,
            "minio_url": minio_url,
            "message": "Video processed successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in process_video_url_endpoint: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for path in [video_temp_path, audio_temp_path, video_downloaded, audio_downloaded]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass


@router.post("/process_video/")
async def process_video_endpoint(text: str = Form(...), video_file: UploadFile = File(...)):
    """Process an uploaded video file."""
    input_path = None
    try:
        logger.info(f"Received file upload process request. Filename: {video_file.filename}")

        input_filename = f"{uuid.uuid4()}_{video_file.filename}"
        input_path = os.path.join(TEMP_DIR, input_filename)

        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(video_file.file, buffer)

        output_filename = f"processed_{input_filename}"
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        logger.info(f"Processing uploaded video: {input_path}")
        result_path = process_video_task(text, input_path, output_path)
        logger.info(f"Processing complete: {result_path}")

        return {"status": "success", "output_path": result_path, "message": "Video processed successfully"}

    except Exception as e:
        logger.error(f"Error in process_video_endpoint: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if input_path and os.path.exists(input_path):
            # Intentionally retaining the uploaded temp file; remove here if cleanup is desired.
            pass


@router.post("/process_video_by_path/")
async def process_video_path_endpoint(request: VideoProcessRequest):
    """Process video given a server-side file path."""
    logger.info(f"Received path process request: {request.video_path}")
    try:
        if not os.path.exists(request.video_path):
            logger.warning(f"File not found: {request.video_path}")
            raise HTTPException(status_code=404, detail="Input video file not found")

        output_filename = f"processed_{uuid.uuid4()}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        result_path = process_video_task(request.text, request.video_path, output_path)
        logger.info(f"Processing complete: {result_path}")

        return {"status": "success", "output_path": result_path}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in process_video_path_endpoint: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
