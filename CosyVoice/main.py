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
from cosyvoice.cli.cosyvoice import CosyVoice, CosyVoice2
from cosyvoice.utils.file_utils import load_wav
from cosyvoice.utils.common import set_all_random_seed


import torch
import torchaudio
import ffmpeg

from app.response import error_response,success_response
from app.schemas import ChatCompletionRequest, TTSCloneRequest, TTSCloneDelRequest, TTSCloneSpkRequest
from app.utils import get_filename_from_url, download_file


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(BASE_DIR))

from vnet.common.config.env import load_env
load_env(dotenv_path=os.path.join(BASE_DIR, ".env"), override=False)

from vnet.common.storage.dal.minio.minio_conn import minio_handler
from vnet.common.tools.http_utils import multiple_download_async

# gpu使用
os.environ["CUDA_VISIBLE_DEVICES"] = "7"


# 模型加载
cosyvoice = CosyVoice2('/media/source/CosyVoice/pretrained_models/CosyVoice2-0.5B')


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




# def stream_sft():
#     # question_data = request.get_json()
#     tts_text = request.form.get('query')
#     speaker = request.form.get('speaker')


# @app.post("/v1/audio/speech")
# async def chat_completion(request: ChatCompletionRequest):
#     try:
#         logger.info(f"Received request: {request}")
#         timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")

#         # 提取所有传入的参数并将其存储到单独的变量中
#         model = request.model
#         input_text = request.input
#         voice = request.voice
#         response_format = request.response_format
#         sample_rate = request.sample_rate
#         stream = request.stream
#         speed = request.speed
#         gain = request.gain
        

#         wav_file_path = os.path.join(download_dir,f"{timestamp}.wav")
#         # 记录所有提取的参数
#         logger.info(f"Received request with parameters: "
#                     f"model={model}, input={input_text}, voice={voice}, "
#                     f"response_format={response_format}, sample_rate={sample_rate}, "
#                     f"stream={stream}, speed={speed}, gain={gain}")


#         for i, j in enumerate(cosyvoice_sft.inference_sft(input_text, voice, stream=False)):
#             torchaudio.save(wav_file_path, j['tts_speech'], cosyvoice.sample_rate)

#         # 流输出
#         # https://blog.csdn.net/u010522887/article/details/144899524
#         # https://cnloong.blog.csdn.net/article/details/140514102
#         def iter_wav_file(chunk_size: int = 1024):
#             # 采用 wave 读取可以保证只读 data 部分
#             with wave.open(wav_file_path, "rb") as wf:
#                 # 先把头部 RIFF+fmt chunk 读出
#                 wf.rewind()
#                 header = wf.readframes(0)  # wave.open 会在内部读出 header
#                 # 但 wave 模块并不提供直接获取 header bytes，
#                 # 所以最简单：用 open 先读 header 区，再读 data
#             with open(wav_file_path, "rb") as f:
#                 # 先读整个文件头（假设 data chunk 紧跟在 header 后）
#                 # 直接按 44 字节（标准 PCM WAV 头部长度）来划
#                 header_bytes = f.read(44)
#                 yield header_bytes
#                 # 然后逐块读 data
#                 chunk = f.read(chunk_size)
#                 while chunk:
#                     yield chunk
#                     chunk = f.read(chunk_size)

#         file_size = os.path.getsize(wav_file_path)
#         headers = {"Content-Length": str(file_size)}

#         return StreamingResponse(
#             iter_wav_file(),
#             media_type="audio/wav",
#             headers=headers
#         )


#         # def iterfile():
#         #     with open(wav_file_path, "rb") as f:
#         #         while chunk := f.read(1024):  # 逐块读取文件，每次读取 1024 字节
#         #             yield chunk

#         # return StreamingResponse(iterfile(), media_type="audio/wav")
#     except Exception as e:
#         logger.error(f"错误: {e}")
#         return error_response(code=500, data="接口调用失败")





# async def generate_audio(request: ChatCompletionRequest):
#     '''音频生成函数'''
#     set_all_random_seed(request.seed if request.seed else 0)

#     inference_map = {
#         'zero_shot': cosyvoice.inference_zero_shot,
#         'instruct': cosyvoice.inference_instruct2,
#         # 'sft': cosyvoice.inference_sft
#         'sft':  cosyvoice.inference_zero_shot
#     }

#     if request.mode not in inference_map:
#         raise HTTPException(status_code=400, detail="Invalid mode")

#     args = None

#     if request.mode == 'sft':
#         # args = (request.tts_text, request.sft_dropdown, request.stream, request.speed)
#         # print(request.sft_dropdown)
#         args = (request.input, '', '',request.voice, True)
#         # elif request.mode == 'zero_shot':
#         #     # args = (request.tts_text, request.prompt_text, prompt_speech_16k, request.stream, request.speed)
#         #     args = ('收到好友从远方寄来的生日礼物，真的那份意外的惊喜与深深的祝福让我心中充满了甜蜜的快乐，笑容如花儿般绽放。', '希望你以后能够做的比我还好呦。', prompt_speech_16k,'', True)
#         # elif request.mode == 'instruct':
#         #     args = (request.tts_text, request.instruct_text, prompt_speech_16k, request.stream, request.speed)
    
