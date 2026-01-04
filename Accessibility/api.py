import sys
import os
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from jsonpath_ng.ext import parse
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s:%(filename)s:%(lineno)d - %(message)s",
)
logger = logging.getLogger("accessibility")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(BASE_DIR))

from vnet.common.config.env import load_env
load_env(dotenv_path=os.path.join(BASE_DIR, ".env"), override=False)

from vnet.common.storage.dal.minio.minio_conn import minio_handler
from vnet.common.tools.http_utils import multiple_download_async

app = FastAPI(title="Accessibility API", version="1.0.0")

class DownloadRequest(BaseModel):
    download_url_jsonpath: List[str]
    data: List[Dict[str, Any]]

def extract_urls(jsonpaths: List[str], data: dict) -> List[str]:
    urls = []
    for path_str in jsonpaths:
        try:
            expr = parse(path_str)
            matches = expr.find(data)
            urls.extend([
                m.value for m in matches if isinstance(m.value, str) and m.value.startswith("http")
            ])
        except Exception as e:
            logger.error(f"Jsonpath解析失败: {path_str}: {e}")
    return urls

def upload_files(downloaded_files: dict) -> dict:
    url_map = {}
    for url, local_path in downloaded_files.items():
        if not local_path or not os.path.exists(local_path):
            logger.error(f"下载文件不存在: {url}, 路径: {local_path}")
            continue
        try:
            upload = minio_handler.upload_file(local_path, upload_dir="accessibility_downloads")
            if upload.get("error"):
                logger.error(f"上传失败: {local_path}: {upload.get('error_str')}")
                continue
            put_path = upload.get("minio_put_path")
            download_url = minio_handler.generate_download_url(put_path) if put_path else None
            final_url = download_url or put_path
            if not final_url:
                logger.error(f"未生成下载链接: {url}, put_path: {put_path}")
                continue
            url_map[url] = final_url
            logger.info(f"上传成功: {url} -> {final_url}")
        finally:
            try:
                os.remove(local_path)
            except Exception:
                pass
    return url_map

def replace_urls(jsonpaths: List[str], data: dict, url_map: dict) -> int:
    replaced = 0
    for path_str in jsonpaths:
        try:
            expr = parse(path_str)
            matches = expr.find(data)
            for match in matches:
                old_url = match.value
                if isinstance(old_url, str) and old_url in url_map:
                    expr.update(data, url_map[old_url])
                    replaced += 1
        except Exception as e:
            logger.error(f"Jsonpath更新失败: {path_str}: {e}")
    return replaced

@app.post("/v1/download-and-upload")
async def download_and_upload(request: DownloadRequest):
    search_data = {"data": request.data}
    logger.info(f"请求jsonpath: {request.download_url_jsonpath}")
    logger.info(f"请求数据量: {len(request.data)}")
    try:
        urls = extract_urls(request.download_url_jsonpath, search_data)
        logger.info(f"提取到{len(urls)}个url")
        if not urls:
            return search_data
        proxy = (
            {"http": os.getenv("HTTP_PROXY"), "https": os.getenv("HTTPS_PROXY")}
            if os.getenv("HTTP_PROXY") else None
        )
        downloaded_files = await multiple_download_async(urls, proxy=proxy)
        url_map = upload_files(downloaded_files)
        logger.info(f"替换url映射: {url_map}")
        replaced = replace_urls(request.download_url_jsonpath, search_data, url_map)
        logger.info(f"替换了{replaced}个url")
        return search_data
    except Exception as e:
        logger.exception("处理失败")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=6003, reload=True)