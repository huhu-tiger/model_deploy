import os.path
import time
from datetime import datetime
# from datetime import date
from minio import Minio
from minio.error import S3Error
import hashlib
from urllib.parse import urljoin, urlencode
import logging

logger = logging.getLogger(__name__)

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

        self.minio_client = Minio(endpoint=minio_server, access_key=access_key, secret_key=secret_key, secure=False)

        self.bucket_name = bucket_name
        self.minio_server = minio_server

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

    def upload_file(self, file_path, object_name=None, valid=True):
        err = False
        err_str = None
        object_name = os.path.basename(file_path)  # 存储在MinIO上的对象名称
        minio_put_path = self.generate_object_name(object_name=object_name)

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


# global_minio_conn = minio_process(access_key=config.BaseConfig.minio_access_key, secret_key=config.BaseConfig.minio_secret_key,
#                   minio_server=config.BaseConfig.minio_upload_url, bucket_name=config.BaseConfig.minio_bucket_name)

# def minio_upload_file_return_download_url(file_path):

#     upload_result = global_minio_conn.upload_file(file_path=file_path)
#     download_url = global_minio_conn.generate_download_url(os.path.basename(file_path))
#     return upload_result,download_url


if __name__ == "__main__":
    # 1. create minio conn
    m = minio_process(access_key="IoeOmDzCZOkM0CiF6IK3", secret_key="c5gKEUpeU1oirwTOmkbLtXKl0fiDCrtlkmEU0fIt",
                      minio_server="120.133.137.142:9000", bucket_name="files")
    # 2. upload file
    upload_result = m.upload_file(file_path="/data/work/pydev/README.md")
    print(f"upload result: {upload_result}")
    # 3. get list dir
    # list_files= m.list_files_in_directory(os.path.dirname(upload_result['minio_put_path']))
    # print(f"File list len: {len(list_files)}")
    #
    # # 4. download file
    if not upload_result['error']:
        m.download_file(prefix=upload_result['minio_put_path'],local_dir='/tmp')
    #
    # 4. delete file
    m.delete_file(prefix=upload_result['minio_put_path'])
    #
    # # 5. get list dir
    # list_files= m.list_files_in_directory(os.path.dirname(upload_result['minio_put_path']))
    # print(f"File list len: {len(list_files)}")


