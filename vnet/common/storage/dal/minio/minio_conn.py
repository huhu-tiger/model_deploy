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
from urllib.parse import urljoin, urlencode
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
        self.minio_client = Minio(
            endpoint=minio_server, 
            access_key=access_key, 
            secret_key=secret_key, 
            secure=False
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
        # 基础URL
        base_url = f"http://{self.minio_server}"

        # 具体路径
        path = f"{self.bucket_name}/{file_name}"

        # 查询参数
        # params = {
        #     "key1": "value1",
        #     "key2": "value2"
        # }

        # 拼接URL
        full_url = urljoin(base_url, path)
        # full_url = f"{url}?{urlencode(params)}"

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


class MinioSettings(BaseSettings):
    Minio_IP: str = Field(default=get_env("MINIO_IP", "120.133.137.142"), env="MINIO_IP")
    Minio_Upload_Port: int = Field(default=int(get_env("MINIO_UPLOAD_PORT", "9000")), env="MINIO_UPLOAD_PORT")
    Minio_Upload_Url: str = Field(
        default=get_env("MINIO_UPLOAD_URL", "http://120.133.137.142:9000"),
        env="MINIO_UPLOAD_URL",
    )
    Minio_Access_Key: str = Field(default=get_env("MINIO_ACCESS_KEY", "IoeOmDzCZOkM0CiF6IK3"), env="MINIO_ACCESS_KEY")
    Minio_Secret_Key: str = Field(
        default=get_env("MINIO_SECRET_KEY", "c5gKEUpeU1oirwTOmkbLtXKl0fiDCrtlkmEU0fIt"), env="MINIO_SECRET_KEY",
    )
    Minio_Bucket_Name: str = Field(default=get_env("MINIO_BUCKET_NAME", "files"), env="MINIO_BUCKET_NAME")


# Instantiate MinioSettings after loading environment variables
minio_settings = MinioSettings()

minio_handler = minio_process(
    access_key=minio_settings.Minio_Access_Key, 
    secret_key=minio_settings.Minio_Secret_Key,
    minio_server=f"{minio_settings.Minio_IP}:{minio_settings.Minio_Upload_Port}", 
    bucket_name=minio_settings.Minio_Bucket_Name
)


if __name__ == "__main__":
    # 1. create minio conn
    m = minio_process(access_key="IoeOmDzCZOkM0CiF6IK3", secret_key="c5gKEUpeU1oirwTOmkbLtXKl0fiDCrtlkmEU0fIt",
                      minio_server="120.133.137.142:9000", bucket_name="files")
    # 2. upload file
    upload_result1 = m.upload_file(file_path="/media/source/model_deploy/vnet/pip.txt")
    print(f"upload result: {upload_result1}")
    upload_result2 = m.upload_file(file_path="/media/source/model_deploy/vnet/pip.txt",upload_dir='test_dir')
    print(f"upload result: {upload_result2}")
    # 3. get list dir
    # list_files= m.list_files_in_directory(os.path.dirname(upload_result['minio_put_path']))
    # print(f"File list len: {len(list_files)}")
    #   
    # # 4. download file
    if not upload_result2['error']:
        m.download_file(prefix=upload_result2['minio_put_path'],local_dir='/tmp')
    #
    # 4. delete file
    # m.delete_file(prefix=upload_result['minio_put_path'])
    #
    # # 5. get list dir
    # list_files= m.list_files_in_directory(os.path.dirname(upload_result['minio_put_path']))
    # print(f"File list len: {len(list_files)}")
    ## 5. generate download url
    download_url= m.generate_download_url(file_name=upload_result2['minio_put_path'])
    print(f"download url: {download_url}")


