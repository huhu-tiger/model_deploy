from aiohttp import web, ClientSession, ClientTimeout
import os
import io
import re
import logging
import mimetypes
import asyncio
from urllib.parse import urlparse
from urllib.parse import quote as urllib_parse_quote
import folder_paths
import node_helpers
from pydantic_settings import BaseSettings
from pydantic import Field
from io import BytesIO
from PIL import Image

logger = logging.getLogger(__name__)

from vnet.common.storage.dal.minio.minio_conn import minio_process

class MinioSettings(BaseSettings):
    Minio_IP: str = Field(default="120.133.137.142", env="MINIO_IP")
    Minio_Upload_Port: int = Field(default=9000, env="MINIO_UPLOAD_PORT")
    Minio_Upload_Url: str = Field(default="http://120.133.137.142:9000", env="MINIO_UPLOAD_URL")
    Minio_Access_Key: str = Field(default="IoeOmDzCZOkM0CiF6IK3", env="MINIO_ACCESS_KEY")
    Minio_Secret_Key: str = Field(default="c5gKEUpeU1oirwTOmkbLtXKl0fiDCrtlkmEU0fIt", env="MINIO_SECRET_KEY")
    Minio_Bucket_Name: str = Field(default="files", env="MINIO_BUCKET_NAME")


minio_settings = MinioSettings()
minio_handler = minio_process(access_key=minio_settings.Minio_Access_Key, secret_key=minio_settings.Minio_Secret_Key,
                              minio_server=f"{minio_settings.Minio_IP}:{minio_settings.Minio_Upload_Port}", bucket_name=minio_settings.Minio_Bucket_Name)


async def compare_image_hash(filepath, image):
    hasher = node_helpers.hasher()

    # function to compare hashes of two images to see if it already exists, fix to #3465
    if os.path.exists(filepath):
        a = hasher()
        b = hasher()
        with open(filepath, "rb") as f:
            a.update(f.read())
        # 处理异步读取（multipart part 的 read() 是异步的）
        if hasattr(image.file, 'read'):
            import inspect
            if inspect.iscoroutinefunction(image.file.read):
                # 异步读取
                content = await image.file.read()
                b.update(content)
                # multipart part 不支持 seek，但我们可以重新读取或使用其他方法
            else:
                # 同步读取
                content = image.file.read()
                b.update(content)
                
        return a.hexdigest() == b.hexdigest()
    return False

def get_dir_by_type(dir_type):
    if dir_type is None:
        dir_type = "input"

    if dir_type == "input":
        type_dir = folder_paths.get_input_directory()
    elif dir_type == "temp":
        type_dir = folder_paths.get_temp_directory()
    elif dir_type == "output":
        type_dir = folder_paths.get_output_directory()

    return type_dir, dir_type
    

def is_valid_url(string: str) -> bool:
    """判断字符串是否为有效的 URL"""
    try:
        result = urlparse(string)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


class FileWrapper:
    """包装下载的文件，使其行为类似于上传的文件对象"""
    def __init__(self, file_content: bytes, filename: str):
        self.file = io.BytesIO(file_content)
        self.filename = filename


async def download_file_from_url(url: str) -> tuple[bytes, str]:
    """从 URL 下载文件并返回文件内容和文件名"""
    try:
        parsed_url = urlparse(url)
        # 从 URL 中提取文件名
        filename = os.path.basename(parsed_url.path)
        if not filename or '.' not in filename:
            # 如果无法从 URL 获取文件名，使用默认名称
            filename = "downloaded_file"
        
        timeout_cfg = ClientTimeout(total=30)
        async with ClientSession(timeout=timeout_cfg) as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                content = await resp.read()
                # 如果响应头中有文件名，优先使用
                content_disposition = resp.headers.get('Content-Disposition', '')
                if 'filename=' in content_disposition:
                    match = re.search(r'filename="?([^"]+)"?', content_disposition)
                    if match:
                        filename = match.group(1)
                
                return content, filename
    except Exception as e:
        raise ValueError(f"下载文件失败: {str(e)}")

    
