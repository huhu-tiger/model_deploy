# 编写辅助下载接口

## 需求: 从接口入参的对象中获取URL,并下载文件到本地，上传minio，返回minio下载地址。 接口返回对象

### 请求示例
```json
{ 
    "download_url_jsonpath": ["$.data[*].audio_url", "$.data[*].video_url", "$.data[*].image_url", "$.data[*].image_large_url","$.data[*].avatar_image_url"],
    "data": [
            {
                "status": "complete",
                "title": "宁静钢琴冥想",
                "play_count": 0,
                "upvote_count": 0,
                "allow_comments": true,
                "id": "56cb7d08-604b-41ad-932c-3a0fab5db506",
                "entity_type": "song_schema",
                "video_url": "",
                "audio_url": "https://cdn1.suno.ai/56cb7d08-604b-41ad-932c-3a0fab5db506.mp3",
                "image_url": "https://cdn2.suno.ai/image_56cb7d08-604b-41ad-932c-3a0fab5db506.jpeg",
                "image_large_url": "https://cdn2.suno.ai/image_large_56cb7d08-604b-41ad-932c-3a0fab5db506.jpeg",
                "major_model_version": "v3.5",
                "model_name": "chirp-v3",
                "metadata": {
                    "tags": "古典",
                    "prompt": "一段平静舒缓的钢琴曲，带有柔和的旋律",
                    "type": "gen",
                    "duration": 186,
                    "refund_credits": false,
                    "stream": true,
                    "make_instrumental": true,
                    "control_sliders": {
                        "audio_weight": 0.65,
                        "style_weight": 0.65,
                        "weirdness_constraint": 0.65
                    },
                    "can_remix": true,
                    "is_remix": false,
                    "priority": 0,
                    "has_stem": false,
                    "uses_latest_model": false,
                    "model_badges": {
                        "songrow": {
                            "display_name": "v3.5",
                            "light": {
                                "text_color": "7D7C83",
                                "background_color": "00000000",
                                "border_color": "0000001A"
                            },
                            "dark": {
                                "text_color": "A3A3A3",
                                "background_color": "00000000",
                                "border_color": "FFFFFF1A"
                            }
                        }
                    }
                },
                "is_liked": false,
                "user_id": "b84baab3-2550-4c45-96a9-99bead3103e4",
                "handle": "nnhkluradpf",
                "is_handle_updated": true,
                "avatar_image_url": "https://cdn1.suno.ai/sAura12.jpg",
                "is_trashed": false,
                "created_at": "2025-12-30T05:07:49.836Z",
                "is_public": false,
                "explicit": false,
                "comment_count": 0,
                "flag_count": 0,
                "is_contest_clip": false,
                "has_hook": false,
                "batch_index": 0
            },
            {
                "status": "complete",
                "title": "宁静钢琴冥想",
                "play_count": 0,
                "upvote_count": 0,
                "allow_comments": true,
                "id": "9a5d32f1-fd18-4ea8-aad3-c78b55244bf2",
                "entity_type": "song_schema",
                "video_url": "",
                "audio_url": "https://cdn1.suno.ai/9a5d32f1-fd18-4ea8-aad3-c78b55244bf2.mp3",
                "image_url": "https://cdn2.suno.ai/image_9a5d32f1-fd18-4ea8-aad3-c78b55244bf2.jpeg",
                "image_large_url": "https://cdn2.suno.ai/image_large_9a5d32f1-fd18-4ea8-aad3-c78b55244bf2.jpeg",
                "major_model_version": "v3.5",
                "model_name": "chirp-v3",
                "metadata": {
                    "tags": "古典",
                    "prompt": "一段平静舒缓的钢琴曲，带有柔和的旋律",
                    "type": "gen",
                    "duration": 146,
                    "refund_credits": false,
                    "stream": true,
                    "make_instrumental": true,
                    "control_sliders": {
                        "audio_weight": 0.65,
                        "style_weight": 0.65,
                        "weirdness_constraint": 0.65
                    },
                    "can_remix": true,
                    "is_remix": false,
                    "priority": 0,
                    "has_stem": false,
                    "uses_latest_model": false,
                    "model_badges": {
                        "songrow": {
                            "display_name": "v3.5",
                            "light": {
                                "text_color": "7D7C83",
                                "background_color": "00000000",
                                "border_color": "0000001A"
                            },
                            "dark": {
                                "text_color": "A3A3A3",
                                "background_color": "00000000",
                                "border_color": "FFFFFF1A"
                            }
                        }
                    }
                },
                "is_liked": false,
                "user_id": "b84baab3-2550-4c45-96a9-99bead3103e4",
                "handle": "nnhkluradpf",
                "is_handle_updated": true,
                "avatar_image_url": "https://cdn1.suno.ai/sAura12.jpg",
                "is_trashed": false,
                "created_at": "2025-12-30T05:07:49.837Z",
                "is_public": false,
                "explicit": false,
                "comment_count": 0,
                "flag_count": 0,
                "is_contest_clip": false,
                "has_hook": false,
                "batch_index": 1
            },
            {
                "status": "complete",
                "title": "宁静钢琴冥想",
                "play_count": 0,
                "upvote_count": 0,
                "allow_comments": true,
                "id": "77272629-327b-4500-9fcf-33cb2e231819",
                "entity_type": "song_schema",
                "video_url": "",
                "audio_url": "https://cdn1.suno.ai/77272629-327b-4500-9fcf-33cb2e231819.mp3",
                "image_url": "https://cdn2.suno.ai/image_77272629-327b-4500-9fcf-33cb2e231819.jpeg",
                "image_large_url": "https://cdn2.suno.ai/image_large_77272629-327b-4500-9fcf-33cb2e231819.jpeg",
                "major_model_version": "v5",
                "model_name": "chirp-crow",
                "metadata": {
                    "tags": "古典",
                    "prompt": "一段平静舒缓的钢琴曲，带有柔和的旋律",
                    "type": "preview",
                    "duration": 45,
                    "refund_credits": false,
                    "stream": true,
                    "make_instrumental": true,
                    "control_sliders": {
                        "audio_weight": 0.65,
                        "style_weight": 0.65,
                        "weirdness_constraint": 0.65
                    },
                    "can_remix": false,
                    "is_remix": false,
                    "priority": 0,
                    "has_stem": false,
                    "uses_latest_model": true,
                    "model_badges": {
                        "songcard": {
                            "display_name": "v5 Preview",
                            "light": {
                                "text_color": "FD429C",
                                "background_color": "0000004D",
                                "border_color": "00000000"
                            },
                            "dark": {
                                "text_color": "FD429C",
                                "background_color": "0000004D",
                                "border_color": "00000000"
                            }
                        },
                        "songrow": {
                            "display_name": "v5 Preview",
                            "light": {
                                "text_color": "FD429C",
                                "background_color": "FD429C1A",
                                "border_color": "00000000"
                            },
                            "dark": {
                                "text_color": "FD429C",
                                "background_color": "FD429C40",
                                "border_color": "00000000"
                            }
                        }
                    }
                },
                "is_liked": false,
                "user_id": "b84baab3-2550-4c45-96a9-99bead3103e4",
                "handle": "nnhkluradpf",
                "is_handle_updated": true,
                "avatar_image_url": "https://cdn1.suno.ai/sAura12.jpg",
                "is_trashed": false,
                "created_at": "2025-12-30T05:07:49.751Z",
                "is_public": false,
                "explicit": false,
                "comment_count": 0,
                "flag_count": 0,
                "is_contest_clip": false,
                "preview_seconds": 600,
                "has_hook": false,
                "batch_index": 0
            },
            {
                "status": "complete",
                "title": "宁静钢琴冥想",
                "play_count": 0,
                "upvote_count": 0,
                "allow_comments": true,
                "id": "8321e5f1-6545-4304-90eb-069ce032e599",
                "entity_type": "song_schema",
                "video_url": "",
                "audio_url": "https://cdn1.suno.ai/8321e5f1-6545-4304-90eb-069ce032e599.mp3",
                "image_url": "https://cdn2.suno.ai/image_8321e5f1-6545-4304-90eb-069ce032e599.jpeg",
                "image_large_url": "https://cdn2.suno.ai/image_large_8321e5f1-6545-4304-90eb-069ce032e599.jpeg",
                "major_model_version": "v5",
                "model_name": "chirp-crow",
                "metadata": {
                    "tags": "古典",
                    "prompt": "一段平静舒缓的钢琴曲，带有柔和的旋律",
                    "type": "preview",
                    "duration": 60,
                    "refund_credits": false,
                    "stream": true,
                    "make_instrumental": true,
                    "control_sliders": {
                        "audio_weight": 0.65,
                        "style_weight": 0.65,
                        "weirdness_constraint": 0.65
                    },
                    "can_remix": false,
                    "is_remix": false,
                    "priority": 0,
                    "has_stem": false,
                    "uses_latest_model": true,
                    "model_badges": {
                        "songcard": {
                            "display_name": "v5 Preview",
                            "light": {
                                "text_color": "FD429C",
                                "background_color": "0000004D",
                                "border_color": "00000000"
                            },
                            "dark": {
                                "text_color": "FD429C",
                                "background_color": "0000004D",
                                "border_color": "00000000"
                            }
                        },
                        "songrow": {
                            "display_name": "v5 Preview",
                            "light": {
                                "text_color": "FD429C",
                                "background_color": "FD429C1A",
                                "border_color": "00000000"
                            },
                            "dark": {
                                "text_color": "FD429C",
                                "background_color": "FD429C40",
                                "border_color": "00000000"
                            }
                        }
                    }
                },
                "is_liked": false,
                "user_id": "b84baab3-2550-4c45-96a9-99bead3103e4",
                "handle": "nnhkluradpf",
                "is_handle_updated": true,
                "avatar_image_url": "https://cdn1.suno.ai/sAura12.jpg",
                "is_trashed": false,
                "created_at": "2025-12-30T05:07:49.751Z",
                "is_public": false,
                "explicit": false,
                "comment_count": 0,
                "flag_count": 0,
                "is_contest_clip": false,
                "preview_seconds": 600,
                "has_hook": false,
                "batch_index": 1
            }
        ]
    }

```

### 响应示例
```json
{
    "data": [
        {
            "status": "complete",
            "title": "宁静钢琴冥想",
            "play_count": 0,
            "upvote_count": 0,
            "allow_comments": true,
            "id": "56cb7d08-604b-41ad-932c-3a0fab5db506",
            "entity_type": "song_schema",
            "video_url": "",
            "audio_url": "minio://<bucket>/path/to/file.mp3",
            "image_url": "minio://<bucket>/path/to/image.jpeg",
            "image_large_url": "minio://<bucket>/path/to/image_large.jpeg",
            "avatar_image_url": "minio://<bucket>/path/to/avatar_image.jpg",
            ...
        },
        ...
    ]
}
```