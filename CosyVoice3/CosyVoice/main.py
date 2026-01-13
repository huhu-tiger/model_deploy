import sys
import os, io
import json, time
import logging, wave
import asyncio
from fastapi import HTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.responses import StreamingResponse
from fastapi.routing import Mount
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
import random
import numpy as np
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, validator
import requests
from datetime import datetime
import tempfile

import sys
sys.path.append('third_party/Matcha-TTS')
from cosyvoice.cli.cosyvoice import AutoModel
from cosyvoice.utils.file_utils import load_wav
from cosyvoice.utils.common import set_all_random_seed

import torch
import torchaudio

from app.response import error_response,success_response
from app.schemas import (
    ChatCompletionRequest, 
    TTSCloneRequest, 
    TTSCloneDelRequest, 
    TTSCloneSpkRequest,
    TTSInstructRequest,
    TTSCrossLingualRequest
)
from app.utils import get_filename_from_url, download_file

Current_Dir = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(Current_Dir)
sys.path.append(os.path.dirname(BASE_DIR))

from vnet.common.config.env import load_env
load_env(dotenv_path=os.path.join(Current_Dir, ".env"), override=False)

from vnet.common.storage.dal.minio.minio_conn import minio_handler
from vnet.common.tools.http_utils import multiple_download_async

# gpu使用
os.environ["CUDA_VISIBLE_DEVICES"] = "7"

# 模型加载
cosyvoice = AutoModel(model_dir='pretrained_models/Fun-CosyVoice3-0.5B-2512')

# 获取项目根目录的绝对路径，公共变量
project_root = os.path.dirname(os.path.abspath(__file__))
download_dir = os.path.join(project_root,"public","download")
upload_dir = os.path.join(project_root,"public","upload")
sys.path.append(project_root)
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

logger = logging.getLogger(__name__)

# fastapi 框架层
app = FastAPI(docs_url=None, redoc_url=None)
## 挂载 public/upload/ 作为静态文件服务器路径
upload_static_path = os.path.join(project_root, "public", "upload")
os.makedirs(upload_static_path, exist_ok=True)
app.mount("/upload", StaticFiles(directory=upload_static_path), name="upload")

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()

# 打印所有路由
def print_routes(app: FastAPI):
    print("Registered Routes:")
    for route in app.routes:
        # 检查是否为 Mount 类型
        if isinstance(route, Mount):
            print(f"{route.path} -> Static (mounted at {route.name})")
        else:
            methods = ", ".join(route.methods)
            print(f"{route.path} -> {methods}")

# 音色列表
@app.get("/tts_clone/spk/list")
def tts_spk_list():
    voices = cosyvoice.list_available_spks()
    logger.info(f"音色克隆已上传voice:{cosyvoice.list_available_spks()}")
    return success_response(data=voices)

# 音色创建
@app.post("/tts_clone/spk/create")
async def tts_spk_create(request: TTSCloneSpkRequest):
    input_text = request.input
    voice_name = request.voice_name
    voice_id = voice_name + "_" +str(random.randint(1000, 9999))
    voice_file = request.voice_file
    src_file_name = get_filename_from_url(voice_file)

    voice_file_path = os.path.join(upload_dir,src_file_name)

    if download_file(url=voice_file, destination_path=voice_file_path) == False:
        return error_response(code=400,message=f"下载音色文件失败")

    logger.info(f"spk download_file:{voice_file_path}")
    logger.info(f"voice_name: {voice_name},voice_id:{voice_id}")
    # add_zero_shot_spk 期望的是文件路径，不是 tensor
    try:
        assert cosyvoice.add_zero_shot_spk(input_text, voice_file_path, voice_id) is True
        cosyvoice.save_spkinfo()
        return success_response(data="ok",message={"voice_id":voice_id,"list_spks":cosyvoice.list_available_spks()})
    except Exception as e:
        logger.error(f"上传音色失败: {e}")
        return error_response(code=400,message=f"上传音色失败: {e}")

# 音色删除
@app.post("/tts_clone/spk/delete")
async def tts_spk_delete(request: TTSCloneDelRequest):
    voices = cosyvoice.list_available_spks()
    voice_id = request.voice_id
    if voice_id not in voices:
        return error_response(code=400,message=f"音色不存在: {voice_id}")
    try:
        assert cosyvoice.delete_spk(voice_id) is True
        return success_response(data="ok",message={"list_spks":cosyvoice.list_available_spks()})
    except Exception as e:
        logger.error(f"删除音色 {e} 失败 ")
        return error_response(code=400,message=f"删除音色 {e} 失败")

