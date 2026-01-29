# 视频接口说明

## 目录
- [1. 通过 URL 处理视频](#1-通过-url-处理视频)
- [2. 上传文件处理视频](#2-上传文件处理视频)
- [3. 通过服务器本地路径处理](#3-通过服务器本地路径处理)

统一前缀：`/multimedia_piolt/video_edit/v1`
默认端口：`8003`

## 1. 通过 URL 处理视频
- Path: `/process_video_by_url/`
- Method: `POST`
- Content-Type: `application/json`
- 功能：下载 video/audio，合成视频，上传 MinIO（若可用）。

请求体
| 参数名 | 类型 | 必选 | 描述 |
| :--- | :--- | :--- | :--- |
| video_url | string | 是 | 视频文件 HTTP/HTTPS 地址 |
| audio_url | string | 是 | 音频文件 HTTP/HTTPS 地址 |
| text | string | 是 | 要叠加的字幕文本 |

响应体
| 字段 | 类型 | 描述 |
| :--- | :--- | :--- |
| status | string | 成功为 `success` |
| output_path | string | 处理后视频的本地路径 |
| minio_url | string | 上传成功时的 MinIO 下载链接 |
| message | string | 提示信息 |

示例
```bash
curl -X POST "http://localhost:8003/multimedia_piolt/video_edit/v1/process_video_by_url/" \
  -H "Content-Type: application/json" \
  -d '{
        "video_url": "https://example.com/video.mp4",
        "audio_url": "https://example.com/audio.mp3",
        "text": "这是测试字幕内容"
      }'
```

## 2. 上传文件处理视频
- Path: `/process_video/`
- Method: `POST`
- Content-Type: `multipart/form-data`
- 功能：上传本地视频并合成输出。

表单参数
| 参数名 | 类型 | 必选 | 描述 |
| :--- | :--- | :--- | :--- |
| video_file | file | 是 | 本地视频文件 |
| text | string | 是 | 要叠加的字幕文本 |

响应体
| 字段 | 类型 | 描述 |
| :--- | :--- | :--- |
| status | string | 成功为 `success` |
| output_path | string | 处理后视频的本地路径 |
| message | string | 提示信息 |

示例
```bash
curl -X POST "http://localhost:8003/multimedia_piolt/video_edit/v1/process_video/" \
  -F "video_file=@/path/to/local/video.mp4" \
  -F "text=这是测试字幕"
```

## 3. 通过服务器本地路径处理
- Path: `/process_video_by_path/`
- Method: `POST`
- Content-Type: `application/json`
- 功能：指定服务器已有的视频文件路径进行处理。

请求体
| 参数名 | 类型 | 必选 | 描述 |
| :--- | :--- | :--- | :--- |
| video_path | string | 是 | 服务器上视频文件的绝对路径 |
| text | string | 是 | 要叠加的字幕文本 |

响应体
| 字段 | 类型 | 描述 |
| :--- | :--- | :--- |
| status | string | 成功为 `success` |
| output_path | string | 处理后视频的本地路径 |

示例
```bash
curl -X POST "http://localhost:8003/multimedia_piolt/video_edit/v1/process_video_by_path/" \
  -H "Content-Type: application/json" \
  -d '{
        "video_path": "/media/source/model_deploy/multimedia_piolt/data/video/temp/test.mp4",
        "text": "测试本地路径处理"
      }'
```
