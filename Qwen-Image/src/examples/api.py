import os
import io
import base64
import time
import random
import queue
import threading
from typing import List, Optional

import numpy as np

import os

os.environ['MODEL_PATH'] = '/media/llm/Qwen-Image'
os.environ['MODEL_NAME'] = 'Qwen-Image'
os.environ['OPENAI_API_KEY'] = 'xxx'
os.environ['OPENAI_BASE_URL'] = 'http://192.168.0.3:8002/v1'
os.environ['OPENAI_MODEL'] = 'Qwen3-235B-A22B-Instruct-2507'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['CUDA_VISIBLE_DEVICES'] = '2,6'
os.environ['NUM_GPUS_TO_USE'] = '2'
os.environ['IMAGE_OUTPUT_DIR'] = os.path.join(os.path.dirname(__file__), 'images_tmp')
os.environ["IMAGE_DOWNLOAD_URL_PREFIX"] = 'http://39.155.179.4:6002/images'

import torch
import torch.multiprocessing as mp
from multiprocessing import Process, Queue, Event
from diffusers import DiffusionPipeline
from PIL import Image

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi import Request
from fastapi.staticfiles import StaticFiles

# 为多进程确保兼容性
mp.set_start_method('spawn', force=True)

# ----------------------------------
# 配置
# ----------------------------------
model_repo_id = os.environ.get("MODEL_PATH", os.environ.get("MODEL_REPO_ID", "Qwen-Image"))
MAX_SEED = np.iinfo(np.int32).max
MODEL_NAME = os.environ.get("MODEL_NAME", "Qwen-Image")
NUM_GPUS_TO_USE = int(os.environ.get("NUM_GPUS_TO_USE", torch.cuda.device_count()))
TASK_QUEUE_SIZE = int(os.environ.get("TASK_QUEUE_SIZE", 100))
TASK_TIMEOUT = int(os.environ.get("TASK_TIMEOUT", 300))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_IMAGE_DIR = os.path.join(BASE_DIR, "images_tmp")
IMAGE_OUTPUT_DIR = os.environ.get("IMAGE_OUTPUT_DIR", DEFAULT_IMAGE_DIR)
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", None)
IMAGE_DOWNLOAD_URL_PREFIX = os.environ.get("IMAGE_DOWNLOAD_URL_PREFIX", None)
os.makedirs(IMAGE_OUTPUT_DIR, exist_ok=True)

# 文本重写工具（可选）
try:
	from examples.tools.prompt_utils import rewrite
except Exception:
	def rewrite(x: str) -> str:
		return x

print(f"Config: Model '{model_repo_id}', Using GPU NUMS {torch.cuda.device_count()}, Using {NUM_GPUS_TO_USE} GPUs, queue size {TASK_QUEUE_SIZE}, timeout {TASK_TIMEOUT} seconds")

# ----------------------------------
# 多 GPU Worker 与管理器（参考 demo.py，移除 Gradio 依赖）
# ----------------------------------
class GPUWorker:
	def __init__(self, gpu_id, model_repo_id, task_queue, result_queue, stop_event):
		self.gpu_id = gpu_id
		self.model_repo_id = model_repo_id
		self.task_queue = task_queue
		self.result_queue = result_queue
		self.stop_event = stop_event
		self.device = f"cuda:{gpu_id}" if torch.cuda.is_available() else "cpu"
		self.pipe = None

	def initialize_model(self):
		try:
			if torch.cuda.is_available():
				torch.cuda.set_device(self.gpu_id)
				torch_dtype = torch.bfloat16
			else:
				torch_dtype = torch.float32

			self.pipe = DiffusionPipeline.from_pretrained(self.model_repo_id, torch_dtype=torch_dtype)
			self.pipe = self.pipe.to(self.device)
			print(f"GPU {self.gpu_id} model initialized successfully")
			return True
		except Exception as e:
			print(f"GPU {self.gpu_id} model initialization failed: {e}")
			return False

	def process_task(self, task):
		try:
			task_id = task['task_id']
			prompt = task['prompt']
			negative_prompt = task.get('negative_prompt', "")
			seed = task['seed']
			width = task['width']
			height = task['height']
			guidance_scale = task['guidance_scale']
			num_inference_steps = task['num_inference_steps']

			def step_callback(pipe, i, t, callback_kwargs):
				return callback_kwargs

			generator = torch.Generator(device=self.device)
			if seed is not None:
				generator = generator.manual_seed(seed)

			# 进行推理
			if torch.cuda.is_available():
				with torch.cuda.device(self.gpu_id):
					image = self.pipe(
						prompt=prompt,
						negative_prompt=negative_prompt,
						true_cfg_scale=guidance_scale,
						num_inference_steps=num_inference_steps,
						width=width,
						height=height,
						generator=generator,
						callback_on_step_end=step_callback
					).images[0]
			else:
				image = self.pipe(
					prompt=prompt,
					negative_prompt=negative_prompt,
					true_cfg_scale=guidance_scale,
					num_inference_steps=num_inference_steps,
					width=width,
					height=height,
					generator=generator,
					callback_on_step_end=step_callback
				).images[0]

			return {
				'task_id': task_id,
				'image': image,
				'success': True,
				'gpu_id': self.gpu_id
			}
		except Exception as e:
			return {
				'task_id': task_id,
				'success': False,
				'error': str(e),
				'gpu_id': self.gpu_id
			}

	def run(self):
		if not self.initialize_model():
			return
		print(f"GPU {self.gpu_id} worker starting")
		while not self.stop_event.is_set():
			try:
				task = self.task_queue.get(timeout=1)
				if task is None:
					break
				result = self.process_task(task)
				self.result_queue.put(result)
			except queue.Empty:
				continue
			except Exception as e:
				print(f"GPU {self.gpu_id} worker exception: {e}")
				continue
		print(f"GPU {self.gpu_id} worker stopping")


