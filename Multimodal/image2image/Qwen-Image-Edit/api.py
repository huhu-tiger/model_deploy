import os

# 设置环境变量
os.environ["CUDA_VISIBLE_DEVICES"] = "4"
os.environ["vl_base_url"] = "http://192.168.0.2:9116/v1"
os.environ["vl_model"] = "Qwen2.5-VL-7B-Instruct"
os.environ["download_url"] = "http://39.155.179.4:6003"


from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import base64
import io
import json
import os
import torch
import numpy as np
import random
from PIL import Image
import requests

from diffusers import QwenImageEditPipeline
import uuid
from datetime import datetime
import time
import pathlib


from vnet.common.storage.dal.minio.minio_conn import minio_process
# 兼容 Pydantic v2：动态导入 pydantic_settings，避免静态检查报未安装告警
from importlib import import_module
try:
	BaseSettings = getattr(import_module("pydantic_settings"), "BaseSettings")  # type: ignore
except Exception:
	BaseSettings = None

if BaseSettings is not None:
	class MinioSettings(BaseSettings):
		Minio_IP: str = Field(default="120.133.137.142", env="MINIO_IP")
		Minio_Upload_Port: int = Field(default=9000, env="MINIO_UPLOAD_PORT")
		Minio_Upload_Url: str = Field(default="http://120.133.137.142:9000", env="MINIO_UPLOAD_URL")
		Minio_Access_Key: str = Field(default="IoeOmDzCZOkM0CiF6IK3", env="MINIO_ACCESS_KEY")
		Minio_Secret_Key: str = Field(default="c5gKEUpeU1oirwTOmkbLtXKl0fiDCrtlkmEU0fIt", env="MINIO_SECRET_KEY")
		Minio_Bucket_Name: str = Field(default="files", env="MINIO_BUCKET_NAME")
	minio_settings = MinioSettings()
else:
	# 回退：未安装 pydantic-settings 时直接从环境变量读取
	class _EnvMinioSettings:
		Minio_IP = os.environ.get("MINIO_IP", "120.133.137.142")
		Minio_Upload_Port = int(os.environ.get("MINIO_UPLOAD_PORT", "9000"))
		Minio_Upload_Url = os.environ.get("MINIO_UPLOAD_URL", "http://120.133.137.142:9000")
		Minio_Access_Key = os.environ.get("MINIO_ACCESS_KEY", "IoeOmDzCZOkM0CiF6IK3")
		Minio_Secret_Key = os.environ.get("MINIO_SECRET_KEY", "c5gKEUpeU1oirwTOmkbLtXKl0fiDCrtlkmEU0fIt")
		Minio_Bucket_Name = os.environ.get("MINIO_BUCKET_NAME", "files")
	minio_settings = _EnvMinioSettings()
minio_handler = minio_process(access_key=minio_settings.Minio_Access_Key, secret_key=minio_settings.Minio_Secret_Key,
                              minio_server=f"{minio_settings.Minio_IP}:{minio_settings.Minio_Upload_Port}", bucket_name=minio_settings.Minio_Bucket_Name)



# 创建输出目录
OUTPUT_DIR = pathlib.Path("output_images")
OUTPUT_DIR.mkdir(exist_ok=True)

def cleanup_old_images(max_files=100):
    """清理旧的图片文件，保留最新的max_files个文件"""
    try:
        files = list(OUTPUT_DIR.glob("*.png"))
        if len(files) > max_files:
            # 按修改时间排序，删除最旧的文件
            files.sort(key=lambda x: x.stat().st_mtime)
            for old_file in files[:-max_files]:
                old_file.unlink()
                print(f"已删除旧文件: {old_file}")
    except Exception as e:
        print(f"清理文件时出错: {e}")

app = FastAPI(
    title="Qwen Image Edit API",
    description="基于Qwen-Image的图像编辑API，符合OpenAI格式",
    version="1.0.0"
)

# 挂载静态文件目录
app.mount("/images", StaticFiles(directory=str(OUTPUT_DIR)), name="images")

