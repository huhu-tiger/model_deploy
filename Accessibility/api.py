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
# Add parent directory to sys.path to allow importing vnet
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(BASE_DIR))

from vnet.common.config.env import load_env
load_env(dotenv_path=os.path.join(BASE_DIR, ".env"), override=False)

from vnet.common.storage.dal.minio.minio_conn import minio_handler
from vnet.common.tools.http_utils import multiple_download_thread_with_thread, multiple_download_async

app = FastAPI(title="Accessibility API", version="1.0.0")

class DownloadRequest(BaseModel):
    download_url_jsonpath: List[str]
    data: List[Dict[str, Any]]

@app.post("/v1/download-and-upload")
async def download_and_upload(request: DownloadRequest):
    try:
        # Wrap data to match jsonpath expectation (assuming paths start with $.data)
        search_data = {"data": request.data}
        logger.info(f"Incoming jsonpaths: {request.download_url_jsonpath}")
        logger.info(f"Incoming items: {len(request.data)}")

        all_matches = []
        # Extract URLs from all jsonpaths
        for path_str in request.download_url_jsonpath:
            try:
                jsonpath_expr = parse(path_str)
                matches = jsonpath_expr.find(search_data)
                all_matches.extend(matches)
            except Exception as e:
                logger.error(f"Error parsing jsonpath {path_str}: {e}")
                continue

        urls = [match.value for match in all_matches if isinstance(match.value, str) and match.value.startswith("http")]
        logger.info(f"Found {len(urls)} url candidates from {len(all_matches)} matches")
        
        if not urls:
            return search_data

        proxy = {
            "http": os.getenv("HTTP_PROXY"),
            "https": os.getenv("HTTPS_PROXY")
        } if os.getenv("HTTP_PROXY") else None

        logger.info(f"Proxy: {proxy}")
        # Download files
        downloaded_files = await multiple_download_async(urls, proxy=proxy)
        logger.info(f"Downloaded files: {downloaded_files}")
        url_map = {}
        # Upload to MinIO
        for url, local_path in downloaded_files.items():
            if not local_path or not os.path.exists(local_path):
                logger.error(f"Downloaded file missing for {url}, path: {local_path}")
                continue
            
            try:   
                # Use a specific bucket or directory
                upload = minio_handler.upload_file(local_path, upload_dir="accessibility_downloads")
                if upload.get("error"):
                    logger.error(f"Upload failed for {local_path}: {upload.get('error_str')}")
                    continue

                put_path = upload.get("minio_put_path")
                download_url = minio_handler.generate_download_url(put_path) if put_path else None
                # 如果预签名失败，则回退存储路径，避免不替换
                final_url = download_url or put_path
                if not final_url:
                    logger.error(f"No download url generated for {url}, put_path: {put_path}")
                    continue
                url_map[url] = final_url
                logger.info(f"Uploaded {url} -> {final_url}")
            finally:
                try:
                    os.remove(local_path)
                except Exception:
                    pass
        logging.info(f"URL map for replacement: {url_map}")
        
        # Update data using jsonpath-ng-ext's update capability
        replaced = 0
        for path_str in request.download_url_jsonpath:
            try:
                jsonpath_expr = parse(path_str)
                # Find all matches for this path
                matches = jsonpath_expr.find(search_data)
                for match in matches:
                    old_url = match.value
                    if isinstance(old_url, str) and old_url in url_map:
                        # Update the value using jsonpath-ng-ext's update method
                        jsonpath_expr.update(search_data, url_map[old_url])
                        replaced += 1
                        logger.debug(f"Replaced {old_url} -> {url_map[old_url]}")
            except Exception as e:
                logger.error(f"Error updating jsonpath {path_str}: {e}")
                continue

        logger.info(f"Replaced {replaced} urls out of {len(url_map)} mappings")

        logger.info(f"Response sample: {search_data}")

        return search_data

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=6003, reload=True)