def gpu_worker_process(gpu_id, model_repo_id, task_queue, result_queue, stop_event):
	worker = GPUWorker(gpu_id, model_repo_id, task_queue, result_queue, stop_event)
	worker.run()


class MultiGPUManager:
	def __init__(self, model_repo_id, num_gpus=None, task_queue_size=100):
		self.model_repo_id = model_repo_id
		self.num_gpus = num_gpus or torch.cuda.device_count()
		self.task_queue = Queue(maxsize=task_queue_size)
		self.result_queue = Queue()
		self.stop_event = Event()
		self.worker_processes = []
		self.task_counter = 0
		self.pending_tasks = {}
		print(f"Initializing Multi-GPU Manager with {self.num_gpus} GPUs, queue size {task_queue_size}")

	def start_workers(self):
		for gpu_id in range(self.num_gpus):
			process = Process(target=gpu_worker_process,
							args=(gpu_id, self.model_repo_id, self.task_queue,
								  self.result_queue, self.stop_event))
			process.start()
			self.worker_processes.append(process)

		self.result_thread = threading.Thread(target=self._process_results)
		self.result_thread.daemon = True
		self.result_thread.start()
		print(f"All {self.num_gpus} GPU workers have started")

	def _process_results(self):
		while not self.stop_event.is_set():
			try:
				result = self.result_queue.get(timeout=1)
				task_id = result['task_id']
				if task_id in self.pending_tasks:
					self.pending_tasks[task_id]['result'] = result
					self.pending_tasks[task_id]['event'].set()
			except queue.Empty:
				continue
			except Exception as e:
				print(f"Result processing thread exception: {e}")
				continue

	def submit_task(self, prompt, negative_prompt="", seed=42, width=1024, height=1024,
					guidance_scale=4.0, num_inference_steps=50, timeout=300):
		return self.submit_task_with_progress(prompt, negative_prompt, seed, width, height,
												guidance_scale, num_inference_steps, timeout)

	def submit_task_with_progress(self, prompt, negative_prompt="", seed=42, width=1024, height=1024,
											guidance_scale=4.0, num_inference_steps=50, timeout=300):
		task_id = f"task_{self.task_counter}_{time.time()}"
		self.task_counter += 1

		task = {
			'task_id': task_id,
			'prompt': prompt,
			'negative_prompt': negative_prompt,
			'seed': seed,
			'width': width,
			'height': height,
			'guidance_scale': guidance_scale,
			'num_inference_steps': num_inference_steps,
		}

		result_event = threading.Event()
		self.pending_tasks[task_id] = {
			'event': result_event,
			'result': None,
			'submitted_time': time.time()
		}

		try:
			self.task_queue.put(task, timeout=10)
			start_time = time.time()
			while not result_event.is_set():
				if result_event.wait(timeout=1):
					break
				if time.time() - start_time > timeout:
					del self.pending_tasks[task_id]
					return {'success': False, 'error': 'Task timeout'}
			result = self.pending_tasks[task_id]['result']
			del self.pending_tasks[task_id]
			return result
		except queue.Full:
			del self.pending_tasks[task_id]
			return {'success': False, 'error': 'Task queue is full'}
		except Exception as e:
			if task_id in self.pending_tasks:
				del self.pending_tasks[task_id]
			return {'success': False, 'error': str(e)}

	def get_queue_status(self):
		return {
			'task_queue_size': self.task_queue.qsize(),
			'result_queue_size': self.result_queue.qsize(),
			'pending_tasks': len(self.pending_tasks),
			'active_workers': len(self.worker_processes)
		}

	def stop(self):
		print("Stopping Multi-GPU Manager...")
		self.stop_event.set()
		for _ in range(self.num_gpus):
			try:
				self.task_queue.put(None, timeout=1)
			except queue.Full:
				pass
		for process in self.worker_processes:
			process.join(timeout=5)
			if process.is_alive():
				process.terminate()
		print("Multi-GPU Manager has stopped")




def initialize_gpu_manager():
	global gpu_manager
	if gpu_manager is None:
		try:
			if torch.cuda.is_available():
				print(f"Detected {torch.cuda.device_count()} GPUs")
			gpu_manager = MultiGPUManager(
				model_repo_id,
				num_gpus=NUM_GPUS_TO_USE,
				task_queue_size=TASK_QUEUE_SIZE
			)
			gpu_manager.start_workers()
			print("GPU Manager initialized successfully")
		except Exception as e:
			print(f"GPU Manager initialization failed: {e}")
			gpu_manager = None



