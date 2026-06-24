#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PaddleOCR-VL FastAPI 服务
提供 /v1/layout-parsing 接口
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel
from typing import Optional, Union
import os
import time
import uuid
from datetime import datetime
import tempfile
import shutil
from paddleocr import PaddleOCRVL
import asyncio
import aiofiles

# ==================== 配置变量 ====================
# 基础路径配置（以当前脚本所在目录为项目根目录）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "official_models")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
WORK_DIR = os.path.join(BASE_DIR, "work")

# 环境变量配置
PADDLEX_CACHE_HOME = MODEL_DIR
HF_HOME = os.path.join(MODEL_DIR, "huggingface")

# 模型路径配置（统一使用 official_models/PaddleOCR-VL）
VL_MODEL_DIR = os.path.join(MODEL_DIR, "PaddleOCR-VL")
LAYOUT_MODEL_DIR = os.path.join(VL_MODEL_DIR, "PP-DocLayoutV2")
LAYOUT_MODEL_NAME = "PP-DocLayoutV2"
VL_REC_MODEL_NAME = "PaddleOCR-VL-0.9B"
PIPELINE_VERSION = "v1"

# 服务配置
VLM_SERVER_URL = "http://127.0.0.1:8080/v1"
API_HOST = "0.0.0.0"
API_PORT = 8000

# 输出文件配置
MERGED_OUTPUT_FILENAME = "merged_output.md"
DEFAULT_DOWNLOAD_FILENAME = "document_parsed.md"  # 默认下载文件名
PAGE_JSON_PREFIX = "page_"
PAGE_MD_PREFIX = "page_"
PAGE_JSON_SUFFIX = "_res.json"
PAGE_MD_SUFFIX = ".md"

# 创建FastAPI应用
app = FastAPI(
    title="PaddleOCR-VL API",
    description="基于PaddleOCR-VL的文档解析API服务",
    version="1.0.0"
)

# 全局变量存储pipeline
pipeline = None

# 请求模型
class LayoutParsingRequest(BaseModel):
    file_url: Optional[str] = None
    file_path: Optional[str] = None
    output_format: Optional[str] = "markdown"  # 支持 "markdown" 或 "json"

class LayoutParsingResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None
    request_id: str
    timestamp: str

# 初始化PaddleOCR-VL
def initialize_pipeline():
    """初始化PaddleOCR-VL pipeline"""
    global pipeline

    if pipeline is not None:
        return pipeline

    # 设置环境变量
    os.environ['PADDLEX_CACHE_HOME'] = PADDLEX_CACHE_HOME
    os.environ['HF_HOME'] = HF_HOME

    # 创建目录
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(HF_HOME, exist_ok=True)

    print(f"初始化PaddleOCR-VL pipeline...")
    print(f"模型存储路径: {MODEL_DIR}")

    try:
        pipeline = PaddleOCRVL(
            pipeline_version=PIPELINE_VERSION,
            layout_detection_model_name=LAYOUT_MODEL_NAME,
            layout_detection_model_dir=LAYOUT_MODEL_DIR,
            vl_rec_model_name=VL_REC_MODEL_NAME,
            vl_rec_model_dir=VL_MODEL_DIR,
            vl_rec_backend="vllm-server",
            vl_rec_server_url=VLM_SERVER_URL,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
        )
        print("PaddleOCR-VL pipeline 初始化成功！")
        return pipeline
    except Exception as e:
        print(f"PaddleOCR-VL pipeline 初始化失败: {e}")
        raise e