# 挂载静态HTML页面
STATIC_DIR = pathlib.Path("static")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 启动事件处理器
@app.on_event("startup")
async def startup_event():
    """应用启动时加载模型"""
    global _pipe, _device
    print("🚀 应用启动，开始加载模型...")
    _pipe, _device = load_model()
    print("✅ 模型加载完成，应用已准备就绪!")

# 数据模型定义
class ImageEditRequest(BaseModel):
    model: str = Field(default="qwen-image-edit", description="模型名称")
    prompt: str = Field(..., description="编辑指令")
    image: str = Field(..., description="图片URL或Base64编码的输入图像")
    n: int = Field(default=1, description="生成图像数量")
    size: str = Field(default="1024x1024", description="图像尺寸")
    quality: str = Field(default="standard", description="图像质量")
    style: Optional[str] = Field(default=None, description="图像风格")
    seed: Optional[int] = Field(default=None, description="随机种子")
    guidance_scale: float = Field(default=4.0, description="引导比例")
    num_inference_steps: int = Field(default=50, description="推理步数")
    rewrite_prompt: bool = Field(default=True, description="是否重写提示词")

class ImageEditFormRequest(BaseModel):
    model: str = Field(default="qwen-image-edit", description="模型名称")
    prompt: str = Field(..., description="编辑指令")
    image_url: Optional[str] = Field(None, description="图片URL")
    n: int = Field(default=1, description="生成图像数量")
    size: str = Field(default="1024x1024", description="图像尺寸")
    quality: str = Field(default="standard", description="图像质量")
    style: Optional[str] = Field(default=None, description="图像风格")
    seed: Optional[int] = Field(default=None, description="随机种子")
    guidance_scale: float = Field(default=4.0, description="引导比例")
    num_inference_steps: int = Field(default=50, description="推理步数")
    rewrite_prompt: bool = Field(default=True, description="是否重写提示词")

class ImageEditResponse(BaseModel):
    id: str
    object: str = "image.edit"
    created: int
    model: str
    data: List[Dict[str, Any]]

class ErrorResponse(BaseModel):
    error: Dict[str, Any]

# 系统提示词
SYSTEM_PROMPT = '''
# Edit Instruction Rewriter
You are a professional edit instruction rewriter. Your task is to generate a precise, concise, and visually achievable professional-level edit instruction based on the user-provided instruction and the image to be edited.  

Please strictly follow the rewriting rules below:

## 1. General Principles
- Keep the rewritten prompt **concise**. Avoid overly long sentences and reduce unnecessary descriptive language.  
- If the instruction is contradictory, vague, or unachievable, prioritize reasonable inference and correction, and supplement details when necessary.  
- Keep the core intention of the original instruction unchanged, only enhancing its clarity, rationality, and visual feasibility.  
- All added objects or modifications must align with the logic and style of the edited input image's overall scene.  

## 2. Task Type Handling Rules
### 1. Add, Delete, Replace Tasks
- If the instruction is clear (already includes task type, target entity, position, quantity, attributes), preserve the original intent and only refine the grammar.  
- If the description is vague, supplement with minimal but sufficient details (category, color, size, orientation, position, etc.). For example:  
    > Original: "Add an animal"  
    > Rewritten: "Add a light-gray cat in the bottom-right corner, sitting and facing the camera"  
- Remove meaningless instructions: e.g., "Add 0 objects" should be ignored or flagged as invalid.  
- For replacement tasks, specify "Replace Y with X" and briefly describe the key visual features of X.  

### 2. Text Editing Tasks
- All text content must be enclosed in English double quotes `" "`. Do not translate or alter the original language of the text, and do not change the capitalization.  
- **For text replacement tasks, always use the fixed template:**
    - `Replace "xx" to "yy"`.  
    - `Replace the xx bounding box to "yy"`.  
- If the user does not specify text content, infer and add concise text based on the instruction and the input image's context. For example:  
    > Original: "Add a line of text" (poster)  
    > Rewritten: "Add text \"LIMITED EDITION\" at the top center with slight shadow"  
- Specify text position, color, and layout in a concise way.  

### 3. Human Editing Tasks
- Maintain the person's core visual consistency (ethnicity, gender, age, hairstyle, expression, outfit, etc.).  
- If modifying appearance (e.g., clothes, hairstyle), ensure the new element is consistent with the original style.  
- **For expression changes, they must be natural and subtle, never exaggerated.**  
- If deletion is not specifically emphasized, the most important subject in the original image (e.g., a person, an animal) should be preserved.
    - For background change tasks, emphasize maintaining subject consistency at first.  
- Example:  
    > Original: "Change the person's hat"  
    > Rewritten: "Replace the man's hat with a dark brown beret; keep smile, short hair, and gray jacket unchanged"  

### 4. Style Transformation or Enhancement Tasks
- If a style is specified, describe it concisely with key visual traits. For example:  
    > Original: "Disco style"  
    > Rewritten: "1970s disco: flashing lights, disco ball, mirrored walls, colorful tones"  
- If the instruction says "use reference style" or "keep current style," analyze the input image, extract main features (color, composition, texture, lighting, art style), and integrate them concisely.  
- **For coloring tasks, including restoring old photos, always use the fixed template:** "Restore old photograph, remove scratches, reduce noise, enhance details, high resolution, realistic, natural skin tones, clear facial features, no distortion, vintage photo restoration"  
- If there are other changes, place the style description at the end.

## 3. Rationality and Logic Checks
- Resolve contradictory instructions: e.g., "Remove all trees but keep all trees" should be logically corrected.  
- Add missing key information: if position is unspecified, choose a reasonable area based on composition (near subject, empty space, center/edges).  

# Output Format Example
```json
{
   "Rewritten": "..."
}
'''