gpu_manager = None
_gpu_init_lock = threading.Lock()
_gpu_initialized = False

# ----------------------------------
# OpenAI 兼容的请求/响应模型
# ----------------------------------
class ImageGenerationRequest(BaseModel):
	model: Optional[str] = Field(default=None, description="模型名，默认为环境变量配置")
	prompt: str = Field(..., description="生成提示词")
	n: int = Field(default=1, ge=1, le=4, description="返回图片数量（最多 4）")
	size: Optional[str] = Field(default="1024x1024", description="OpenAI 规格的尺寸，如 256x256 / 512x512 / 1024x1024")
	response_format: Optional[str] = Field(default="b64_json", description="返回格式：b64_json")
	user: Optional[str] = None

	# 扩展参数（非 OpenAI 标准，但保持兼容）
	negative_prompt: Optional[str] = ""
	seed: Optional[int] = None
	guidance_scale: float = 4.0
	num_inference_steps: int = Field(default=50, ge=1, le=50)
	aspect_ratio: Optional[str] = Field(default=None, description="可选：1:1, 16:9, 9:16, 4:3, 3:4。若提供将覆盖 size")
'''
扩展参数（非 OpenAI 标准，但保持兼容；均已在接口中支持）：
negative_prompt: 负向提示词，用于抑制不希望出现的元素或风格，例如 "blurry, low quality, watermark"。
seed: 随机种子。设定后可复现结果；当 n>1 时，内部会使用 seed+i 生成第 i 张图。未设定则随机。
guidance_scale: 文本引导强度（对应管线的 true_cfg_scale）。数值越大越贴近 prompt，但可能更生硬或产生伪影；建议 3.0–6.0，默认 4.0。
num_inference_steps: 采样步数。步数越多通常越细致，但越慢；建议 30–50，默认 50，上限 50。
aspect_ratio: 宽高比快捷选项，提供固定分辨率映射，若设置将覆盖 size：
"1:1" → 1328x1328
"16:9" → 1664x928
"9:16" → 928x1664
"4:3" → 1472x1140
"3:4" → 1140x1472
'''



class ImageData(BaseModel):
	b64_json: Optional[str] = None
	url: Optional[str] = None


class ImageGenerationResponse(BaseModel):
	created: int
	data: List[ImageData]


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
	# 解析 OpenAI 的 size（默认 1024x1024）
	try:
		w, h = size.lower().split("x")
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
@app.on_event("startup")
async def _startup_init_gpu_manager():
	global gpu_manager, _gpu_initialized
	with _gpu_init_lock:
		if not _gpu_initialized and gpu_manager is None:
			initialize_gpu_manager()
			_gpu_initialized = gpu_manager is not None


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
	# 处理参数
	model_id = req.model
	if model_id.lower() != MODEL_NAME.lower():
		# 简单校验：仅允许当前模型
		raise HTTPException(status_code=400, detail=f"Model not available: {MODEL_NAME}")

	width, height = get_image_size(req.aspect_ratio, req.size)
	original_prompt = req.prompt
	prompt = rewrite(req.prompt)

	images: List[Image.Image] = []
	errors: List[str] = []

	base_seed = req.seed if req.seed is not None else random.randint(0, MAX_SEED)

	for i in range(req.n):
		seed_i = base_seed + i
		result = gpu_manager.submit_task(
			prompt=prompt,
			negative_prompt=req.negative_prompt or "",
			seed=seed_i,
			width=width,
			height=height,
			guidance_scale=req.guidance_scale,
			num_inference_steps=req.num_inference_steps,
			timeout=TASK_TIMEOUT,
		)
		if result.get('success'):
			images.append(result['image'])
		else:
			errors.append(result.get('error', 'unknown error'))

	if not images:
		raise HTTPException(status_code=500, detail=f"Inference failed: {'; '.join(errors)}")

	# 根据 response_format 返回 b64 或 URL
	if (req.response_format or "b64_json").lower() == "url":
		# 生成可访问 URL
		base = PUBLIC_BASE_URL.rstrip('/') + '/' if PUBLIC_BASE_URL else str(request.base_url)
		if not base.endswith('/'):
			base += '/'
		urls: List[ImageData] = []
		for img in images:
			filename = save_image(img, IMAGE_OUTPUT_DIR)
			urls.append(ImageData(url=f"{IMAGE_DOWNLOAD_URL_PREFIX}/{filename}"))
		return ImageGenerationResponse(created=int(time.time()), data=urls)
	else:
		data_items = [ImageData(b64_json=pil_to_b64(img)) for img in images]
		return ImageGenerationResponse(created=int(time.time()), data=data_items)


@app.on_event("shutdown")
async def on_shutdown():
	global gpu_manager
	if gpu_manager:
		gpu_manager.stop()

if __name__ == "__main__":

    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=6002, reload=True)