#     try:
#         result = await asyncio.to_thread(inference_map[request.mode], *args)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Audio generation error: {str(e)}")

#     if result is None:
#         raise HTTPException(status_code=500, detail="Failed to generate audio")
    
#     return result

# async def generate_audio_stream(request: ChatCompletionRequest):
#     result = await generate_audio(request)

#     # 构建 WAV 头部
#     with io.BytesIO() as header_buffer:
#         with wave.open(header_buffer, 'wb') as wav_file:
#             wav_file.setnchannels(1)  # 单声道
#             wav_file.setsampwidth(2)  # 16-bit PCM
#             wav_file.setframerate(cosyvoice.sample_rate)  # 采样率

#             for i in result:
#                 audio_data = i['tts_speech'].numpy().flatten()
#                 audio_bytes = (audio_data * (2**15)).astype(np.int16).tobytes()

#                 # 写入数据到内存文件
#                 wav_file.writeframes(audio_bytes)

#         # 获取完整的 WAV 文件二进制数据
#         wav_data = header_buffer.getvalue()

#     # 分块输出
#     chunk_size = 4096
#     for i in range(0, len(wav_data), chunk_size):
#         yield wav_data[i:i + chunk_size]

# async def generate_audio_buffer(request: ChatCompletionRequest):
#     '''非流式处理，返回音频数据流'''
#     result = await generate_audio(request)
#     buffer = io.BytesIO()
#     audio_data = torch.cat([j['tts_speech'] for j in result], dim=1)
#     torchaudio.save(buffer, audio_data, cosyvoice.sample_rate, format="wav")
#     buffer.seek(0)
#     return buffer


# 音色克隆流输出
# @app.post("/tts_clone/stream")
# async def tts_stream(request: ChatCompletionRequest):
#     input_text = request.input
#     voice = request.voice
#     if request.stream:
#         # 流式输出
#         return StreamingResponse(generate_audio_stream(request), media_type="audio/wav")
#     else:
#         # 非流式输出
#         buffer = await generate_audio_buffer(request)
#         return Response(buffer.read(), media_type="audio/wav")
    

# 音色列表
@app.get("/tts_clone/spk/list")
def tts_spk_list():

    voices = cosyvoice.list_available_spks()
    logger.info(f"音色克隆已上传voice:{cosyvoice.list_available_spks()}")
    return success_response(data=voices)


# 音色创建
@app.post("/tts_clone/spk/create")
async def tts1(request: TTSCloneSpkRequest):

    input_text = request.input
    voice_name = request.voice_name
    voice_id = voice_name + "_" +str(random.randint(1000, 9999))
    voice_file = request.voice_file
    src_file_name = get_filename_from_url(voice_file)

    voice_file_path = os.path.join(upload_dir,src_file_name)

    if download_file(url=voice_file, destination_path=voice_file_path) == False:
        return error_response(code=400,message=f"下载音色文件失败")

    logger.info(f"spk downlaod_file:{voice_file_path}")
    logger.info(f"voice_name: {voice_name},voice_id:{voice_id}")
    prompt_speech_16k = load_wav(voice_file_path, 16000)
    try:
        assert cosyvoice.add_zero_shot_spk(input_text, prompt_speech_16k, voice_id) is True
        cosyvoice.save_spkinfo()
        return success_response(data="ok",message={"voice_id":voice_id,"list_spks":cosyvoice.list_available_spks()})
    except Exception as e:
        logger.error(f"上传音色失败: {e}")
        return error_response(code=400,message=f"上传音色失败: {e}")



# 音色删除
@app.post("/tts_clone/spk/delete")
async def tts1(request: TTSCloneDelRequest):

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



# 音色克隆
@app.post("/tts_clone/spk/gen")
async def tts1(request: TTSCloneRequest):

    input_text = request.input
    # voice = request.voice
    voice_id = request.voice_id
    voices = cosyvoice.list_available_spks()
    print(voices)
    if voice_id not in voices:
        return error_response(code=400,message=f"音色不存在: {voice_id}")
    ts_int = int(time.time())
    os.makedirs(download_dir, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(prefix=f"{voice_id}_{ts_int}_", suffix=".wav", dir=download_dir, delete=False)
    WAV_FILE_PATH = tmp.name
    tmp.close()

        # 记录所有提取的参数
    logger.info(f"Received request with parameters: {request}")

    # 收集分段音频并一次性保存，避免覆盖只保留最后一段
    _segments = []
    for _, j in enumerate(cosyvoice.inference_zero_shot(input_text, '', '', zero_shot_spk_id=voice_id, stream=False)):
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





if __name__ == "__main__":
    import uvicorn
    print_routes(app=app)
    uvicorn.run(app='main:app', host="0.0.0.0", port=int(os.getenv("port", 5788)),reload=True)