# 工具函数
def encode_image(pil_image):
    """将PIL图像编码为base64字符串"""
    buffered = io.BytesIO()
    pil_image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def download_image_from_url(url: str) -> Image.Image:
    """从URL下载图片"""
    try:
        # 替换IP地址
        modified_url = url.replace("39.155.179.4", "192.168.0.2")
        if modified_url != url:
            print(f"IP地址已替换: {url} -> {modified_url}")
        
        response = requests.get(modified_url, timeout=30)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content))
        return image
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"从URL下载图片失败: {str(e)}")

def decode_image(image_input: str) -> Image.Image:
    """处理图片输入（URL或Base64）"""
    try:
        # 检查是否为URL
        if image_input.startswith(('http://', 'https://')):
            return download_image_from_url(image_input)
        
        # 处理Base64编码
        if ',' in image_input:
            image_input = image_input.split(',')[1]
        
        image_data = base64.b64decode(image_input)
        image = Image.open(io.BytesIO(image_data))
        return image
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"图像处理失败: {str(e)}")

def custom_api(prompt, img_list, model="gpt-4o-mini", kwargs={}):
    """调用自定义API进行提示词重写"""
    import os
    try:
        from openai import OpenAI
    except Exception as e:
        raise ImportError("请先安装 openai 包: pip install openai") from e

    api_key = kwargs.get('openai_api_key', os.environ.get('OPENAI_API_KEY'))
    base_url = kwargs.get('openai_api_base', os.environ.get('OPENAI_API_BASE') or os.environ.get('OPENAI_BASE_URL') or os.environ.get('vl_base_url'))
    model_name = kwargs.get('model_name', os.environ.get('vl_model'))
    client_init_kwargs = {
        'api_key': api_key or 'EMPTY'
    }
    if base_url:
        client_init_kwargs['base_url'] = base_url

    client = OpenAI(**client_init_kwargs)

    system_prompt = kwargs.get('system_prompt', 'you are a helpful assistant, you should provide useful answers to users.')

    user_content = [{"type": "text", "text": f"{prompt}"}]
    for pil_image in (img_list or []):
        try:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encode_image(pil_image)}"}
            })
        except Exception:
            continue

    temperature = float(kwargs.get('temperature', 0.2))
    max_tokens = int(kwargs.get('max_tokens', 2048))

    params = {
        'model': model_name,
        'messages': [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        'temperature': temperature,
        'max_tokens': max_tokens,
    }
    response_format = kwargs.get('response_format')
    if response_format is not None:
        params['response_format'] = response_format

    resp = client.chat.completions.create(**params)
    try:
        return resp.choices[0].message.content
    except Exception:
        raise Exception(f"OpenAI 返回格式不兼容: {resp}")

def polish_prompt(prompt, img):
    """重写提示词"""
    prompt = f"{SYSTEM_PROMPT}\n\nUser Input: {prompt}\n\nRewritten Prompt:"
    success = False
    while not success:
        try:
            result = custom_api(prompt, [img])
            if isinstance(result, str):
                result = result.replace('```json','')
                result = result.replace('```','')
                result = json.loads(result)
            else:
                result = json.loads(result)

            polished_prompt = result['Rewritten']
            polished_prompt = polished_prompt.strip()
            polished_prompt = polished_prompt.replace("\n", " ")
            success = True
        except Exception as e:
            print(f"[Warning] Error during API call: {e}")
            # 如果API调用失败，返回原始提示词
            return prompt
    return polished_prompt

# 全局变量用于模型加载
_pipe = None
_device = None

def load_model():
    """加载模型"""
    global _pipe, _device
    
    print("正在加载Qwen-Image-Edit模型...")
    
    # 检查CUDA环境
    if torch.cuda.is_available():
        print(f"CUDA可用，设备数量: {torch.cuda.device_count()}")
        print(f"当前CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES', '未设置')}")
        
        # 显示GPU信息
        for i in range(torch.cuda.device_count()):
            gpu_name = torch.cuda.get_device_name(i)
            gpu_memory = torch.cuda.get_device_properties(i).total_memory / 1024**3
            print(f"GPU {i}: {gpu_name}, 内存: {gpu_memory:.1f} GB")
        
        # 设置内存分配策略
        os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
        
        # 清理GPU缓存
        torch.cuda.empty_cache()
        
        _device = 'cuda'
        dtype = torch.bfloat16
        
        # 检查是否使用多GPU
        use_multi_gpu = torch.cuda.device_count() > 1 or (',' in os.environ.get('CUDA_VISIBLE_DEVICES', ''))
        
        if use_multi_gpu:
            print("使用多GPU配置...")
            _pipe = QwenImageEditPipeline.from_pretrained(
                "/media/llm/Qwen-Image-Edit", 
                torch_dtype=dtype, 
                device_map='balanced',
                low_cpu_mem_usage=True
            )
        else:
            print("使用单GPU配置...")
            _pipe = QwenImageEditPipeline.from_pretrained(
                "/media/llm/Qwen-Image-Edit", 
                torch_dtype=dtype,
                low_cpu_mem_usage=True
            ).to(_device)
    else:
        print("CUDA不可用，使用CPU...")
        _device = 'cpu'
        dtype = torch.float32
        _pipe = QwenImageEditPipeline.from_pretrained(
            "/media/llm/Qwen-Image-Edit", 
            torch_dtype=dtype,
            low_cpu_mem_usage=True
        ).to(_device)
    
    print(f"模型加载完成! 使用设备: {_device}")
    return _pipe, _device

# API端点
@app.post("/v1/images/edits", response_model=ImageEditResponse)
async def create_image_edit(request: ImageEditRequest):
    """
    创建图像编辑
    
    支持JSON格式请求，图片输入可以是：
    1. 图片URL: "image": "https://example.com/image.jpg"
    2. Base64编码: "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
    
    注意：当图片URL中包含IP地址39.155.179.4时，会自动替换为192.168.0.2
    """
    """
    创建图像编辑
    
    兼容三种格式：
    1. JSON格式：使用request参数（支持图片URL或Base64）
    2. 表单格式：使用image文件上传 + 其他表单参数
    3. 表单格式：使用image_url参数 + 其他表单参数
    """
    try:
        # 处理图片输入（URL或Base64）
        input_image = decode_image(request.image)
        
        # 设置随机种子
        if request.seed is None:
            final_seed = random.randint(0, 2**32 - 1)
        else:
            final_seed = request.seed
        
        # 设置随机种子
        if final_seed is None:
            final_seed = random.randint(0, 2**32 - 1)
            
        generator = torch.Generator(device=_device).manual_seed(final_seed)
        
        # 重写提示词
        final_prompt = request.prompt
        if request.rewrite_prompt:
            final_prompt = polish_prompt(request.prompt, input_image)
            print(f"原始提示词: {request.prompt}")
            print(f"重写后提示词: {final_prompt}")
        
        # 检查模型是否已加载
        if _pipe is None:
            raise HTTPException(status_code=503, detail="模型尚未加载完成，请稍后重试")
        
        # 生成图像
        print(f"开始生成图像，提示词: '{final_prompt}'")
        print(f"种子: {final_seed}, 步数: {request.num_inference_steps}, 引导比例: {request.guidance_scale}")
        
        images = _pipe(
            input_image,
            prompt=final_prompt,
            negative_prompt=" ",
            num_inference_steps=request.num_inference_steps,
            generator=generator,
            true_cfg_scale=request.guidance_scale,
            num_images_per_prompt=request.n
        ).images
        
        # 准备响应数据
        data = []
        for i, image in enumerate(images):
            # 生成唯一文件名
            filename = f"edit_{uuid.uuid4().hex}.png"
            file_path = OUTPUT_DIR / filename
            
            # 保存图像到文件系统
            image.save(file_path, format="PNG")
            
            # 上传到 MinIO
            upload_result = minio_handler.upload_file(file_path=str(file_path))
            if upload_result.get("error"):
                error_str = upload_result.get("error_str", "MinIO upload failed")
                raise HTTPException(status_code=500, detail=f"图片上传至MinIO失败: {error_str}")
            
            minio_object_path = upload_result.get("minio_put_path")
            download_url = minio_handler.generate_download_url(minio_object_path)
            
            # 上传完成后清理本地文件以节省空间
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass
            
            data.append({
                "url": download_url,
                "revised_prompt": final_prompt
            })
        
        # 清理旧文件
        cleanup_old_images()
        
        # 创建响应
        response = ImageEditResponse(
            id=f"img_edit_{uuid.uuid4().hex}",
            created=int(time.time()),
            model=request.model,
            data=data
        )
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图像编辑失败: {str(e)}")



@app.get("/images/{filename}")
async def download_image(filename: str):
    """下载生成的图片"""
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="image/png"
    )