async def image_upload(post, image_save_function=None):
    image = post.get("image")
    overwrite = post.get("overwrite")
    image_is_duplicate = False

    # 处理字符串值中的引号（curl 命令中可能包含引号）
    if isinstance(overwrite, str):
        overwrite = overwrite.strip('"\'')

    image_upload_type = post.get("type")
    if isinstance(image_upload_type, str):
        image_upload_type = image_upload_type.strip('"\'')
    
    upload_dir, image_upload_type = get_dir_by_type(image_upload_type)

    # 判断 image 是文件对象还是 URL 字符串
    is_url_input = False
    if isinstance(image, str):
        # 去除可能的引号
        image = image.strip('"\'')
        if is_valid_url(image):
            # 如果是 URL，下载文件
            is_url_input = True
            try:
                file_content, downloaded_filename = await download_file_from_url(image)
                # 创建文件包装对象，使其行为类似于上传的文件
                image = FileWrapper(file_content, downloaded_filename)
            except Exception as e:
                logger.error(f"下载文件失败: {str(e)}")
                return web.Response(status=400, text=f"下载文件失败: {str(e)}")
    
    # 检查 image 是否为文件对象（支持 aiohttp 的 FileField 和我们的 FileWrapper）
    # 直接检查 image.file，与 server.py 保持一致
    if image and hasattr(image, 'file') and image.file:
        filename = image.filename
        if not filename:
            return web.Response(status=400)

        subfolder = post.get("subfolder", "")
        # 处理字符串值中的引号
        if isinstance(subfolder, str):
            subfolder = subfolder.strip('"\'')
        full_output_folder = os.path.join(upload_dir, os.path.normpath(subfolder))
        filepath = os.path.abspath(os.path.join(full_output_folder, filename))

        if os.path.commonpath((upload_dir, filepath)) != upload_dir:
            return web.Response(status=400)

        if not os.path.exists(full_output_folder):
            os.makedirs(full_output_folder)

        split = os.path.splitext(filename)

        if overwrite is not None and (overwrite == "true" or overwrite == "1"):
            pass
        else:
            i = 1
            while os.path.exists(filepath):
                if await compare_image_hash(filepath, image): #compare hash to prevent saving of duplicates with same name, fix for #3465
                    image_is_duplicate = True
                    break
                filename = f"{split[0]} ({i}){split[1]}"
                filepath = os.path.join(full_output_folder, filename)
                i += 1

        if not image_is_duplicate:
            if image_save_function is not None:
                image_save_function(image, post, filepath)
            else:
                # 处理不同类型的文件对象
                if hasattr(image.file, 'read'):
                    import inspect
                    if inspect.iscoroutinefunction(image.file.read):
                        # 异步读取（multipart part）
                        content = await image.file.read()
                    else:
                        # 同步读取（FileWrapper 或普通文件对象）
                        content = image.file.read()
                elif isinstance(image.file, bytes):
                    # 如果已经是 bytes，直接使用
                    content = image.file
                else:
                    # 尝试转换为 bytes
                    content = bytes(image.file) if hasattr(image.file, '__bytes__') else image.file
                
                with open(filepath, "wb") as f:
                    f.write(content)

        return web.json_response({"name" : filename, "subfolder": subfolder, "type": image_upload_type})
    else:
        # 提供更详细的错误信息用于调试
        error_msg = "无效的请求"
        if image is None:
            error_msg = "缺少 'image' 字段"
        elif isinstance(image, str):
            # 如果是字符串但不是有效的 URL，或者 URL 下载失败
            if is_valid_url(image):
                error_msg = f"'image' 字段是 URL 但下载失败: {image}"
            else:
                error_msg = f"'image' 字段是字符串但不是有效的 URL，期望文件对象或 URL: {image[:100]}"
        elif not hasattr(image, 'file'):
            error_msg = f"'image' 字段类型不正确，期望文件对象或 URL 字符串，得到: {type(image).__name__}"
        elif not image.file:
            error_msg = "文件对象为空"
        logger.error(f"上传失败: {error_msg}")
        return web.Response(status=400, text=error_msg)

