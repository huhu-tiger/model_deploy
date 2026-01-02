import os
import tempfile
import requests
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
import time
import asyncio
import aiohttp
import aiofiles

# 从环境变量获取超时配置,提供默认值
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "300"))  # 默认 300 秒 (5分钟)
DOWNLOAD_HEAD_TIMEOUT = int(os.getenv("DOWNLOAD_HEAD_TIMEOUT", "10"))  # 默认 10 秒

def download_file_via_http(url, proxy=None):
    """
    下载 HTTP 文件到临时目录，并返回临时文件路径。

    :param url: HTTP 文件的下载地址。
    :param proxy: 可选，HTTP 代理地址。
    :return: 下载的临时文件路径。
    """

    # 解析文件名
    parsed_url = urlparse(url)
    file_name = os.path.basename(parsed_url.path) or "downloaded_file"

    # 创建临时文件
    temp_dir = tempfile.gettempdir()
    temp_file_path = os.path.join(temp_dir, file_name)

    try:
        # 记录开始时间
        start_time = time.time()

        # 下载文件
        with requests.get(url, stream=True, proxies=proxy, timeout=DOWNLOAD_TIMEOUT) as response:
            response.raise_for_status()
            with open(temp_file_path, "wb") as temp_file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    temp_file.write(chunk)

        # 记录结束时间并计算用时
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Download completed in {elapsed_time:.2f} seconds.")

        return temp_file_path
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to download file: {e}")


def download_file_thread(url,proxy=None):
    # 解析文件名
    parsed_url = urlparse(url)
    file_name = os.path.basename(parsed_url.path) or "downloaded_file"

    # 创建临时文件
    temp_dir = tempfile.gettempdir()
    temp_file_path = os.path.join(temp_dir, file_name)
    THREADS = 8
    size = int(requests.head(url, timeout=DOWNLOAD_HEAD_TIMEOUT).headers["Content-Length"])
    chunk = size // THREADS

    def download(start, end, idx):
        headers = {"Range": f"bytes={start}-{end}"}
        r = requests.get(url, headers=headers, stream=True, proxies=proxy, timeout=DOWNLOAD_TIMEOUT)
        with open(f"{temp_file_path}.part{idx}", "wb") as f:
            for c in r.iter_content(1024 * 1024):
                f.write(c)

    # 记录开始时间
    start_time = time.time()

    with ThreadPoolExecutor(THREADS) as pool:
        for i in range(THREADS):
            pool.submit(
                download,
                i * chunk,
                size - 1 if i == THREADS - 1 else (i + 1) * chunk - 1,
                i,
            )

    # 合并
    with open(temp_file_path, "wb") as out:
        for i in range(THREADS):
            with open(f"{temp_file_path}.part{i}", "rb") as f:
                out.write(f.read())
            os.remove(f"{temp_file_path}.part{i}")

    # 记录结束时间并计算用时
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Download origin_http: {url},temp_file_path: {temp_file_path}, completed in {elapsed_time:.2f} seconds.")

    return temp_file_path


def multiple_download_thread(urls, proxy=None):
    """
    多线程下载多个文件。

    :param urls: 包含多个 HTTP 文件下载地址的列表。
    :param proxy: 可选，HTTP 代理地址。
    :return: 下载的临时文件路径列表。
    """
    downloaded_files = []

    with ThreadPoolExecutor(max_workers=len(urls)) as executor:
        futures = [executor.submit(download_file_via_http, url, proxy) for url in urls]
        for future in futures:
            try:
                downloaded_files.append(future.result())
            except Exception as e:
                print(f"Error downloading file: {e}")

    return downloaded_files


def _should_use_single_stream(url, proxy=None):
    # 对小文件或图片使用单连接下载，避免不必要的分块开销。
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        resp = requests.head(url, allow_redirects=True, proxies=proxies, timeout=DOWNLOAD_HEAD_TIMEOUT)
        content_length = int(resp.headers.get("Content-Length", 0) or 0)
        content_type = resp.headers.get("Content-Type", "").lower()

        if content_length and content_length <= 100 * 1024:
            return True
        if "image" in content_type:
            return True
    except Exception as e:
        print(f"HEAD request failed for {url}: {e}")
    return False


async def download_file_async(session, url, proxy=None):
    """
    异步下载单个文件。
    """
    try:
        parsed_url = urlparse(url)
        file_name = os.path.basename(parsed_url.path) or "downloaded_file"
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, file_name)

        # 处理代理：aiohttp 接受字符串
        proxy_url = proxy
        if isinstance(proxy, dict):
            # 优先使用 https，其次 http
            proxy_url = proxy.get("https") or proxy.get("http")

        async with session.get(url, proxy=proxy_url, timeout=DOWNLOAD_TIMEOUT) as response:
            response.raise_for_status()
            async with aiofiles.open(temp_file_path, 'wb') as f:
                async for chunk in response.content.iter_chunked(1024 * 1024):
                    await f.write(chunk)
        return url, temp_file_path, None
    except Exception as e:
        return url, None, str(e)


async def multiple_download_async(urls, proxy=None):
    """
    异步并发下载多个文件。
    """
    downloaded_files = {}
    
    # 限制并发数
    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for url in urls:
            tasks.append(download_file_async(session, url, proxy))
        
        results = await asyncio.gather(*tasks)
        
        for url, path, error in results:
            if error:
                print(f"Error downloading file {url}: {error}")
                downloaded_files[url] = None
            else:
                downloaded_files[url] = path
                
    return downloaded_files

if __name__ == "__main__":
    test_url = "https://cdn1.suno.ai/56cb7d08-604b-41ad-932c-3a0fab5db506.mp3"
    # downloaded_path = download_file_via_http(test_url,proxy="http://192.168.0.2:20171")
    # print(f"File downloaded to: {downloaded_path}")

    downloaded_path_thread = download_file_thread(test_url,proxy="http://192.168.0.2:20171")
    print(f"File downloaded to: {downloaded_path_thread}")

    test_urls = [
        "https://cdn1.suno.ai/56cb7d08-604b-41ad-932c-3a0fab5db506.mp3",
        "https://cdn2.suno.ai/image_56cb7d08-604b-41ad-932c-3a0fab5db506.jpeg",
        "https://cdn1.suno.ai/77272629-327b-4500-9fcf-33cb2e231819.mp3",
        "https://cdn1.suno.ai/8321e5f1-6545-4304-90eb-069ce032e599.mp3",
        "https://cdn2.suno.ai/image_8321e5f1-6545-4304-90eb-069ce032e599.jpeg"
    ]
    downloaded_files = multiple_download_async(test_urls,proxy="http://192.168.0.2:20171")
    for url, path in downloaded_files.items():
        print(f"File from {url} downloaded to: {path}")