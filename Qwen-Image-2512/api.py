import os
import io
import base64
import time
import random
import uuid
import sys
from typing import List, Optional, Tuple

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
from vnet.common.storage.dal.minio.minio_userpass import MinioApiUploader, MinioSettings


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

# 初始化 MinIO 上传器
minio_settings = MinioSettings()
minio_handler = MinioApiUploader(
	endpoint=f"{minio_settings.Minio_IP}:{minio_settings.Minio_Upload_Port}",
	username=minio_settings.Minio_Root_User,
	password=minio_settings.Minio_Root_Password,
	bucket_name=minio_settings.Minio_Bucket_Name,
	download_base_url=minio_settings.Minio_Upload_Url,
	api_path=minio_settings.Minio_Api_Path,
)


# ----------------------------------
# 阿里云百炼兼容的请求/响应模型
# ----------------------------------


class ContentItem(BaseModel):
	text: Optional[str] = None
	image_url: Optional[str] = None


class Message(BaseModel):
	role: str
	content: List[ContentItem]


class InputPayload(BaseModel):
	prompt: Optional[str] = Field(default=None, max_length=800, description="文本描述，最多800字符")
	messages: Optional[List[Message]] = Field(default=None, description="消息列表（支持阿里云格式）")
	negative_prompt: Optional[str] = Field(default="", max_length=500, description="反向提示词，最多500字符")
	ref_image: Optional[str] = Field(default=None, description="参考图片URL（暂不支持）")


class Parameters(BaseModel):
	style: Optional[str] = Field(default="<auto>", description="图像风格（暂不支持）")
	size: Optional[str] = Field(default="1024*1024", description="图像尺寸，格式：宽*高")
	n: int = Field(default=1, ge=1, le=4, description="生成图片数量，1-4")
	seed: Optional[int] = Field(default=None, ge=0, le=2147483647, description="随机种子")
	ref_strength: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="参考图强度（暂不支持）")
	ref_mode: Optional[str] = Field(default="repaint", description="参考模式（暂不支持）")
	negative_prompt: Optional[str] = Field(default="", max_length=500, description="反向提示词，最多500字符")
	watermark: Optional[bool] = Field(default=False, description="是否添加水印")
	# 内部参数（非阿里云标准，用于兼容现有实现）
	prompt_extend: Optional[bool] = Field(default=True, description="是否扩展提示词（内部参数）")
	num_inference_steps: Optional[int] = Field(default=50, ge=1, le=50, description="推理步数（内部参数）")
	guidance_scale: Optional[float] = Field(default=4.0, description="引导系数（内部参数）")
	response_format: Optional[str] = Field(default="url", description="返回格式：url 或 b64_json（内部参数）")


class ImageGenerationRequest(BaseModel):
	model: str
	input: InputPayload
	parameters: Optional[Parameters] = Field(default_factory=Parameters)


class ImageContent(BaseModel):
	image: Optional[str] = None


class MessageContent(BaseModel):
	content: List[ImageContent]
	role: str = "assistant"


class Choice(BaseModel):
	finish_reason: str = "stop"
	message: MessageContent


class TaskMetric(BaseModel):
	TOTAL: int
	SUCCEEDED: int
	FAILED: int


class OutputPayload(BaseModel):
	choices: List[Choice]
	task_metric: TaskMetric


class Usage(BaseModel):
	image_count: int
	width: int
	height: int


class ImageGenerationResponse(BaseModel):
	output: OutputPayload
	usage: Usage
	request_id: str


# ----------------------------------
# 实用函数
# ----------------------------------

def get_image_size(size: Optional[str]) -> Tuple[int, int]:
	"""解析阿里云格式的尺寸字符串，如 1024*1024"""
	if not size:
		return 1024, 1024
	try:
		# 支持 1024*1024 或 1024x1024 格式
		sz = size.replace("x", "*")
		w, h = sz.split("*")
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


@app.on_event("startup")
async def startup_event():
	"""应用启动时预加载模型和登录 MinIO"""
	# 登录 MinIO
	print("正在登录 MinIO...")
	if minio_handler.login():
		print("MinIO 登录成功")
	else:
		print("MinIO 登录失败，请检查配置")

	# 加载模型
	print(f"正在加载模型: {model_repo_id}")
	try:
		# 调用一次 generate_image 触发模型加载
		from generate import _get_pipe
		_get_pipe(model_repo_id)
		print(f"模型加载完成: {model_repo_id}")
	except Exception as e:
		print(f"模型加载失败: {e}")
		import traceback
		traceback.print_exc()


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