# 创建输出目录
def create_output_dir():
    """创建带时间戳的输出目录"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    request_id = str(uuid.uuid4())[:8]
    output_dir = os.path.join(OUTPUT_DIR, f"{timestamp}_{request_id}")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir, request_id

# 创建Markdown响应
def create_markdown_response(content: str, filename: str = None):
    """创建带有文件名的Markdown响应"""
    if filename is None:
        filename = DEFAULT_DOWNLOAD_FILENAME

    # 确保文件名有.md扩展名
    if not filename.endswith('.md'):
        filename += '.md'

    return Response(
        content=content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/markdown; charset=utf-8"
        }
    )

# 处理文件
async def process_file(file_path: str, output_dir: str) -> dict:
    """处理文件并返回结果"""
    global pipeline

    if pipeline is None:
        pipeline = initialize_pipeline()

    try:
        # 处理文档
        print(f"开始处理文件: {file_path}")
        output = pipeline.predict(file_path)

        # 获取每页的markdown内容
        markdown_list = [res._to_markdown() for res in output]

        # 使用内置方法合并所有页面的markdown内容
        combined_markdown = pipeline.concatenate_markdown_pages(markdown_list)

        # 保存合并后的markdown文件
        merged_path = os.path.join(output_dir, MERGED_OUTPUT_FILENAME)
        async with aiofiles.open(merged_path, 'w', encoding='utf-8') as f:
            await f.write(combined_markdown)

        # 保存单独的页面文件并收集JSON内容
        page_files = []
        json_contents = []
        for i, res in enumerate(output):
            # 保存JSON格式
            json_filename = f"{PAGE_JSON_PREFIX}{i}{PAGE_JSON_SUFFIX}"
            res.save_to_json(save_path=output_dir)

            # 查找实际保存的JSON文件（因为save_to_json可能使用原始文件名）
            json_file_path = None
            # 首先尝试期望的文件名
            expected_json_path = os.path.join(output_dir, json_filename)
            if os.path.exists(expected_json_path):
                json_file_path = expected_json_path
            else:
                # 如果期望的文件名不存在，查找所有以_res.json结尾的文件
                for file_name in os.listdir(output_dir):
                    if file_name.endswith(PAGE_JSON_SUFFIX):
                        json_file_path = os.path.join(output_dir, file_name)
                        print(f"找到JSON文件: {file_name}")
                        break

            if json_file_path and os.path.exists(json_file_path):
                try:
                    with open(json_file_path, 'r', encoding='utf-8') as f:
                        json_content = f.read()
                        json_contents.append(json_content)
                except Exception as e:
                    print(f"读取JSON文件失败: {e}")
                    json_contents.append("{}")
            else:
                print(f"未找到JSON文件，尝试直接获取结果对象的JSON数据")
                # 如果文件不存在，尝试直接从结果对象获取JSON数据
                try:
                    # 尝试获取结果对象的JSON表示
                    import json
                    if hasattr(res, 'to_dict'):
                        json_data = res.to_dict()
                        json_contents.append(json.dumps(json_data, ensure_ascii=False, indent=2))
                    elif hasattr(res, '__dict__'):
                        json_data = res.__dict__
                        json_contents.append(json.dumps(json_data, ensure_ascii=False, indent=2))
                    else:
                        json_contents.append("{}")
                except Exception as e:
                    print(f"获取JSON数据失败: {e}")
                    json_contents.append("{}")

            # 保存Markdown格式
            md_filename = f"{PAGE_MD_PREFIX}{i}{PAGE_MD_SUFFIX}"
            res.save_to_markdown(save_path=output_dir)

            page_files.append({
                "page": i,
                "json_file": json_filename,
                "markdown_file": md_filename
            })

        return {
            "merged_markdown": combined_markdown,
            "merged_file": MERGED_OUTPUT_FILENAME,
            "page_files": page_files,
            "total_pages": len(output),
            "output_directory": output_dir,
            "raw_output": output,  # 添加原始输出结果
            "json_contents": json_contents  # 添加JSON文件内容
        }

    except Exception as e:
        print(f"处理文件时出错: {e}")
        raise HTTPException(status_code=500, detail=f"文件处理失败: {str(e)}")

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化pipeline"""
    print("正在启动PaddleOCR-VL API服务...")
    try:
        initialize_pipeline()
        print("服务启动成功！")
    except Exception as e:
        print(f"服务启动失败: {e}")

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "PaddleOCR-VL API服务",
        "version": "1.0.0",
        "endpoints": {
            "layout_parsing": "/v1/layout-parsing (POST) - 文档解析，支持output_format参数控制返回Markdown或JSON",
            "get_result": "/v1/layout-parsing/{request_id} (GET) - 返回Markdown内容",
            "get_details": "/v1/layout-parsing/{request_id}/details (GET) - 返回JSON详细信息",
            "health": "/health"
        }
    }

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "pipeline_initialized": pipeline is not None
    }

