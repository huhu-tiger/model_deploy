# 阿里云百炼 API 测试示例

## 端点
```
POST /api/v1/services/aigc/text2image/image-synthesis
```

## 支持的请求参数

### input 字段
- `prompt` (string, 必填): 文本描述，最多800字符
- `messages` (array, 可选): 消息列表格式（与 prompt 二选一）
- `negative_prompt` (string, 可选): 反向提示词，最多500字符

### parameters 字段
- `size` (string, 可选): 图像尺寸，支持格式：
  - `宽*高` 格式：如 `1024*1024`、`1328*1328`、`512*768`
  - `宽x高` 格式：如 `1024x1024`、`1328x1328`、`512x768`
  - 默认值：`1024*1024`
- `n` (integer, 可选): 生成图片数量，范围 1-4，默认 1
- `seed` (integer, 可选): 随机种子，范围 0-2147483647
- `negative_prompt` (string, 可选): 反向提示词（也可在 input 中指定）
- `prompt_extend` (boolean, 可选): 是否扩展提示词，默认 true
- `watermark` (boolean, 可选): 是否添加水印（当前版本暂未实现），默认 false
- `num_inference_steps` (integer, 可选): 推理步数，范围 1-50，默认 50
  - 值越大生成质量越高，但耗时越长
  - 推荐值：快速生成 10-20，标准质量 30-40，高质量 50
- `guidance_scale` (float, 可选): 引导系数，默认 4.0
  - 控制生成图像与提示词的匹配程度
  - 推荐范围：3.0-7.0
- `response_format` (string, 可选): 返回格式 `url` 或 `b64_json`，默认 `url`

## 示例 1: 使用 prompt 格式返回 URL
```bash
curl -X POST \
	http://127.0.0.1:6002/api/v1/services/aigc/text2image/image-synthesis \
	-H "Content-Type: application/json" \
	-d '{
		"model": "Qwen-Image",
		"input": {
			"prompt": "一副典雅庄重的对联悬挂于厅堂之中，房间是个安静古典的中式布置，桌子上放着一些青花瓷，对联上左书\"义本生知人机同道善思新\"，右书\"通云赋智乾坤启数高志远\"，横批\"智启通义\"，字体飘逸，在中间挂着一幅中国风的画作，内容是岳阳楼。",
			"negative_prompt": ""
		},
		"parameters": {
			"size": "1328*1328",
			"n": 1,
			"seed": 12345,
			"num_inference_steps": 10,
			"guidance_scale": 4.5,
			"prompt_extend": true,
			"response_format": "url"
		}
	}'
```

## 示例 2: 使用 messages 格式返回 URL（阿里云百炼标准格式）
```bash
curl -X POST \
	http://127.0.0.1:6002/api/v1/services/aigc/text2image/image-synthesis \
	-H "Content-Type: application/json" \
	-d '{
		"model": "Qwen-Image-2512",
		"input": {
			"messages": [
				{
					"role": "user",
					"content": [
						{
							"text": "一副典雅庄重的对联悬挂于厅堂之中，房间是个安静古典的中式布置，桌子上放着一些青花瓷，对联上左书\"义本生知人机同道善思新\"，右书\"通云赋智乾坤启数高志远\"，横批\"智启通义\"，字体飘逸，在中间挂着一幅中国风的画作，内容是岳阳楼。"
						}
					]
				}
			]
		},
		"parameters": {
			"negative_prompt": "",
			"prompt_extend": true,
			"size": "1328*1328",
			"n": 1,
			"num_inference_steps": 30,
			"guidance_scale": 4.0,
			"response_format": "url"
		}
	}'
```

## 示例 3: 返回 base64 格式
```bash
curl -X POST \
	http://127.0.0.1:6002/api/v1/services/aigc/text2image/image-synthesis \
	-H "Content-Type: application/json" \
	-d '{
		"model": "Qwen-Image",
		"input": {
			"prompt": "a serene lakeside sunrise with light mist and warm golden light"
		},
		"parameters": {
			"size": "1024*1024",
			"n": 1,
			"num_inference_steps": 30,
			"guidance_scale": 4.0,
			"prompt_extend": true,
			"response_format": "b64_json"
		}
	}'
```

## 示例 4: 批量生成多张图片
```bash
curl -X POST \
	http://127.0.0.1:6002/api/v1/services/aigc/text2image/image-synthesis \
	-H "Content-Type: application/json" \
	-d '{
		"model": "Qwen-Image",
		"input": {
			"prompt": "未来科技城市夜景",
			"negative_prompt": "模糊，低质量"
		},
		"parameters": {
			"size": "1024*1024",
			"n": 4,
			"seed": 100
		}
	}'
```

## 响应格式
```json
{
	"output": {
		"choices": [
			{
				"finish_reason": "stop",
				"message": {
					"content": [
						{"image": "https://minio-url/path/to/image.png"}
					],
					"role": "assistant"
				}
			}
		],
		"task_metric": {
			"TOTAL": 1,
			"SUCCEEDED": 1,
			"FAILED": 0
		}
	},
	"usage": {
		"image_count": 1,
		"width": 1024,
		"height": 1024
	},
	"request_id": "abc123..."
}
```