@app.post("/api/v1/services/aigc/text2image/image-synthesis", response_model=ImageGenerationResponse)
async def create_image(req: ImageGenerationRequest, request: Request):
	"""
	阿里云百炼兼容的文生图接口

	支持的参数：
	- model: 模型名称
	- input.prompt: 文本描述（必填）
	- input.negative_prompt: 反向提示词
	- parameters.size: 图像尺寸（格式：宽*高）
	- parameters.n: 生成数量（1-4）
	- parameters.seed: 随机种子
	- parameters.response_format: 返回格式（url/b64_json，内部参数）

	暂不支持的参数：
	- input.ref_image: 参考图片（需要图像编辑模型支持）
	- parameters.style: 图像风格（当前模型不支持风格控制）
	- parameters.ref_strength: 参考图强度（需要参考图支持）
	- parameters.ref_mode: 参考模式（需要参考图支持）
	"""
	# 校验模型
	accepted_models = {m.lower() for m in [MODEL_NAME, os.environ.get("OPENAI_MODEL", "") if os.environ.get("OPENAI_MODEL") else None] if m}
	if req.model.lower() not in accepted_models:
		raise HTTPException(status_code=400, detail=f"Model not available: {req.model}")

	# 检查不支持的参数
	if req.input.ref_image:
		raise HTTPException(status_code=400, detail="参数 ref_image 暂不支持，需要图像编辑模型")

	params = req.parameters or Parameters()

	# 获取提示词 - 支持两种格式
	original_prompt = None
	if req.input.prompt:
		original_prompt = req.input.prompt
	elif req.input.messages:
		# 从 messages 中提取 text
		for msg in req.input.messages:
			if msg.role == "user" and msg.content:
				for item in msg.content:
					if item.text:
						original_prompt = item.text
						break
				if original_prompt:
					break

	if not original_prompt:
		raise HTTPException(status_code=400, detail="Invalid request: missing input.prompt or input.messages with text content")

	# 获取 negative_prompt - 优先从 input 获取，其次从 parameters 获取
	negative_prompt = req.input.negative_prompt or params.negative_prompt or ""

	use_rewrite = params.prompt_extend if params.prompt_extend is not None else True
	prompt = rewrite(original_prompt) if use_rewrite else original_prompt

	# 解析尺寸
	width, height = get_image_size(params.size)

	# 生成图像
	images: List[Image.Image] = []
	errors: List[str] = []

	base_seed = params.seed if params.seed is not None else random.randint(0, MAX_SEED)

	for i in range(params.n):
		seed_i = base_seed + i
		try:
			img = generate_image(
				model_repo_id,
				prompt,
				negative_prompt,
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

	# 处理返回格式
	response_format = (params.response_format or "url").lower()
	choices: List[Choice] = []

	if response_format == "url":
		for img in images:
			filename = save_image(img, IMAGE_OUTPUT_DIR)
			local_path = os.path.join(IMAGE_OUTPUT_DIR, filename)
			upload = minio_handler.upload_file(local_path, upload_dir=MINIO_UPLOAD_DIR)
			if upload.get("error"):
				errors.append(upload.get("error_str", "upload failed"))
				continue
			# MinioApiUploader 直接返回 download_url
			download_url = upload.get("download_url")

			# 构造 choice
			choice = Choice(
				finish_reason="stop",
				message=MessageContent(
					content=[ImageContent(image=download_url)],
					role="assistant"
				)
			)
			choices.append(choice)

			try:
				os.remove(local_path)
			except Exception:
				pass
	else:
		# b64_json 格式暂不支持新格式，保持原有逻辑
		for img in images:
			choice = Choice(
				finish_reason="stop",
				message=MessageContent(
					content=[ImageContent(image=f"data:image/png;base64,{pil_to_b64(img)}")],
					role="assistant"
				)
			)
			choices.append(choice)

	# 构造阿里云格式的响应
	task_metric = TaskMetric(
		TOTAL=params.n,
		SUCCEEDED=len(images),
		FAILED=len(errors)
	)

	output = OutputPayload(
		choices=choices,
		task_metric=task_metric
	)

	usage = Usage(
		image_count=len(images),
		width=width,
		height=height
	)

	resp = ImageGenerationResponse(
		output=output,
		usage=usage,
		request_id=uuid.uuid4().hex,
	)
	return resp


if __name__ == "__main__":

    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=6002, reload=True)