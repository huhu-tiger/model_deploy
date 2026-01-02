import os
import io
import base64
import time
import random
import uuid
import sys
from typing import List, Optional

import numpy as np
from pathlib import Path


# 重写提示词
# os.environ['OPENAI_API_KEY'] = 'tk-OvOx9M2qhHxYHcO8SQJdAkFVHVnf1tUD'
# os.environ['OPENAI_BASE_URL'] = 'http://220.181.114.184:30951/compatible-mode/v1'
# os.environ['OPENAI_MODEL'] = 'aliyun/aliyun/qwen-plus'


# os.environ['MODEL_PATH'] = '/media/llm/Qwen-Image'
# os.environ['MODEL_NAME'] = 'Qwen-Image'
# os.environ['HF_HUB_OFFLINE'] = '1'
# os.environ['CUDA_VISIBLE_DEVICES'] = '7'
# os.environ['IMAGE_OUTPUT_DIR'] = os.path.join(os.path.dirname(__file__), 'images_tmp')
# os.environ["IMAGE_DOWNLOAD_URL_PREFIX"] = 'http://39.155.179.5:6002/images'
# os.environ["MINIO_UPLOAD_DIR"] = os.environ.get("MINIO_UPLOAD_DIR", "images")

from PIL import Image

BASE_DIR= os.path.dirname(os.path.abspath(__file__))
# 允许直接导入 prompt_utils_2512.py 中的 rewrite 和生成逻辑
sys.path.append(os.path.join(BASE_DIR, 'service'))
print(f"current Base_Dir: {BASE_DIR}")
from prompt_utils_2512 import rewrite
from generate import generate_image
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi import Request
from fastapi.staticfiles import StaticFiles

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vnet.common.config.env import load_env
load_env(dotenv_path=os.path.join(BASE_DIR, ".env"), override=False) # 加载当前目录下的 .env 文件,要在minio_conn前面加载
from vnet.common.storage.dal.minio.minio_conn import minio_handler


# ----------------------------------
# 配置
# ----------------------------------
model_repo_id = os.environ.get("MODEL_PATH", os.environ.get("MODEL_REPO_ID", "Qwen3-Image-2512"))
MAX_SEED = np.iinfo(np.int32).max
MODEL_NAME = os.environ.get("MODEL_NAME", "Qwen-Image")
DEFAULT_IMAGE_DIR = os.path.join(BASE_DIR, "images_tmp")
IMAGE_OUTPUT_DIR = os.environ.get("IMAGE_OUTPUT_DIR", DEFAULT_IMAGE_DIR)
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", None)
IMAGE_DOWNLOAD_URL_PREFIX = os.environ.get("IMAGE_DOWNLOAD_URL_PREFIX", None)
MINIO_UPLOAD_DIR = os.environ.get("MINIO_UPLOAD_DIR", "qwen3-image-2512")
os.makedirs(IMAGE_OUTPUT_DIR, exist_ok=True)


# ----------------------------------
# OpenAI 兼容的请求/响应模型（按 tech.md）
# ----------------------------------


class MessageContent(BaseModel):
	text: str


class Message(BaseModel):
	role: str
	content: List[MessageContent]


class InputPayload(BaseModel):
	messages: List[Message]


class Parameters(BaseModel):
	negative_prompt: Optional[str] = ""
	prompt_extend: bool = True
	watermark: Optional[bool] = False
	size: Optional[str] = "1024x1024"
	response_format: Optional[str] = "b64_json"
	num_inference_steps: int = Field(default=50, ge=1, le=50)
	guidance_scale: float = 4.0
	seed: Optional[int] = None
	n: int = Field(default=1, ge=1, le=4)
	width: Optional[int] = None
	height: Optional[int] = None
	aspect_ratio: Optional[str] = None


class ImageGenerationRequest(BaseModel):
	model: str
	input: InputPayload
	parameters: Parameters


class ImageContent(BaseModel):
	image: Optional[str] = None
	b64_json: Optional[str] = None


class ChoiceMessage(BaseModel):
	role: str
	content: List[ImageContent]


class Choice(BaseModel):
	finish_reason: str
	message: ChoiceMessage


class TaskMetric(BaseModel):
	FAILED: int
	SUCCEEDED: int
	TOTAL: int


class Usage(BaseModel):
	height: int
	image_count: int
	width: int


class Output(BaseModel):
	choices: List[Choice]
	task_metric: TaskMetric


class ImageGenerationResponse(BaseModel):
	output: Output
	usage: Usage
	request_id: str


# ----------------------------------
# 实用函数
# ----------------------------------