@app.get("/images")
async def list_images():
    """列出所有可下载的图片"""
    try:
        files = list(OUTPUT_DIR.glob("*.png"))
        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)  # 按修改时间倒序排列
        
        image_list = []
        for file_path in files:
            stat = file_path.stat()
            image_list.append({
                "filename": file_path.name,
                "url": f"/images/{file_path.name}",
                "size": stat.st_size,
                "created": stat.st_mtime,
                "modified": stat.st_mtime
            })
        
        return {
            "total": len(image_list),
            "images": image_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取图片列表失败: {str(e)}")

@app.delete("/images/{filename}")
async def delete_image(filename: str):
    """删除指定的图片"""
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    
    try:
        file_path.unlink()
        return {"message": f"图片 {filename} 已删除"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除图片失败: {str(e)}")

@app.get("/images/stats")
async def get_image_stats():
    """获取图片统计信息"""
    try:
        files = list(OUTPUT_DIR.glob("*.png"))
        total_size = sum(f.stat().st_size for f in files)
        
        return {
            "total_images": len(files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "directory": str(OUTPUT_DIR)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")

@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy" if _pipe is not None else "loading", 
        "model_loaded": _pipe is not None, 
        "device": _device if _device else "unknown",
        "model_type": "Qwen-Image-Edit"
    }

@app.get("/")
async def root():
    """根端点 - 重定向到文件管理页面"""
    from fastapi.responses import RedirectResponse
    
    # 检查静态文件是否存在
    if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
        return RedirectResponse(url="/static/index.html")
    else:
        return {
            "message": "Qwen Image Edit API",
            "version": "1.0.0",
                    "endpoints": {
            "POST /v1/images/edits": "创建图像编辑 (JSON格式，支持图片URL和Base64，自动IP地址替换)",
            "GET /images/{filename}": "下载生成的图片",
            "GET /images": "列出所有可下载的图片",
            "GET /images/stats": "获取图片统计信息",
            "DELETE /images/{filename}": "删除指定的图片",
            "GET /health": "健康检查 (显示模型加载状态)",
            "GET /docs": "API文档"
        }
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=6003, reload=True)
