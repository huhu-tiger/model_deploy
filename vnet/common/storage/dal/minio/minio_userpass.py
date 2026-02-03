"""
MinIO 用户名密码登录与上传（MinioApiUploader / minio_process）。

运行方式（需在 conda 虚拟环境中）:
  conda activate <环境名>   # 如 conda activate multimedia_piolt
  cd /media/source/model_deploy
  python -m vnet.common.storage.dal.minio.minio_userpass
  或直接: python vnet/common/storage/dal/minio/minio_userpass.py
"""
import os.path
import time
from datetime import datetime
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field
import sys

# 确保项目根目录在 sys.path，便于导入 vnet.common.config.env
PROJECT_ROOT = Path(__file__).resolve().parents[5]  # /media/source/model_deploy
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from vnet.common.config.env import get_env

from minio import Minio
from minio.error import S3Error
import hashlib
import json
from urllib.parse import urljoin, urlencode, urlparse, urlunparse
import logging
import urllib3
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

def calculate_md5(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


class RunError(Exception):
    def __init__(self, ErrorInfo):
        super().__init__(self)  # 初始化父类
        self.errorinfo = ErrorInfo

    def __str__(self):
        return self.errorinfo


class minio_process():
    def __init__(self, access_key, secret_key, bucket_name, minio_server, **kwargs):
        # 配置MinIO服务器连接参数
        # 将 Minio 服务器地址添加到 NO_PROXY 环境变量，确保不走系统代理
        minio_host = minio_server.split(':')[0] if ':' in minio_server else minio_server
        
        # 更新 NO_PROXY 环境变量
        current_no_proxy = os.environ.get('NO_PROXY', '')
        if current_no_proxy:
            no_proxy_list = set(current_no_proxy.split(','))
            no_proxy_list.add(minio_host)
            no_proxy_list.add(minio_server)
            os.environ['NO_PROXY'] = ','.join(no_proxy_list)
        else:
            os.environ['NO_PROXY'] = f"{minio_host},{minio_server}"
        
        # 更新 no_proxy 环境变量（小写）
        current_no_proxy_lower = os.environ.get('no_proxy', '')
        if current_no_proxy_lower:
            no_proxy_list_lower = set(current_no_proxy_lower.split(','))
            no_proxy_list_lower.add(minio_host)
            no_proxy_list_lower.add(minio_server)
            os.environ['no_proxy'] = ','.join(no_proxy_list_lower)
        else:
            os.environ['no_proxy'] = f"{minio_host},{minio_server}"
        
        # 配置 urllib3 禁用警告
        urllib3.disable_warnings()
        
        # 初始化 Minio 客户端
        # 根据端口判断是否使用 HTTPS
        use_https = ':443' in minio_server or minio_server.startswith('https://')
        # 移除协议前缀(如果有)
        clean_server = minio_server.replace('https://', '').replace('http://', '')
        
        self.minio_client = Minio(
            endpoint=clean_server,
            access_key=access_key,
            secret_key=secret_key,
            secure=use_https,  # 根据端口自动判断
            http_client=urllib3.PoolManager(
                cert_reqs="CERT_NONE",  # 禁用 SSL 证书验证
            )
            if use_https
            else None,
        )

        self.bucket_name = bucket_name
        self.minio_server = minio_server
        self.minio_host = minio_host

    @staticmethod
    def generate_object_name(user="test", object_name=None):
        # 获取今天的日期
        timestamp = str(int(time.time()))
        formatted_today = datetime.now().strftime('%Y-%m-%d')
        return f"{formatted_today}/{timestamp}/{object_name}"

    def generate_download_url(self,file_name):
        # 根据是否使用 secure 决定协议
        protocol = "https" if self.minio_client._base_url.is_https else "http"
        base_url = f"{protocol}://{self.minio_server}"

        # 具体路径
        path = f"{self.bucket_name}/{file_name}"

        # 拼接URL
        full_url = urljoin(base_url, path)

        return full_url

    def list_files_in_directory(self, prefix):
        """列出存储桶中指定目录下的所有文件和子目录"""
        try:
            # 确保前缀以斜杠结束，代表目录
            if not prefix.endswith('/'):
                prefix += '/'
            object_list = self.minio_client.list_objects(self.bucket_name, prefix=prefix, recursive=True)
            return list(object_list)
            # for obj in object_list:
            #     print(f"Object: {obj.object_name}, Size: {obj.size}")
        except S3Error as e:
            logger.error(f"Error: {e}")
            return []

    def upload_file(self, file_path, upload_dir=None, object_name=None, valid=True):
        err = False
        err_str = None
        base_name = os.path.basename(file_path)

        # 目标对象路径：可选目录 + 自动生成日期/时间 + 对象名
        minio_put_path = self.generate_object_name(object_name=(object_name or base_name))
        if upload_dir:
            minio_put_path = f"{upload_dir.rstrip('/')}/{minio_put_path}"

        try:
            wresult = self.minio_client.fput_object(self.bucket_name,
                                                    minio_put_path,
                                                    file_path)
            if valid:
                etag = wresult.etag
                # Multipart uploads (indicated by '-') have special ETags that don't match simple file MD5
                if '-' not in etag:
                    cmd5 = calculate_md5(file_path)
                    if etag != cmd5:
                        err_str = f"ETag: {etag}, neq {file_path} hash {cmd5}"
                        err = True
            logger.info(f"File {file_path} [Minio]uploaded successfully as {object_name} to bucket {self.bucket_name}")

        except S3Error as e:
            logger.error(f"Error: {e}")
            err_str = str(e)
            err = True
        except Exception as e:
            logger.error(f"Error: {e}")
            err_str = str(e)
            err = True
        return {"error": err, "error_str": err_str, "minio_put_path": minio_put_path, "local_file_path": file_path}
    def download_file(self, local_dir,prefix: str):
        err_str = None
        err = False
        local_file_path=''
        try:
            file_stat = self.minio_client.stat_object(self.bucket_name, prefix)
            local_file_path=os.path.join(local_dir,os.path.basename(file_stat.object_name))
            self.minio_client.fget_object(self.bucket_name, prefix, local_file_path)
            logger.info(f"File {prefix} [Minio]downloaded successfully as {local_file_path} to bucket {self.bucket_name}")
        except S3Error as e:
            logger.error(f"Error: {e}")
            err_str = str(e)
            err = True
        return {"error": err, "error_str": err_str, "minio_path": prefix, "local_file_path": local_file_path}

    def delete_file(self, prefix):
        err_str = None
        err = False
        """从指定存储桶中删除一个文件"""
        try:
            self.minio_client.remove_object(self.bucket_name, prefix)
            logger.info(f"File '{prefix}' has been deleted from bucket '{self.bucket_name}'.")
        except S3Error as e:
            logger.error(f"Error during file deletion: {e}")
            err_str = f"Error during file deletion: {e}"
            err = True
        return {"error": err, "error_str": err_str, "minio_path": prefix}


class _MinioPathPrefixPoolManager(urllib3.PoolManager):
    """urllib3 PoolManager 子类：在请求 URL 路径前加上 nginx 代理路径（如 /fileserver_api）。"""

    def __init__(self, path_prefix: str, **kwargs):
        super().__init__(**kwargs)
        self._path_prefix = path_prefix.rstrip("/")

    def urlopen(self, method, url, redirect=True, **kwargs):
        parsed = urlparse(url)
        prefix = self._path_prefix
        path = parsed.path if parsed.path else "/"
        new_path = f"{prefix}{path}" if path.startswith("/") else f"{prefix}/{path}"
        new_url = urlunparse((parsed.scheme, parsed.netloc, new_path, parsed.params, parsed.query, parsed.fragment))
        return super().urlopen(method, new_url, redirect=redirect, **kwargs)


class MinioApiUploader:
    """
    通过 MinIO 用户名密码以 API 方式登录并上传文件的独立类。
    使用 access_key 作为用户名、secret_key 作为密码，连接 MinIO S3 兼容 API。
    """

    def __init__(
        self,
        endpoint: str,
        username: str,
        password: str,
        bucket_name: str,
        download_base_url: str | None = None,
        api_path: str | None = None,
        **kwargs,
    ):
        """
        Args:
            endpoint: MinIO 服务地址，如 "host:443" 或 "https://wan.vnet.com"
            username: 对应 MinIO access_key（API 用户名）
            password: 对应 MinIO secret_key（API 密码）
            bucket_name: 存储桶名称
            download_base_url: 下载地址的 API 基地址（如 MINIO_UPLOAD_URL），用于拼接 基地址/桶/对象路径 得到直链
            api_path: nginx 代理路径前缀（如 /fileserver_api），请求时会拼到 URL 路径前
        """
        # 解析 endpoint，去掉协议前缀，仅保留 host:port（不含路径）
        clean_endpoint = endpoint.replace("https://", "").replace("http://", "").strip()
        if "/" in clean_endpoint:
            clean_endpoint = clean_endpoint.split("/")[0]
        minio_host = clean_endpoint.split(":")[0] if ":" in clean_endpoint else clean_endpoint

        # 确保 MinIO 不走系统代理
        current_no_proxy = os.environ.get("NO_PROXY", "")
        if current_no_proxy:
            no_proxy_list = set(current_no_proxy.split(","))
            no_proxy_list.add(minio_host)
            no_proxy_list.add(clean_endpoint)
            os.environ["NO_PROXY"] = ",".join(no_proxy_list)
        else:
            os.environ["NO_PROXY"] = f"{minio_host},{clean_endpoint}"

        current_no_proxy_lower = os.environ.get("no_proxy", "")
        if current_no_proxy_lower:
            no_proxy_list_lower = set(current_no_proxy_lower.split(","))
            no_proxy_list_lower.add(minio_host)
            no_proxy_list_lower.add(clean_endpoint)
            os.environ["no_proxy"] = ",".join(no_proxy_list_lower)
        else:
            os.environ["no_proxy"] = f"{minio_host},{clean_endpoint}"

        urllib3.disable_warnings()
        use_https = ":443" in clean_endpoint or endpoint.strip().lower().startswith("https://")

        # 使用 nginx 代理路径时，用自定义 PoolManager 在请求路径前加 api_path（如 /fileserver_api）
        path_prefix = (api_path or "").strip().rstrip("/")
        if path_prefix and not path_prefix.startswith("/"):
            path_prefix = "/" + path_prefix
        if use_https:
            http_client = (
                _MinioPathPrefixPoolManager(path_prefix, cert_reqs="CERT_NONE")
                if path_prefix
                else urllib3.PoolManager(cert_reqs="CERT_NONE")
            )
        else:
            http_client = _MinioPathPrefixPoolManager(path_prefix) if path_prefix else None

        # 使用用户名密码登录：MinIO S3 API 以 access_key/secret_key 表示，即 MINIO_ROOT_USER / MINIO_ROOT_PASSWORD
        self._client = Minio(
            endpoint=clean_endpoint,
            access_key=username,   # 用户名（MINIO_ROOT_USER）
            secret_key=password,   # 密码（MINIO_ROOT_PASSWORD）
            secure=use_https,
            http_client=http_client,
        )
        self.bucket_name = bucket_name
        self.endpoint = clean_endpoint
        self._download_base_url = (download_base_url or "").rstrip("/")

    def generate_download_url(self, object_name: str) -> str:
        """通过拼接 API 基地址 + 桶路径 + 对象路径，得到直接可下载的文件地址。"""
        if self._download_base_url:
            return f"{self._download_base_url}/{self.bucket_name}/{object_name}"
        protocol = "https" if self._client._base_url.is_https else "http"
        base_url = f"{protocol}://{self.endpoint}"
        path = f"{self.bucket_name}/{object_name}"
        return urljoin(base_url, path)

    def _public_bucket_policy(self) -> str:
        """生成桶公开读的 policy（s3:GetObject 允许所有人）。"""
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": ["s3:GetBucketLocation", "s3:ListBucket"],
                    "Resource": f"arn:aws:s3:::{self.bucket_name}",
                },
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{self.bucket_name}/*",
                },
            ],
        }
        return json.dumps(policy)

    def login(self) -> bool:
        """
        校验用户名密码；若桶不存在则创建桶，并将桶设置为 public 读权限。
        Returns:
            True 表示登录成功，False 表示失败。
        """
        try:
            if not self._client.bucket_exists(self.bucket_name):
                self._client.make_bucket(self.bucket_name)
                logger.info("MinioApiUploader: bucket %s created", self.bucket_name)
            self._client.set_bucket_policy(
                self.bucket_name,
                self._public_bucket_policy(),
            )
            logger.info("MinioApiUploader: bucket %s set to public read", self.bucket_name)
            return True
        except S3Error as e:
            logger.warning("MinioApiUploader login check failed: %s", e)
            return False
        except Exception as e:
            # 服务器返回非 XML（如 HTML 错误页）时 minio 解析会抛 ParseError，多为 endpoint/反向代理配置问题
            logger.warning(
                "MinioApiUploader login failed (endpoint or proxy?): %s: %s",
                type(e).__name__,
                e,
            )
            return False

    def upload_file(
        self,
        file_path: str,
        object_name: str | None = None,
        upload_dir: str | None = None,
        valid: bool = True,
    ) -> dict:
        """
        上传本地文件到 MinIO。

        Args:
            file_path: 本地文件路径
            object_name: 对象名，默认使用本地文件名
            upload_dir: 可选前缀目录
            valid: 是否校验上传后 ETag 与本地 MD5

        Returns:
            {"error": bool, "error_str": str|None, "minio_put_path": str, "local_file_path": str, "download_url": str}
        """
        err = False
        err_str = None
        base_name = os.path.basename(file_path)
        minio_put_path = minio_process.generate_object_name(object_name=(object_name or base_name))
        if upload_dir:
            minio_put_path = f"{upload_dir.rstrip('/')}/{minio_put_path}"

        try:
            result = self._client.fput_object(
                self.bucket_name,
                minio_put_path,
                file_path,
            )
            if valid:
                etag = result.etag
                if etag and "-" not in etag:
                    cmd5 = calculate_md5(file_path)
                    if etag != cmd5:
                        err_str = f"ETag: {etag}, neq {file_path} hash {cmd5}"
                        err = True
            logger.info(
                "MinioApiUploader: file %s uploaded as %s to bucket %s",
                file_path,
                minio_put_path,
                self.bucket_name,
            )
        except S3Error as e:
            logger.error("MinioApiUploader upload S3Error: %s", e)
            err_str = str(e)
            err = True
        except Exception as e:
            logger.error("MinioApiUploader upload Error: %s", e)
            err_str = str(e)
            err = True

        download_url = self.generate_download_url(minio_put_path)
        return {
            "error": err,
            "error_str": err_str,
            "minio_put_path": minio_put_path,
            "local_file_path": file_path,
            "download_url": download_url,
        }


class MinioSettings(BaseSettings):
    """API 连接直连 MinIO 端口（MINIO_IP:MINIO_UPLOAD_PORT）；下载直链用 Minio_Upload_Url（nginx 反向代理路径）。"""

    model_config = {"env_file": ".env", "extra": "ignore"}

    # API 连接地址；走 nginx 代理时用域名:443，并设置 MINIO_API_PATH=/fileserver_api
    Minio_IP: str = Field(default="wan.vnet.com", validation_alias="MINIO_IP")
    Minio_Upload_Port: int = Field(default=443, validation_alias="MINIO_UPLOAD_PORT")
    # nginx 反向代理 MinIO 的域名路径，仅用于生成下载直链，如 https://wan.vnet.com/fileserver_api
    Minio_Upload_Url: str = Field(
        default="https://wan.vnet.com/fileserver_api",
        validation_alias="MINIO_UPLOAD_URL",
    )
    # nginx 代理的 API 路径前缀，请求时会拼到 URL 路径前，如 /fileserver_api（与 Minio_Upload_Url 路径一致）
    Minio_Api_Path: str = Field(default="/fileserver_api", validation_alias="MINIO_API_PATH")
    # 与 docker-compose 一致：用户名/密码（MINIO_ROOT_USER / MINIO_ROOT_PASSWORD）
    Minio_Root_User: str = Field(default="admin", validation_alias="MINIO_ROOT_USER")
    Minio_Root_Password: str = Field(
        default="21VIAnet@Mod!106",
        validation_alias="MINIO_ROOT_PASSWORD",
    )
    # 桶名仅允许小写字母、数字、连字符，不能含下划线（S3 规范）
    Minio_Bucket_Name: str = Field(default="files-models", validation_alias="MINIO_BUCKET_NAME")


# Instantiate MinioSettings after loading environment variables
minio_settings = MinioSettings()

# minio_handler = minio_process(
#     access_key=minio_settings.Minio_Root_User,
#     secret_key=minio_settings.Minio_Root_Password,
#     minio_server=f"{minio_settings.Minio_IP}:{minio_settings.Minio_Upload_Port}",
#     bucket_name=minio_settings.Minio_Bucket_Name,
# )

# nginx 反向代理 MinIO，域名路径 https://wan.vnet.com/fileserver_api，下载直链示例：
# https://wan.vnet.com/fileserver_api/files/docker_upload/2026-02-03/1770083445/pip.txt


if __name__ == "__main__":
    # 请先 conda activate <环境名> 再运行；Endpoint 等可通过 .env 覆盖
    api_uploader = MinioApiUploader(
        endpoint=f"{minio_settings.Minio_IP}:{minio_settings.Minio_Upload_Port}",
        username=minio_settings.Minio_Root_User,
        password=minio_settings.Minio_Root_Password,
        bucket_name=minio_settings.Minio_Bucket_Name,
        download_base_url=minio_settings.Minio_Upload_Url,
        api_path=minio_settings.Minio_Api_Path,
    )
    if api_uploader.login():
        print("MinioApiUploader 登录成功")
        # 上传文件（可改为实际本地路径）
        sample_file = "/media/source/model_deploy/vnet/common/storage/dal/minio/yudie.mp3"
        if os.path.isfile(sample_file):
            result = api_uploader.upload_file(sample_file, upload_dir="docker_upload")
            if result["error"]:
                print("上传失败:", result["error_str"])
            else:
                print("上传成功:", result["minio_put_path"])
                print("下载地址:", result["download_url"])
        else:
            print("示例文件不存在，请指定 file_path 调用 upload_file()")
    else:
        print("MinioApiUploader 登录失败，请检查 endpoint/用户名/密码及桶是否存在")
        print("  若经 nginx 反向代理，API 需直连 MinIO 端口：.env 中设置 MINIO_IP=MinIO 宿主机 IP，MINIO_UPLOAD_PORT=31088，并确保该端口可访问")