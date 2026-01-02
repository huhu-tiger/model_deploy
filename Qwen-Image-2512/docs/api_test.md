# /v1/images/generations 测试用 curl

## 返回 URL 示例
```bash
curl -X POST \
	http://127.0.0.1:6002/v1/images/generations \
	-H "Content-Type: application/json" \
	-d '{
		"model": "aliyun/aliyun/qwen-image-plus",
		"input": {
			"messages": [
				{
					"role": "user",
					"content": [
						{"text": "一副典雅庄重的对联悬挂于厅堂之中，房间是个安静古典的中式布置，桌子上放着一些青花瓷，对联上左书\"义本生知人机同道善思新\"，右书\"通云赋智乾坤启数高志远\"，横批\"智启通义\"，字体飘逸，在中间挂着一幅中国风的画作，内容是岳阳楼。"}
					]
				}
			]
		},
		"parameters": {
			"negative_prompt": "",
			"prompt_extend": true,
			"watermark": false,
			"size": "1328*1328",
			"response_format": "url",
			"num_inference_steps": 10,
			"guidance_scale": 4.5,
			"seed": 12345,
			"n": 1,
			"width": 1328,
			"height": 1328
		}
	}'
```

## 返回 base64 示例
```bash
curl -X POST \
	http://127.0.0.1:6002/v1/images/generations \
	-H "Content-Type: application/json" \
	-d '{
		"model": "aliyun/aliyun/qwen-image-plus",
		"input": {
			"messages": [
				{
					"role": "user",
					"content": [
						{"text": "a serene lakeside sunrise with light mist and warm golden light"}
					]
				}
			]
		},
		"parameters": {
			"prompt_extend": true,
			"response_format": "b64_json",
			"num_inference_steps": 30,
			"guidance_scale": 4.0,
			"n": 1,
			"size": "1024x1024"
		}
	}'
```
