import os
import io
import base64
import time
import uuid
import sys
import requests
import logging
import json
from logging.handlers import TimedRotatingFileHandler
from typing import List, Optional, Tuple
from pathlib import Path

from PIL import Image
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

# 配置日志
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# 创建日志格式（包含行号）
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')

# 创建 logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# 文件处理器 - 每天滚动
file_handler = TimedRotatingFileHandler(
    filename=os.path.join(LOG_DIR, "api-vllm-gateway.log"),
    when="midnight",  # 每天午夜滚动
    interval=1,       # 间隔1天
    backupCount=30,   # 保留30天的日志
    encoding="utf-8"
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(log_formatter)
file_handler.suffix = "%Y-%m-%d"  # 日志文件后缀格式
logger.addHandler(file_handler)

logger.info(f"日志目录: {LOG_DIR}")
logger.info(f"日志文件: api-vllm-gateway.log (每天滚动，保留30天)")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vnet.common.config.env import load_env
load_env(dotenv_path=os.path.join(BASE_DIR, ".env"), override=False)
from vnet.common.storage.dal.minio.minio_userpass import MinioApiUploader, MinioSettings

# ----------------------------------
# 配置
# ----------------------------------
VLLM_API_URL = os.environ.get("VLLM_API_URL", "http://localhost:9111/v1/images/generations")
MODEL_NAME = os.environ.get("MODEL_NAME", "qwen-image")
DEFAULT_IMAGE_DIR = os.path.join(BASE_DIR, "images_tmp")
IMAGE_OUTPUT_DIR = os.environ.get("IMAGE_OUTPUT_DIR", DEFAULT_IMAGE_DIR)
MINIO_UPLOAD_DIR = os.environ.get("MINIO_UPLOAD_DIR", "qwen-image")
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
# 请求/响应模型
# ----------------------------------

# 阿里百炼格式（嵌套结构）
class TextContent(BaseModel):
    text: str = Field(..., max_length=800)

class InputMessage(BaseModel):
    role: str = "user"
    content: List[TextContent]

class InputPayload(BaseModel):
    prompt: Optional[str] = Field(default=None, max_length=800)
    messages: Optional[List[InputMessage]] = None

class Parameters(BaseModel):
    size: Optional[str] = Field(default="1024*1024")
    n: Optional[int] = Field(default=1, ge=1, le=4)
    seed: Optional[int] = Field(default=None, ge=0, le=2147483647)
    negative_prompt: Optional[str] = Field(default="", max_length=500)
    # 支持两种参数名：num_inference_steps 或 steps
    num_inference_steps: Optional[int] = Field(default=None, ge=1, le=50)
    steps: Optional[int] = Field(default=None, ge=1, le=50)
    # 支持两种参数名：guidance_scale 或 scale
    guidance_scale: Optional[float] = Field(default=None)
    scale: Optional[float] = Field(default=None)
    response_format: Optional[str] = Field(default="url")

    def get_num_inference_steps(self) -> int:
        """获取推理步数，优先使用 steps，其次 num_inference_steps，默认 30"""
        return self.steps or self.num_inference_steps or 30

    def get_guidance_scale(self) -> float:
        """获取引导系数，优先使用 scale，其次 guidance_scale，默认 4.0"""
        return self.scale or self.guidance_scale or 4.0

class ImageGenerationRequest(BaseModel):
    model: str
    input: InputPayload
    parameters: Optional[Parameters] = Field(default_factory=Parameters)

    class Config:
        extra = "forbid"

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
    """解析尺寸字符串，支持 1024*1024 或 1024x1024"""
    if not size:
        return 1024, 1024
    try:
        sz = size.replace("x", "*")
        w, h = sz.split("*")
        return int(w), int(h)
    except Exception:
        return 1024, 1024

def save_image_from_b64(b64_data: str, output_dir: str) -> str:
    """保存 base64 图像到本地"""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.png"
    filepath = os.path.join(output_dir, filename)

    logger.info(f"开始转换 base64 数据为图片: {filename}")
    try:
        image_data = base64.b64decode(b64_data)
        with open(filepath, "wb") as f:
            f.write(image_data)
        logger.info(f"图片保存成功: {filepath}, 大小: {len(image_data)} bytes")
        return filepath
    except Exception as e:
        logger.error(f"保存图片失败: {str(e)}")
        raise

def call_vllm_api(prompt: str, size: str, n: int, negative_prompt: str,
                  num_inference_steps: int, guidance_scale: float, seed: Optional[int]) -> dict:
    """调用 vLLM API 生成图像"""
    # 扁平化参数格式（不使用 extra_body）
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "n": n,
        "size": size.replace("*", "x"),
        "response_format": "b64_json",
        "negative_prompt": negative_prompt,
        "num_inference_steps": num_inference_steps,
        "guidance_scale": guidance_scale,
    }

    if seed is not None:
        payload["seed"] = seed

    logger.info(f"========== 准备调用 vLLM API ==========")
    logger.info(f"vLLM API URL: {VLLM_API_URL}")
    logger.info(f"发送至 vLLM 的参数明细:")
    logger.info(f"  - model: {payload['model']}")
    logger.info(f"  - prompt: {prompt[:100]}..." if len(prompt) > 100 else f"  - prompt: {prompt}")
    logger.info(f"  - n: {payload['n']}")
    logger.info(f"  - size: {payload['size']}")
    logger.info(f"  - response_format: {payload['response_format']}")
    logger.info(f"  - negative_prompt: {payload['negative_prompt']}")
    logger.info(f"  - num_inference_steps: {payload['num_inference_steps']}")
    logger.info(f"  - guidance_scale: {payload['guidance_scale']}")
    if seed is not None:
        logger.info(f"  - seed: {payload['seed']}")
    logger.info(f"========================================")

    try:
        start_time = time.time()
        response = requests.post(VLLM_API_URL, json=payload, timeout=300)
        elapsed_time = time.time() - start_time

        response.raise_for_status()
        logger.info(f"vLLM API 调用成功, 耗时: {elapsed_time:.2f}s, 状态码: {response.status_code}")

        result = response.json()
        image_count = len(result.get("data", []))
        logger.info(f"vLLM 返回 {image_count} 张图像")

        return result
    except requests.exceptions.Timeout:
        logger.error(f"vLLM API 调用超时 (>300s)")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"vLLM API 调用失败: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"vLLM API 响应解析失败: {str(e)}")
        raise

