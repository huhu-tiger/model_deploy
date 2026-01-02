# 编写多模态产品说明文档

# 接口
## 编写/v1/images/generations接口
## 请求参数

{
    "model": "aliyun/aliyun/qwen-image-plus",
    "input": {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "text": "一副典雅庄重的对联悬挂于厅堂之中，房间是个安静古典的中式布置，桌子上放着一些青花瓷，对联上左书“义本生知人机同道善思新”，右书“通云赋智乾坤启数高志远”， 横批“智启通义”，字体飘逸，在中间挂着一幅中国风的画作，内容是岳阳楼。"
                    }
                ]
            }
        ]
    },
    "parameters": {
        "negative_prompt": "",
        "prompt_extend": true,
        "watermark": false,
        "size": "1328*1328"
    }
}

## 响应参数

{
    "output": {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": [
                        {
                            "image": "https://dashscope-result-wlcb-acdr-1.oss-cn-wulanchabu-acdr-1.aliyuncs.com/7d/93/20260102/cfc32567/d1c485a5-48bb-45bd-ab11-dab2de3b4226-1.png?Expires=1767927258&OSSAccessKeyId=LTAI5tKPD3TMqf2Lna1fASuh&Signature=YD5PN9nnADTpCoGL7ojcUDnocEE%3D"
                        }
                    ],
                    "role": "assistant"
                }
            }
        ],
        "task_metric": {
            "FAILED": 0,
            "SUCCEEDED": 1,
            "TOTAL": 1
        }
    },
    "usage": {
        "height": 1328,
        "image_count": 1,
        "width": 1328
    },
    "request_id": "d1c485a5-48bb-45bd-ab11-dab2de3b4226"
}