@app.post("/v1/layout-parsing")
async def layout_parsing(
    file: Optional[UploadFile] = File(None),
    file_url: Optional[str] = Form(None),
    file_path: Optional[str] = Form(None),
    output_format: Optional[str] = Form("markdown")
):
    """
    文档布局解析接口

    支持三种输入方式：
    1. 上传文件 (file)
    2. 文件URL (file_url)
    3. 本地文件路径 (file_path)

    参数:
    - output_format: 返回格式，支持 "markdown" 或 "json"，默认为 "markdown"

    返回:
    - 当 output_format="markdown" 时，返回合并后的Markdown文件内容
    - 当 output_format="json" 时，返回save_to_json保存的JSON文件内容（所有页面的JSON数据数组）
    """

    # 创建输出目录
    output_dir, request_id = create_output_dir()

    try:
        # 处理不同的输入方式
        if file is not None:
            # 处理上传的文件
            print(f"处理上传文件: {file.filename}")

            # 保存上传的文件到临时目录
            temp_dir = tempfile.mkdtemp()
            file_path = os.path.join(temp_dir, file.filename)

            async with aiofiles.open(file_path, 'wb') as f:
                content = await file.read()
                await f.write(content)

            # 处理文件
            result = await process_file(file_path, output_dir)

            # 清理临时文件
            shutil.rmtree(temp_dir, ignore_errors=True)

        elif file_url is not None:
            # 处理URL文件
            print(f"处理URL文件: {file_url}")
            result = await process_file(file_url, output_dir)

        elif file_path is not None:
            # 处理本地文件路径
            print(f"处理本地文件: {file_path}")

            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="文件不存在")

            result = await process_file(file_path, output_dir)

        else:
            raise HTTPException(status_code=400, detail="请提供文件、文件URL或文件路径")

        # 根据 output_format 参数决定返回格式
        if output_format and output_format.lower() == "json":
            # 返回保存的JSON文件内容，按页码组织
            import json

            # 按页码组织JSON内容
            pages_json = {}
            for i, json_content in enumerate(result["json_contents"]):
                try:
                    # 解析JSON字符串为Python对象
                    json_obj = json.loads(json_content)
                    pages_json[f"page_{i}"] = json_obj
                except json.JSONDecodeError as e:
                    print(f"解析第{i}页JSON内容失败: {e}")
                    # 如果解析失败，添加错误信息
                    pages_json[f"page_{i}"] = {"error": f"JSON解析失败: {str(e)}"}

            # 添加元数据信息
            response_data = {
                "request_id": request_id,
                "total_pages": result["total_pages"],
                "output_directory": result["output_directory"],
                "pages": pages_json
            }

            return response_data
        else:
            # 默认返回Markdown内容
            return create_markdown_response(result["merged_markdown"])

    except HTTPException:
        raise
    except Exception as e:
        print(f"处理请求时出错: {e}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")

@app.get("/v1/layout-parsing/{request_id}")
async def get_result(request_id: str):
    """获取处理结果 - 返回Markdown内容"""
    # 查找对应的输出目录
    if not os.path.exists(OUTPUT_DIR):
        raise HTTPException(status_code=404, detail="输出目录不存在")

    # 查找匹配的目录
    for dir_name in os.listdir(OUTPUT_DIR):
        if request_id in dir_name:
            result_dir = os.path.join(OUTPUT_DIR, dir_name)

            # 检查合并后的文件是否存在
            merged_file = os.path.join(result_dir, MERGED_OUTPUT_FILENAME)
            if os.path.exists(merged_file):
                try:
                    with open(merged_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    return create_markdown_response(content)
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"读取结果文件失败: {str(e)}")

    raise HTTPException(status_code=404, detail="未找到对应的处理结果")

@app.get("/v1/layout-parsing/{request_id}/details")
async def get_result_details(request_id: str):
    """获取处理结果详细信息 - 返回JSON格式"""
    # 查找对应的输出目录
    if not os.path.exists(OUTPUT_DIR):
        raise HTTPException(status_code=404, detail="输出目录不存在")

    # 查找匹配的目录
    for dir_name in os.listdir(OUTPUT_DIR):
        if request_id in dir_name:
            result_dir = os.path.join(OUTPUT_DIR, dir_name)

            # 检查合并后的文件是否存在
            merged_file = os.path.join(result_dir, MERGED_OUTPUT_FILENAME)
            if os.path.exists(merged_file):
                try:
                    with open(merged_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # 获取页面文件列表
                    page_files = []
                    for file_name in os.listdir(result_dir):
                        if file_name.startswith(PAGE_JSON_PREFIX) and file_name.endswith(PAGE_JSON_SUFFIX):
                            page_num = file_name.replace(PAGE_JSON_PREFIX, "").replace(PAGE_JSON_SUFFIX, "")
                            md_file = f"{PAGE_MD_PREFIX}{page_num}{PAGE_MD_SUFFIX}"
                            if os.path.exists(os.path.join(result_dir, md_file)):
                                page_files.append({
                                    "page": int(page_num),
                                    "json_file": file_name,
                                    "markdown_file": md_file
                                })

                    return {
                        "success": True,
                        "request_id": request_id,
                        "merged_markdown": content,
                        "merged_file": MERGED_OUTPUT_FILENAME,
                        "page_files": sorted(page_files, key=lambda x: x["page"]),
                        "total_pages": len(page_files),
                        "output_directory": result_dir
                    }
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"读取结果文件失败: {str(e)}")

    raise HTTPException(status_code=404, detail="未找到对应的处理结果")

def main():
    """启动FastAPI服务"""

    # 设置环境变量
    os.environ['PADDLEX_CACHE_HOME'] = PADDLEX_CACHE_HOME
    os.environ['HF_HOME'] = HF_HOME

    # 创建必要的目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)

    print("启动PaddleOCR-VL FastAPI服务...")
    print(f"服务地址: http://{API_HOST}:{API_PORT}")
    print(f"API文档: http://{API_HOST}:{API_PORT}/docs")
    print(f"健康检查: http://{API_HOST}:{API_PORT}/health")

    # 启动服务
    import uvicorn
    uvicorn.run(
        "fastapi_app:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main()