def get_image_size(aspect_ratio: Optional[str], size: Optional[str]) -> (int, int):
	if aspect_ratio:
		if aspect_ratio == "1:1":
			return 1328, 1328
		elif aspect_ratio == "16:9":
			return 1664, 928
		elif aspect_ratio == "9:16":
			return 928, 1664
		elif aspect_ratio == "4:3":
			return 1472, 1140
		elif aspect_ratio == "3:4":
			return 1140, 1472
	# 解析 size，支持 1024x1024 或 1328*1328
	try:
		sz = size.lower().replace("*", "x")
		w, h = sz.split("x")
		return int(w), int(h)
	except Exception:
		return 1024, 1024


def pil_to_b64(image: Image.Image) -> str:
	buf = io.BytesIO()
	image.save(buf, format="PNG")
	b = base64.b64encode(buf.getvalue()).decode("utf-8")
	return b

def save_image(image: Image.Image, output_dir: str) -> str:
	import uuid
	os.makedirs(output_dir, exist_ok=True)
	filename = f"{uuid.uuid4().hex}.png"
	filepath = os.path.join(output_dir, filename)
	image.save(filepath, format="PNG")
	return filename

# ----------------------------------
# FastAPI 应用
# ----------------------------------
app = FastAPI(title="Qwen-Image OpenAI-Compatible API", version="1.0.0")

# 静态文件挂载：用于 URL 返回
os.makedirs(IMAGE_OUTPUT_DIR, exist_ok=True)
app.mount("/images", StaticFiles(directory=IMAGE_OUTPUT_DIR), name="images")

# 在应用启动时初始化一次（放在 app 定义之后，避免未定义引用）


@app.get("/healthz")
async def healthz():
	return {"status": "ok", "model": model_repo_id}


@app.get("/v1/models")
async def list_models():
	return {
		"object": "list",
		"data": [
			{"id": model_repo_id, "object": "model", "created": 0, "owned_by": "owner"}
		]
	}


@app.post("/v1/images/generations", response_model=ImageGenerationResponse)
async def create_image(req: ImageGenerationRequest, request: Request):
	# 校验模型
	accepted_models = {m.lower() for m in [MODEL_NAME, os.environ.get("OPENAI_MODEL", "") if os.environ.get("OPENAI_MODEL") else None] if m}
	if req.model.lower() not in accepted_models:
		raise HTTPException(status_code=400, detail=f"Model not available: {MODEL_NAME}")

	params = req.parameters
	messages = req.input.messages if req.input and req.input.messages else []
	if not messages or not messages[0].content:
		raise HTTPException(status_code=400, detail="Invalid request: missing input.messages.content.text")
	original_prompt = messages[0].content[0].text
	use_rewrite = params.prompt_extend if params.prompt_extend is not None else True
	prompt = rewrite(original_prompt) if use_rewrite else original_prompt

	# 分辨率解析：width/height 优先，其次 size/aspect_ratio
	if params.width and params.height:
		width, height = params.width, params.height
	else:
		width, height = get_image_size(params.aspect_ratio, params.size)

	images: List[Image.Image] = []
	errors: List[str] = []

	base_seed = params.seed if params.seed is not None else random.randint(0, MAX_SEED)

	for i in range(params.n):
		seed_i = base_seed + i
		try:
			img = generate_image(
				model_repo_id,
				prompt,
				params.negative_prompt or "",
				width,
				height,
				params.num_inference_steps,
				params.guidance_scale,
				seed_i,
			)
			images.append(img)
		except Exception as e:
			errors.append(str(e))

	if not images:
		raise HTTPException(status_code=500, detail=f"Inference failed: {'; '.join(errors)}")

	response_format = (params.response_format or "b64_json").lower()
	contents: List[ImageContent] = []
	if response_format == "url":
			for img in images:
				filename = save_image(img, IMAGE_OUTPUT_DIR)
				local_path = os.path.join(IMAGE_OUTPUT_DIR, filename)
				upload = minio_handler.upload_file(local_path, upload_dir=MINIO_UPLOAD_DIR)
				if upload.get("error"):
					errors.append(upload.get("error_str", "upload failed"))
					continue
				download_url = minio_handler.generate_download_url(upload.get("minio_put_path"))
				contents.append(ImageContent(image=download_url))
				try:
					os.remove(local_path)
				except Exception:
					pass
	else:
		for img in images:
			contents.append(ImageContent(b64_json=pil_to_b64(img)))

	choices = [Choice(
		finish_reason="stop",
		message=ChoiceMessage(role="assistant", content=contents),
	)]

	task_metric = TaskMetric(FAILED=len(errors), SUCCEEDED=len(images), TOTAL=params.n)
	usage = Usage(height=height, width=width, image_count=len(images))
	resp = ImageGenerationResponse(
		output=Output(choices=choices, task_metric=task_metric),
		usage=usage,
		request_id=uuid.uuid4().hex,
	)
	return resp


if __name__ == "__main__":

    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=6002, reload=True)