def define_view(routes,PromptServer_instance):
    @routes.get("/task_output")
    async def task_output(request):

        prompt_id = request.rel_url.query.get("prompt_id")
        timeout_s = int(request.rel_url.query.get("timeout", "600"))
        poll_interval = float(request.rel_url.query.get("interval", "1.0"))
        if not prompt_id:
            return web.json_response({"success": False, "error": "missing prompt_id"}, status=400)

        start_time = asyncio.get_event_loop().time()

        result_payload = None
        # 轮询任务结果
        while True:
            history_entry = PromptServer_instance.prompt_queue.get_history(prompt_id=prompt_id)
            logger.info(f"history_entry: {history_entry}")
            if history_entry is not None:
                # history_entry 可能是 {prompt_id: {...}}
                entry = history_entry.get(prompt_id) if isinstance(history_entry, dict) and prompt_id in history_entry else history_entry
                status_obj = entry.get("status") or {}
                status_str = status_obj.get("status_str")
                completed = status_obj.get("completed") is True
                outputs = entry.get("outputs") or {}

                if status_str == "success" and completed:
                    # 收集所有输出文件并上传到 MinIO
                    download_urls = []
                    files = []
                    upload_errors = []
                    
                    for node_id, node_out in outputs.items():
                        # 常见键：images、gifs、videos、files 等
                        for key in ("images", "gifs", "videos", "files"):
                            items = node_out.get(key) or []
                            for item in items:
                                filename = item.get("filename") or item.get("name")
                                subfolder = item.get("subfolder", "")
                                ftype = item.get("type", "output")
                                if not filename:
                                    continue
                                
                                # 构建文件完整路径
                                output_dir = folder_paths.get_directory_by_type(ftype)
                                if output_dir is None:
                                    error_msg = f"无法获取类型 {ftype} 的目录"
                                    logger.error(error_msg)
                                    upload_errors.append(f"{filename}: {error_msg}")
                                    continue
                                
                                if subfolder:
                                    full_output_dir = os.path.join(output_dir, os.path.normpath(subfolder))
                                    # 安全检查：防止路径遍历
                                    if os.path.commonpath((os.path.abspath(full_output_dir), output_dir)) != output_dir:
                                        error_msg = f"无效的子文件夹路径: {subfolder}"
                                        logger.error(error_msg)
                                        upload_errors.append(f"{filename}: {error_msg}")
                                        continue
                                    output_dir = full_output_dir
                                
                                file_path = os.path.join(output_dir, filename)
                                
                                # 检查文件是否存在
                                if not os.path.isfile(file_path):
                                    error_msg = f"文件不存在: {file_path}"
                                    logger.warning(error_msg)
                                    upload_errors.append(f"{filename}: {error_msg}")
                                    continue
                                
                                # 上传文件到 MinIO
                                try:
                                    upload_result = minio_handler.upload_file(file_path=file_path)
                                    if upload_result.get("error"):
                                        err_str = upload_result.get("error_str", "upload error")
                                        error_msg = f"MinIO 上传失败: {err_str}"
                                        logger.error(f"{filename}: {error_msg}")
                                        upload_errors.append(f"{filename}: {error_msg}")
                                        continue
                                    
                                    minio_object_path = upload_result.get("minio_put_path")
                                    minio_download_url = minio_handler.generate_download_url(minio_object_path)
                                    
                                    download_urls.append(minio_download_url)
                                    files.append({
                                        "filename": filename,
                                        "subfolder": subfolder,
                                        "type": ftype,
                                        "url": minio_download_url,
                                        "minio_path": minio_object_path,
                                        "node_id": node_id,
                                        "kind": key,
                                    })
                                    logger.info(f"文件 {filename} 已成功上传到 MinIO: {minio_download_url}")
                                except Exception as e:
                                    error_msg = f"上传到 MinIO 时发生异常: {str(e)}"
                                    logger.error(f"{filename}: {error_msg}", exc_info=True)
                                    upload_errors.append(f"{filename}: {error_msg}")
                    
                    result_payload = {
                        "success": True,
                        "status": status_obj,
                        "prompt_id": prompt_id,
                        "download_urls": download_urls,
                        "files": files,
                        "raw": entry,
                    }
                    if upload_errors:
                        result_payload["upload_errors"] = upload_errors
                        logger.warning(f"部分文件上传失败: {upload_errors}")
                    break

                # 失败/错误状态
                if status_str in ("error", "failed"):
                    result_payload = {
                        "success": False,
                        "status": status_obj,
                        "prompt_id": prompt_id,
                        "raw": entry,
                    }
                    break

            # 超时检查
            now = asyncio.get_event_loop().time()
            if now - start_time > timeout_s:
                result_payload = {"success": False, "error": "timeout", "prompt_id": prompt_id}
                break
            await asyncio.sleep(poll_interval)

        return web.json_response(result_payload)

    @routes.post("/upload/anything")
    async def upload_anthing(request):
        try:
            # 记录请求头信息（使用print确保能看到）
            content_type = request.headers.get('Content-Type', '')
            print(f"[UPLOAD DEBUG] 收到上传请求，Content-Type: {content_type}")
            logger.info(f"收到上传请求，Content-Type: {content_type}")
            
            # 使用 multipart reader 来确保所有字段（包括文件）都被正确解析
            # 注意：request.post() 可能不会返回文件字段，所以直接使用 multipart reader
            post = {}
            reader = await request.multipart()
            
            while True:
                part = await reader.next()
                if part is None:
                    break
                
                name = part.name
                if part.filename:
                    # 这是文件字段，需要包装成类似 FileField 的对象
                    print(f"[UPLOAD DEBUG] 找到文件字段: {name}, filename: {part.filename}")
                    
                    class MultipartFileWrapper:
                        def __init__(self, part):
                            self.part = part
                            self.filename = part.filename
                            # aiohttp 的 FileField 有 file 属性，这里我们使用 part 本身
                            self.file = part
                    
                    post[name] = MultipartFileWrapper(part)
                    print(f"[UPLOAD DEBUG] 文件字段 '{name}' 已包装，filename: {post[name].filename}")
                else:
                    # 这是普通文本字段
                    value = await part.read(decode=True)
                    post[name] = value.decode('utf-8') if value else ''
                    print(f"[UPLOAD DEBUG] 找到文本字段: {name}, 值: {post[name][:100]}")
            
            print(f"[UPLOAD DEBUG] 使用 multipart reader 解析完成，共 {len(post)} 个字段")
            
            # 记录所有接收到的键（使用print确保能看到）
            post_keys = list(post.keys())
            print(f"[UPLOAD DEBUG] 接收到的 POST 数据键: {post_keys}")
            print(f"[UPLOAD DEBUG] POST 数据项数量: {len(post)}")
            logger.info(f"接收到的 POST 数据键: {post_keys}")
            logger.info(f"POST 数据项数量: {len(post)}")
            
            # 详细记录每个字段
            for key in post_keys:
                value = post.get(key)
                if value:
                    value_type = type(value).__name__
                    if hasattr(value, 'filename'):
                        info_str = f"字段 '{key}': 类型={value_type}, filename={value.filename}, 有file属性={hasattr(value, 'file')}"
                    elif hasattr(value, 'read'):  # 可能是文件对象
                        info_str = f"字段 '{key}': 类型={value_type}, 可能是文件对象（有read方法）"
                    else:
                        info_str = f"字段 '{key}': 类型={value_type}, 值={str(value)[:100]}"
                    print(f"[UPLOAD DEBUG] {info_str}")
                    logger.info(info_str)
                else:
                    print(f"[UPLOAD DEBUG] 字段 '{key}': 值为 None")
                    logger.info(f"字段 '{key}': 值为 None")
            
            image = post.get("image")
            image_info = f"image 字段: {image is not None}, 类型: {type(image).__name__ if image else 'None'}"
            print(f"[UPLOAD DEBUG] {image_info}")
            logger.info(image_info)
            
            if image:
                has_file_info = f"image 是否有 file 属性: {hasattr(image, 'file')}"
                print(f"[UPLOAD DEBUG] {has_file_info}")
                logger.info(has_file_info)
                if hasattr(image, 'file'):
                    file_info = f"image.file: {image.file is not None}, filename: {getattr(image, 'filename', 'N/A')}"
                    print(f"[UPLOAD DEBUG] {file_info}")
                    logger.info(file_info)
            else:
                print(f"[UPLOAD DEBUG] image 字段为 None，所有字段: {post_keys}")
                logger.warning(f"image 字段为 None，所有字段: {post_keys}")
            
            return await image_upload(post)
        except Exception as e:
            error_msg = f"处理上传请求时出错: {str(e)}"
            print(f"[UPLOAD DEBUG] ERROR: {error_msg}")
            import traceback
            print(f"[UPLOAD DEBUG] 错误堆栈: {traceback.format_exc()}")
            logger.error(error_msg, exc_info=True)
            return web.Response(status=500, text=f"服务器错误: {str(e)}")

    @routes.get("/view_url")
    async def view_image(request):
        # 明确打印到控制台，避免被日志等级过滤
        print(f"[VIEW_URL DEBUG] request: {request}")
        print(f"[VIEW_URL DEBUG] query: {dict(request.rel_url.query)}")
        logger.info(f"request: {request}")
        if "filename" in request.rel_url.query:
            filename = request.rel_url.query["filename"]
            filename, output_dir = folder_paths.annotated_filepath(filename)

            if not filename:
                return web.Response(status=400)

            # validation for security: prevent accessing arbitrary path
            if filename[0] == '/' or '..' in filename:
                return web.Response(status=400)

            if output_dir is None:
                type = request.rel_url.query.get("type", "output")
                output_dir = folder_paths.get_directory_by_type(type)

            if output_dir is None:
                return web.Response(status=400)

            if "subfolder" in request.rel_url.query:
                full_output_dir = os.path.join(output_dir, request.rel_url.query["subfolder"])
                if os.path.commonpath((os.path.abspath(full_output_dir), output_dir)) != output_dir:
                    return web.Response(status=403)
                output_dir = full_output_dir

            filename = os.path.basename(filename)
            file = os.path.join(output_dir, filename)

            if os.path.isfile(file):

                # 如果指定 upload_to_minio，则将文件上传到 MinIO 并返回下载地址
                upload_flag = request.rel_url.query.get("upload_to_minio", "0").lower()
                if upload_flag in ("1", "true", "yes"): 
                    try:
                        upload_result = minio_handler.upload_file(file_path=file)
                        if upload_result.get("error"):
                            err_str = upload_result.get("error_str", "upload error")
                            return web.json_response({
                                "success": False,
                                "error": err_str
                            }, status=500)
                        minio_object_path = upload_result.get("minio_put_path")
                        download_url = minio_handler.generate_download_url(minio_object_path)
                        return web.json_response({
                            "success": True,
                            "minio_path": minio_object_path,
                            "download_url": download_url
                        })
                    except Exception as e:
                        logger.error(f"MinIO 上传失败: {str(e)}", exc_info=True)
                        return web.json_response({
                            "success": False,
                            "error": str(e)
                        }, status=500)
                if 'preview' in request.rel_url.query:
                    with Image.open(file) as img:
                        preview_info = request.rel_url.query['preview'].split(';')
                        image_format = preview_info[0]
                        if image_format not in ['webp', 'jpeg'] or 'a' in request.rel_url.query.get('channel', ''):
                            image_format = 'webp'

                        quality = 90
                        if preview_info[-1].isdigit():
                            quality = int(preview_info[-1])

                        buffer = BytesIO()
                        if image_format in ['jpeg'] or request.rel_url.query.get('channel', '') == 'rgb':
                            img = img.convert("RGB")
                        img.save(buffer, format=image_format, quality=quality)
                        buffer.seek(0)

                        return web.Response(body=buffer.read(), content_type=f'image/{image_format}',
                                            headers={"Content-Disposition": f"filename=\"{filename}\""})

                if 'channel' not in request.rel_url.query:
                    channel = 'rgba'
                else:
                    channel = request.rel_url.query["channel"]

                if channel == 'rgb':
                    with Image.open(file) as img:
                        if img.mode == "RGBA":
                            r, g, b, a = img.split()
                            new_img = Image.merge('RGB', (r, g, b))
                        else:
                            new_img = img.convert("RGB")

                        buffer = BytesIO()
                        new_img.save(buffer, format='PNG')
                        buffer.seek(0)

                        return web.Response(body=buffer.read(), content_type='image/png',
                                            headers={"Content-Disposition": f"filename=\"{filename}\""})

                elif channel == 'a':
                    with Image.open(file) as img:
                        if img.mode == "RGBA":
                            _, _, _, a = img.split()
                        else:
                            a = Image.new('L', img.size, 255)

                        # alpha img
                        alpha_img = Image.new('RGBA', img.size)
                        alpha_img.putalpha(a)
                        alpha_buffer = BytesIO()
                        alpha_img.save(alpha_buffer, format='PNG')
                        alpha_buffer.seek(0)

                        return web.Response(body=alpha_buffer.read(), content_type='image/png',
                                            headers={"Content-Disposition": f"filename=\"{filename}\""})
                else:
                    # Get content type from mimetype, defaulting to 'application/octet-stream'
                    content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

                    # For security, force certain mimetypes to download instead of display
                    if content_type in {'text/html', 'text/html-sandboxed', 'application/xhtml+xml', 'text/javascript', 'text/css'}:
                        content_type = 'application/octet-stream'  # Forces download

                    return web.FileResponse(
                        file,
                        headers={
                            "Content-Disposition": f"filename=\"{filename}\"",
                            "Content-Type": content_type
                        }
                    )

        return web.Response(status=404)