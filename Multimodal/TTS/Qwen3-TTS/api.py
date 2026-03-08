import asyncio
import os
import time
import uuid
from pathlib import Path
from typing import List, Literal, Optional, Union

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vnet.common.config.env import load_env

from services.base_voice_clone_service import synthesize_voice_clone_to_minio
from services.custom_voice_service import synthesize_custom_voice_to_minio
from services.voice_design_service import synthesize_voice_design_to_minio

BASE_DIR = Path(__file__).resolve().parent
load_env(dotenv_path=BASE_DIR / ".env", override=False)


MODEL_ID = os.environ.get("TTS_MODEL_ID", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")
MODEL_PATH = os.environ.get("TTS_MODEL_PATH", MODEL_ID)
BASE_MODEL_ID = os.environ.get("TTS_BASE_MODEL_ID", "Qwen/Qwen3-TTS-12Hz-1.7B-Base")
BASE_MODEL_PATH = os.environ.get("TTS_BASE_MODEL_PATH", BASE_MODEL_ID)
VOICE_DESIGN_MODEL_ID = os.environ.get("TTS_VOICE_DESIGN_MODEL_ID", "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign")
VOICE_DESIGN_MODEL_PATH = os.environ.get("TTS_VOICE_DESIGN_MODEL_PATH", VOICE_DESIGN_MODEL_ID)
DEFAULT_VOICE = os.environ.get("TTS_DEFAULT_VOICE", "Vivian")
DEFAULT_LANGUAGE = os.environ.get("TTS_DEFAULT_LANGUAGE", "Chinese")
DEVICE = os.environ.get("TTS_DEVICE", "cuda:0" if torch.cuda.is_available() else "cpu")
DTYPE_STR = os.environ.get("TTS_DTYPE", "bfloat16" if DEVICE.startswith("cuda") else "float32")
ATTN_IMPL = os.environ.get("TTS_ATTN_IMPL", "flash_attention_2")
OUTPUT_DIR = Path(os.environ.get("TTS_OUTPUT_DIR", BASE_DIR / "outputs"))
MINIO_UPLOAD_DIR = os.environ.get("TTS_MINIO_UPLOAD_DIR", "qwen3-tts")

app = FastAPI(title="Qwen3-TTS OpenAI-Compatible API", version="1.0.0")


class SpeechRequest(BaseModel):
	model: str = Field(default=MODEL_ID, description="Model id or local path")
	input: str = Field(..., min_length=1, description="Text to synthesize")
	voice: str = Field(default=DEFAULT_VOICE, description="Speaker identifier")
	language: str = Field(default=DEFAULT_LANGUAGE, description="Language hint")
	instruct: Optional[str] = Field(default="", description="Style instruction")
	response_format: Literal["url", "wav", "flac"] = Field(default="url")
	stream: bool = Field(default=False, description="Streaming is not supported yet")
	max_new_tokens: Optional[int] = Field(default=None, gt=0, description="Optional generation limit")


class AudioContent(BaseModel):
	audio: str
	format: str
	minio_path: str
	duration: float


class ChoiceMessage(BaseModel):
	role: str = "assistant"
	content: List[AudioContent]


class AudioChoice(BaseModel):
	index: int
	finish_reason: str
	message: ChoiceMessage


class TaskMetric(BaseModel):
	FAILED: int
	SUCCEEDED: int
	TOTAL: int


class AudioOutput(BaseModel):
	choices: List[AudioChoice]
	task_metric: TaskMetric


class AudioUsage(BaseModel):
	duration: float
	input_length: int


class AudioSpeechResponse(BaseModel):
	id: str
	object: str
	created: int
	model: str
	voice: str
	output: AudioOutput
	usage: AudioUsage
	request_id: str


class VoiceDesignRequest(BaseModel):
	model: str = Field(default=VOICE_DESIGN_MODEL_ID, description="VoiceDesign model id or path")
	input: str = Field(..., min_length=1, description="Text to synthesize")
	language: str = Field(default=DEFAULT_LANGUAGE, description="Language hint")
	instruct: Optional[str] = Field(default="", description="Voice design instruction")
	response_format: Literal["url", "wav", "flac"] = Field(default="url")
	stream: bool = Field(default=False, description="Streaming is not supported yet")
	max_new_tokens: Optional[int] = Field(default=None, gt=0, description="Optional generation limit")


class AudioVoiceDesignResponse(BaseModel):
	id: str
	object: str
	created: int
	model: str
	output: AudioOutput
	usage: AudioUsage
	request_id: str


class VoiceCloneRequest(BaseModel):
	model: str = Field(default=BASE_MODEL_ID, description="Base model id or local path")
	input: str = Field(..., min_length=1, description="Text to synthesize")
	language: str = Field(default="Auto", description="Language hint")
	ref_audio: Union[str, List[str]] = Field(..., description="Reference audio: URL/local path/base64, or list")
	ref_text: Optional[Union[str, List[Optional[str]]]] = Field(
		default=None,
		description="Reference transcript(s). Required when x_vector_only_mode=False (ICL).",
	)
	x_vector_only_mode: Union[bool, List[bool]] = Field(
		default=False,
		description="True: speaker embedding only; False: ICL mode (requires ref_text).",
	)
	response_format: Literal["url", "wav", "flac"] = Field(default="url")
	stream: bool = Field(default=False, description="Streaming is not supported yet")
	max_new_tokens: Optional[int] = Field(default=None, gt=0, description="Optional generation limit")


@app.get("/healthz")
async def healthz():
	return {"status": "ok", "model": MODEL_ID}


@app.get("/v1/models")
async def list_models():
	return {
		"object": "list",
		"data": [
			{"id": MODEL_ID, "object": "model", "created": 0, "owned_by": "owner"},
			{"id": BASE_MODEL_ID, "object": "model", "created": 0, "owned_by": "owner"},
			{"id": VOICE_DESIGN_MODEL_ID, "object": "model", "created": 0, "owned_by": "owner"},
		],
	}


@app.post("/v1/audio/speech", response_model=AudioSpeechResponse)
async def create_speech(req: SpeechRequest):
	if req.model.lower() != MODEL_ID.lower():
		raise HTTPException(status_code=400, detail=f"Model not available: {MODEL_ID}")

	if req.stream:
		raise HTTPException(status_code=400, detail="stream is not supported; set stream to false")

	try:
		minio_path, download_url, duration, _ = await asyncio.to_thread(
			synthesize_custom_voice_to_minio,
			model_path=MODEL_PATH,
			device=DEVICE,
			dtype_str=DTYPE_STR,
			attn_impl=ATTN_IMPL,
			text=req.input,
			language=req.language,
			speaker=req.voice,
			instruct=req.instruct or "",
			response_format=req.response_format,
			output_dir=OUTPUT_DIR,
			minio_upload_dir=MINIO_UPLOAD_DIR,
			max_new_tokens=req.max_new_tokens,
		)
	except Exception as exc:  # noqa: BLE001
		raise HTTPException(status_code=500, detail=str(exc)) from exc

	content = AudioContent(
		audio=download_url,
		format="wav" if req.response_format == "url" else req.response_format,
		minio_path=minio_path,
		duration=duration,
	)

	output = AudioOutput(
		choices=[
			AudioChoice(
				index=0,
				finish_reason="stop",
				message=ChoiceMessage(content=[content]),
			)
		],
		task_metric=TaskMetric(FAILED=0, SUCCEEDED=1, TOTAL=1),
	)

	usage = AudioUsage(duration=duration, input_length=len(req.input))

	resp = AudioSpeechResponse(
		id=str(uuid.uuid4()),
		object="audio.speech",
		created=int(time.time()),
		model=req.model,
		voice=req.voice,
		output=output,
		usage=usage,
		request_id=str(uuid.uuid4()),
	)
	return resp


@app.post("/v1/audio/voice_design", response_model=AudioVoiceDesignResponse)
async def create_voice_design(req: VoiceDesignRequest):
	if req.model.lower() != VOICE_DESIGN_MODEL_ID.lower():
		raise HTTPException(status_code=400, detail=f"Model not available: {VOICE_DESIGN_MODEL_ID}")

	if req.stream:
		raise HTTPException(status_code=400, detail="stream is not supported; set stream to false")

	try:
		minio_path, download_url, duration, _ = await asyncio.to_thread(
			synthesize_voice_design_to_minio,
			model_path=VOICE_DESIGN_MODEL_PATH,
			device=DEVICE,
			dtype_str=DTYPE_STR,
			attn_impl=ATTN_IMPL,
			text=req.input,
			language=req.language,
			instruct=req.instruct or "",
			response_format=req.response_format,
			output_dir=OUTPUT_DIR,
			minio_upload_dir=MINIO_UPLOAD_DIR,
			max_new_tokens=req.max_new_tokens,
		)
	except Exception as exc:  # noqa: BLE001
		raise HTTPException(status_code=500, detail=str(exc)) from exc

	content = AudioContent(
		audio=download_url,
		format="wav" if req.response_format == "url" else req.response_format,
		minio_path=minio_path,
		duration=duration,
	)

	output = AudioOutput(
		choices=[
			AudioChoice(
				index=0,
				finish_reason="stop",
				message=ChoiceMessage(content=[content]),
			)
		],
		task_metric=TaskMetric(FAILED=0, SUCCEEDED=1, TOTAL=1),
	)

	usage = AudioUsage(duration=duration, input_length=len(req.input))

	resp = AudioVoiceDesignResponse(
		id=str(uuid.uuid4()),
		object="audio.voice_design",
		created=int(time.time()),
		model=req.model,
		output=output,
		usage=usage,
		request_id=str(uuid.uuid4()),
	)
	return resp


@app.post("/v1/audio/voice_clone", response_model=AudioSpeechResponse)
async def create_voice_clone(req: VoiceCloneRequest):
	if req.model.lower() != BASE_MODEL_ID.lower():
		raise HTTPException(status_code=400, detail=f"Model not available: {BASE_MODEL_ID}")

	if req.stream:
		raise HTTPException(status_code=400, detail="stream is not supported; set stream to false")

	try:
		minio_path, download_url, duration, _ = await asyncio.to_thread(
			synthesize_voice_clone_to_minio,
			model_path=BASE_MODEL_PATH,
			device=DEVICE,
			dtype_str=DTYPE_STR,
			attn_impl=ATTN_IMPL,
			text=req.input,
			language=req.language,
			ref_audio=req.ref_audio,
			ref_text=req.ref_text,
			x_vector_only_mode=req.x_vector_only_mode,
			response_format=req.response_format,
			output_dir=OUTPUT_DIR,
			minio_upload_dir=MINIO_UPLOAD_DIR,
			max_new_tokens=req.max_new_tokens,
		)
	except Exception as exc:  # noqa: BLE001
		raise HTTPException(status_code=500, detail=str(exc)) from exc

	content = AudioContent(
		audio=download_url,
		format="wav" if req.response_format == "url" else req.response_format,
		minio_path=minio_path,
		duration=duration,
	)

	output = AudioOutput(
		choices=[
			AudioChoice(
				index=0,
				finish_reason="stop",
				message=ChoiceMessage(content=[content]),
			)
		],
		task_metric=TaskMetric(FAILED=0, SUCCEEDED=1, TOTAL=1),
	)

	usage = AudioUsage(duration=duration, input_length=len(req.input))

	resp = AudioSpeechResponse(
		id=str(uuid.uuid4()),
		object="audio.speech",
		created=int(time.time()),
		model=req.model,
		voice="voice_clone",
		output=output,
		usage=usage,
		request_id=str(uuid.uuid4()),
	)
	return resp


if __name__ == "__main__":
	import uvicorn

	uvicorn.run("api:app", host="0.0.0.0", port=int(os.getenv("PORT", "6006")), reload=True)