# ----------------------------------
# FastAPI 应用
# ----------------------------------
app = FastAPI(title="Qwen-Image vLLM Proxy API", version="1.0.0")

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求参数验证错误"""
    errors = exc.errors()
    error_messages = []
    invalid_fields = []

    for error in errors:
        field = ".".join(str(loc) for loc in error["loc"])
        msg = error["msg"]
        error_type = error["type"]

        if error_type == "extra_forbidden":
            invalid_fields.append(field)
            error_messages.append(f"无效字段: {field} (不允许的额外字段)")
        else:
            error_messages.append(f"{field}: {msg}")

    logger.error(f"请求参数验证失败: {error_messages}")

    if invalid_fields:
        valid_fields_msg = (
            "有效的字段:\n"
            "  - model: 模型名称\n"
            "  - input: prompt (字符串) 或 messages (消息数组)\n"
            "  - parameters: size, n, seed, negative_prompt, num_inference_steps (或 steps), guidance_scale (或 scale), response_format"
        )
        return JSONResponse(
            status_code=400,
            content={
                "detail": f"请求包含无效字段: {', '.join(invalid_fields)}",
                "errors": error_messages,
                "valid_fields": valid_fields_msg
            }
        )

    return JSONResponse(
        status_code=400,
        content={"detail": "请求参数验证失败", "errors": error_messages}
    )

@app.on_event("startup")
async def startup_event():
    """应用启动时登录 MinIO"""
    logger.info("=" * 60)
    logger.info("启动 Qwen-Image vLLM 网关服务")
    logger.info(f"vLLM API 地址: {VLLM_API_URL}")
    logger.info(f"模型名称: {MODEL_NAME}")
    logger.info(f"临时目录: {IMAGE_OUTPUT_DIR}")
    logger.info(f"MinIO 上传目录: {MINIO_UPLOAD_DIR}")
    logger.info("=" * 60)

    logger.info("正在登录 MinIO...")
    if minio_handler.login():
        logger.info("MinIO 登录成功")
    else:
        logger.error("MinIO 登录失败，请检查配置")

@app.get("/healthz")
async def healthz():
    logger.debug("健康检查请求")
    return {"status": "ok", "vllm_url": VLLM_API_URL}

@app.post("/api/v1/services/aigc/multimodal-generation/generation", response_model=ImageGenerationResponse)
async def create_image(req: ImageGenerationRequest, request: Request):
    """多模态生成接口（阿里百炼格式）"""
    request_id = uuid.uuid4().hex
    logger.info(f"[{request_id}] ========== 收到图像生成请求 ==========")

    # 打印客户端实际请求
    try:
        request_body = await request.body()
        request_json = json.loads(request_body.decode('utf-8'))
        logger.info(f"[{request_id}] 客户端原始请求:")
        logger.info(f"[{request_id}] {json.dumps(request_json, ensure_ascii=False, indent=2)}")
    except Exception as e:
        logger.warning(f"[{request_id}] 无法解析客户端请求体: {str(e)}")

    # 提取 prompt（支持 input.prompt 或 input.messages 格式）
    prompt = None
    if req.input.prompt:
        prompt = req.input.prompt
    elif req.input.messages and len(req.input.messages) > 0:
        # 从 messages 中提取 text
        for msg in req.input.messages:
            if msg.content and len(msg.content) > 0:
                prompt = msg.content[0].text
                break

    if not prompt:
        logger.error(f"[{request_id}] 缺少 prompt 参数")
        raise HTTPException(status_code=400, detail="缺少 prompt 参数，请在 input.prompt 或 input.messages 中提供")

    # 获取参数（使用默认值）
    params = req.parameters or Parameters()

    # 获取实际使用的参数值（支持参数别名）
    actual_steps = params.get_num_inference_steps()
    actual_scale = params.get_guidance_scale()

    # 打印完整请求参数
    logger.info(f"[{request_id}] 请求模型: {req.model}")
    logger.info(f"[{request_id}] 请求参数明细:")
    logger.info(f"[{request_id}]   - input.prompt: {req.input.prompt}")
    logger.info(f"[{request_id}]   - input.messages: {req.input.messages}")
    logger.info(f"[{request_id}]   - parameters.size: {params.size}")
    logger.info(f"[{request_id}]   - parameters.n: {params.n}")
    logger.info(f"[{request_id}]   - parameters.seed: {params.seed}")
    logger.info(f"[{request_id}]   - parameters.negative_prompt: {params.negative_prompt}")
    logger.info(f"[{request_id}]   - parameters.steps/num_inference_steps: {params.steps}/{params.num_inference_steps} -> 实际使用: {actual_steps}")
    logger.info(f"[{request_id}]   - parameters.scale/guidance_scale: {params.scale}/{params.guidance_scale} -> 实际使用: {actual_scale}")
    logger.info(f"[{request_id}]   - parameters.response_format: {params.response_format}")

    # 验证有效参数
    logger.info(f"[{request_id}] ========== 参数验证 ==========")
    logger.info(f"[{request_id}] 有效字段: model, input (prompt/messages), parameters (size, n, seed, negative_prompt, num_inference_steps/steps, guidance_scale/scale, response_format)")

    # 验证 response_format
    valid_formats = ["url", "b64_json"]
    if params.response_format.lower() not in valid_formats:
        logger.error(f"[{request_id}] 无效的 response_format: {params.response_format}, 有效值: {valid_formats}")
        raise HTTPException(status_code=400, detail=f"无效的 response_format，有效值: {valid_formats}")
    logger.info(f"[{request_id}] ✓ response_format 验证通过: {params.response_format}")

    # 验证 size 格式
    try:
        width, height = get_image_size(params.size)
        if width <= 0 or height <= 0:
            raise ValueError("尺寸必须大于0")
        logger.info(f"[{request_id}] ✓ size 验证通过: {params.size} -> {width}x{height}")
    except Exception as e:
        logger.error(f"[{request_id}] 无效的 size 格式: {params.size}, 错误: {str(e)}")
        raise HTTPException(status_code=400, detail=f"无效的 size 格式，应为 '宽*高' 或 '宽x高'，如 '1024*1024'")

    logger.info(f"[{request_id}] ✓ 所有参数验证通过")
    logger.info(f"[{request_id}] ============================")

    logger.info(f"[{request_id}] 提取的 Prompt: {prompt[:100]}..." if len(prompt) > 100 else f"[{request_id}] 提取的 Prompt: {prompt}")
    logger.info(f"[{request_id}] 参数: size={params.size}({width}x{height}), n={params.n}, steps={actual_steps}, guidance={actual_scale}, seed={params.seed}")

    # 调用 vLLM API
    try:
        vllm_response = call_vllm_api(
            prompt=prompt,
            size=params.size,
            n=params.n,
            negative_prompt=params.negative_prompt,
            num_inference_steps=actual_steps,
            guidance_scale=actual_scale,
            seed=params.seed
        )
    except Exception as e:
        logger.error(f"[{request_id}] vLLM API 调用失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"vLLM API 调用失败: {str(e)}")

    # 处理返回的图像
    logger.info(f"[{request_id}] 开始处理返回的图像")
    choices: List[Choice] = []
    errors: List[str] = []
    response_format = params.response_format.lower()
    logger.info(f"[{request_id}] 返回格式: {response_format}")

    for idx, item in enumerate(vllm_response.get("data", [])):
        logger.info(f"[{request_id}] 处理第 {idx + 1} 张图像")
        b64_json = item.get("b64_json")
        if not b64_json:
            error_msg = f"第 {idx + 1} 张图像缺少 b64_json 数据"
            logger.error(f"[{request_id}] {error_msg}")
            errors.append(error_msg)
            continue

        try:
            if response_format == "url":
                # 保存图像并上传到 MinIO
                logger.info(f"[{request_id}] 转换 base64 为图片文件")
                filepath = save_image_from_b64(b64_json, IMAGE_OUTPUT_DIR)

                logger.info(f"[{request_id}] 上传图片到 MinIO: {filepath}")
                upload_start = time.time()
                upload = minio_handler.upload_file(filepath, upload_dir=MINIO_UPLOAD_DIR)
                upload_time = time.time() - upload_start

                if upload.get("error"):
                    error_msg = upload.get("error_str", "上传失败")
                    logger.error(f"[{request_id}] MinIO 上传失败: {error_msg}")
                    errors.append(error_msg)
                    continue

                download_url = upload.get("download_url")
                logger.info(f"[{request_id}] MinIO 上传成功, 耗时: {upload_time:.2f}s, URL: {download_url}")

                choice = Choice(
                    finish_reason="stop",
                    message=MessageContent(
                        content=[ImageContent(image=download_url)],
                        role="assistant"
                    )
                )
                choices.append(choice)

                # 清理本地文件
                try:
                    os.remove(filepath)
                    logger.debug(f"[{request_id}] 已清理临时文件: {filepath}")
                except Exception as e:
                    logger.warning(f"[{request_id}] 清理临时文件失败: {str(e)}")
            else:
                # b64_json 格式
                logger.info(f"[{request_id}] 返回 base64 格式")
                choice = Choice(
                    finish_reason="stop",
                    message=MessageContent(
                        content=[ImageContent(image=f"data:image/png;base64,{b64_json}")],
                        role="assistant"
                    )
                )
                choices.append(choice)
        except Exception as e:
            error_msg = f"处理第 {idx + 1} 张图像失败: {str(e)}"
            logger.error(f"[{request_id}] {error_msg}")
            errors.append(error_msg)

    if not choices:
        logger.error(f"[{request_id}] 所有图像处理失败: {'; '.join(errors)}")
        raise HTTPException(status_code=500, detail=f"图像处理失败: {'; '.join(errors)}")

    # 构造响应
    task_metric = TaskMetric(
        TOTAL=params.n,
        SUCCEEDED=len(choices),
        FAILED=len(errors)
    )

    output = OutputPayload(
        choices=choices,
        task_metric=task_metric
    )

    usage = Usage(
        image_count=len(choices),
        width=width,
        height=height
    )

    resp = ImageGenerationResponse(
        output=output,
        usage=usage,
        request_id=request_id,
    )

    logger.info(f"[{request_id}] 请求处理完成, 成功: {len(choices)}, 失败: {len(errors)}")
    return resp

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api-for-vllm:app", host="0.0.0.0", port=6003, reload=True)