# 音色克隆 (zero_shot)
@app.post("/tts_clone/spk/gen")
async def tts_clone_gen(request: TTSCloneRequest):
    input_text = request.input
    prompt_text = request.prompt_text
    voice_id = request.voice_id
    prompt_file = request.prompt_file
    voices = cosyvoice.list_available_spks()
    
    if voice_id and voice_id not in voices:
        return error_response(code=400,message=f"音色不存在: {voice_id}")
    
    # 如果没有 voice_id，必须提供 prompt_file
    if not voice_id and not prompt_file:
        return error_response(code=400, message="需要提供 voice_id 或 prompt_file")
    
    ts_int = int(time.time())
    os.makedirs(download_dir, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(prefix=f"zero_shot_{ts_int}_", suffix=".wav", dir=download_dir, delete=False)
    WAV_FILE_PATH = tmp.name
    tmp.close()

    logger.info(f"Received request with parameters: {request}")

    # 收集分段音频并一次性保存，避免覆盖只保留最后一段
    _segments = []
    
    # 如果提供了 voice_id，使用已保存的音色
    if voice_id:
        # 使用已保存的音色，参考 example.py 中 CosyVoice2 的用法
        # 当使用 voice_id 时，prompt_text 和 prompt_wav 可以为空字符串
        for _, j in enumerate(cosyvoice.inference_zero_shot(
            input_text, 
            '',  # prompt_text 为空，使用 voice_id
            '',  # prompt_wav 为空，使用 voice_id
            zero_shot_spk_id=voice_id, 
            stream=False
        )):
            _segments.append(j['tts_speech'])
    else:
        # 使用 prompt_file，参考 example.py 中 CosyVoice3 的用法
        # prompt_wav 应该传递文件路径，而不是加载后的 tensor
        src_file_name = get_filename_from_url(prompt_file)
        prompt_file_path = os.path.join(upload_dir, f"prompt_{ts_int}_{src_file_name}")
        
        if download_file(url=prompt_file, destination_path=prompt_file_path) == False:
            return error_response(code=400, message=f"下载 prompt 文件失败")
        
        # 直接传递文件路径，inference_zero_shot 内部会处理
        for _, j in enumerate(cosyvoice.inference_zero_shot(
            input_text,
            prompt_text,
            prompt_file_path,  # 传递文件路径，不是 tensor
            stream=False
        )):
            _segments.append(j['tts_speech'])
    
    if len(_segments) == 0:
        return error_response(code=500, message="未生成任何音频数据")
    full_audio = torch.cat(_segments, dim=1)
    torchaudio.save(WAV_FILE_PATH, full_audio, cosyvoice.sample_rate)

    # 根据 output 返回
    if getattr(request, "output", "file") == "file":
        def iterfile():
            with open(WAV_FILE_PATH, "rb") as f:
                while chunk := f.read(1024):  # 逐块读取文件，每次读取 1024 字节
                    yield chunk
        return StreamingResponse(iterfile(), media_type="audio/wav")
    elif request.output == "url":
        upload_result = minio_handler.upload_file(file_path=WAV_FILE_PATH)
        if upload_result.get("error"):
            err = upload_result.get("error_str", "upload error")
            logger.error(f"MinIO 上传失败: {err}")
            return error_response(code=500, message=f"MinIO 上传失败: {err}")
        minio_object_path = upload_result.get("minio_put_path")
        minio_download_url = minio_handler.generate_download_url(minio_object_path)
        return success_response(
            data="ok",
            message={
                "voice_id": voice_id,
                "audio_url": minio_download_url,
                "minio_path": minio_object_path
            }
        )

    # 兜底：默认返回文件
    def iterfile():
        with open(WAV_FILE_PATH, "rb") as f:
            while chunk := f.read(1024):
                yield chunk
    return StreamingResponse(iterfile(), media_type="audio/wav")

# Instruct 模式
@app.post("/tts/instruct")
async def tts_instruct(request: TTSInstructRequest):
    input_text = request.input
    instruct_text = request.instruct_text
    prompt_file = request.prompt_file
    
    if not prompt_file:
        return error_response(code=400, message="需要提供 prompt_file")
    
    ts_int = int(time.time())
    os.makedirs(download_dir, exist_ok=True)
    src_file_name = get_filename_from_url(prompt_file)
    prompt_file_path = os.path.join(upload_dir, f"prompt_{ts_int}_{src_file_name}")
    
    if download_file(url=prompt_file, destination_path=prompt_file_path) == False:
        return error_response(code=400, message=f"下载 prompt 文件失败")
    
    prompt_wav = load_wav(prompt_file_path, 16000)
    
    tmp = tempfile.NamedTemporaryFile(prefix=f"instruct_{ts_int}_", suffix=".wav", dir=download_dir, delete=False)
    WAV_FILE_PATH = tmp.name
    tmp.close()

    logger.info(f"Received instruct request: input={input_text}, instruct={instruct_text}")

    _segments = []
    for _, j in enumerate(cosyvoice.inference_instruct2(
        input_text,
        instruct_text,
        prompt_wav,
        stream=False
    )):
        _segments.append(j['tts_speech'])
    
    if len(_segments) == 0:
        return error_response(code=500, message="未生成任何音频数据")
    full_audio = torch.cat(_segments, dim=1)
    torchaudio.save(WAV_FILE_PATH, full_audio, cosyvoice.sample_rate)

    if request.output == "url":
        upload_result = minio_handler.upload_file(file_path=WAV_FILE_PATH)
        if upload_result.get("error"):
            err = upload_result.get("error_str", "upload error")
            logger.error(f"MinIO 上传失败: {err}")
            return error_response(code=500, message=f"MinIO 上传失败: {err}")
        minio_object_path = upload_result.get("minio_put_path")
        minio_download_url = minio_handler.generate_download_url(minio_object_path)
        return success_response(
            data="ok",
            message={
                "audio_url": minio_download_url,
                "minio_path": minio_object_path
            }
        )
    
    def iterfile():
        with open(WAV_FILE_PATH, "rb") as f:
            while chunk := f.read(1024):
                yield chunk
    return StreamingResponse(iterfile(), media_type="audio/wav")

# Cross-lingual 模式
@app.post("/tts/cross_lingual")
async def tts_cross_lingual(request: TTSCrossLingualRequest):
    input_text = request.input
    prompt_file = request.prompt_file
    
    if not prompt_file:
        return error_response(code=400, message="需要提供 prompt_file")
    
    ts_int = int(time.time())
    os.makedirs(download_dir, exist_ok=True)
    src_file_name = get_filename_from_url(prompt_file)
    prompt_file_path = os.path.join(upload_dir, f"prompt_{ts_int}_{src_file_name}")
    
    if download_file(url=prompt_file, destination_path=prompt_file_path) == False:
        return error_response(code=400, message=f"下载 prompt 文件失败")
    
    prompt_wav = load_wav(prompt_file_path, 16000)
    
    tmp = tempfile.NamedTemporaryFile(prefix=f"cross_lingual_{ts_int}_", suffix=".wav", dir=download_dir, delete=False)
    WAV_FILE_PATH = tmp.name
    tmp.close()

    logger.info(f"Received cross_lingual request: input={input_text}")

    _segments = []
    for _, j in enumerate(cosyvoice.inference_cross_lingual(
        input_text,
        prompt_wav,
        stream=False
    )):
        _segments.append(j['tts_speech'])
    
    if len(_segments) == 0:
        return error_response(code=500, message="未生成任何音频数据")
    full_audio = torch.cat(_segments, dim=1)
    torchaudio.save(WAV_FILE_PATH, full_audio, cosyvoice.sample_rate)

    if request.output == "url":
        upload_result = minio_handler.upload_file(file_path=WAV_FILE_PATH)
        if upload_result.get("error"):
            err = upload_result.get("error_str", "upload error")
            logger.error(f"MinIO 上传失败: {err}")
            return error_response(code=500, message=f"MinIO 上传失败: {err}")
        minio_object_path = upload_result.get("minio_put_path")
        minio_download_url = minio_handler.generate_download_url(minio_object_path)
        return success_response(
            data="ok",
            message={
                "audio_url": minio_download_url,
                "minio_path": minio_object_path
            }
        )
    
    def iterfile():
        with open(WAV_FILE_PATH, "rb") as f:
            while chunk := f.read(1024):
                yield chunk
    return StreamingResponse(iterfile(), media_type="audio/wav")

if __name__ == "__main__":
    import uvicorn
    print_routes(app=app)
    uvicorn.run(app='main:app', host="0.0.0.0", port=int(os.getenv("port", 5788)),reload=True)
