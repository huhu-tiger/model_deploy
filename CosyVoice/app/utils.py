import os
from urllib.parse import urlparse, unquote
import requests
# utils 
def get_filename_from_url(url: str) -> str:
    """
    从 URL 中提取文件名。

    :param url: 文件的下载链接。
    :return: 从 URL 中提取的文件名。
    """
    # 解析 URL
    parsed_url = urlparse(url)

    # 提取路径中的最后部分，即文件名
    filename = os.path.basename(parsed_url.path)

    return filename


def download_file(url: str, destination_path: str):
    """
    从给定的 URL 下载文件并保存到本地。

    :param url: 下载链接的 URL。
    :param destination_path: 文件保存的目标路径（包括文件名）。
    """
    try:
        # 发送 GET 请求并流式下载文件
        response = requests.get(url, stream=True)

        # 如果请求成功（状态码200），开始下载文件
        if response.status_code == 200:
            with open(destination_path, 'wb') as file:
                # 分块下载文件
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
            print(f"File successfully downloaded to {destination_path}")
            return True
        else:
            print(f"Failed to download file, status code: {response.status_code}")
            return False

    except Exception as e:
        print(f"Error downloading file: {str(e)}")
        return False




