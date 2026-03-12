# Qwen3-VL-8B-Instruct 部署文档

基于 [vLLM](https://github.com/vllm-project/vllm) 部署 Qwen3-VL-8B 多模态视觉语言模型，提供 OpenAI 兼容接口。

---

## 环境信息

| 项目 | 值 |
|---|---|
| 模型 | Qwen3-VL-8B-Instruct |
| 模型路径 | `/media/llm/Qwen/Qwen3-VL-8B-Instruct/` |
| vLLM 镜像 | `vllm/vllm-openai:v0.15.0-cu130` |
| 服务端口 | `9116` |
| GPU | 物理卡 1、6（容器内 GPU 0、1） |
| 张量并行 | 2 卡 |

---

## 快速启动

```bash
cd /media/source/model_deploy/Multimodal/VL/qwen3-8B-VL
docker compose up -d
```

查看日志：

```bash
docker logs -f vllm-qwen3-vl-8b
```

停止服务：

```bash
docker compose down
```

---

## 启动参数说明

| 参数 | 值 | 说明 |
|---|---|---|
| `--served-model-name` | `Qwen3-VL-8B-Instruct` | API 请求时使用的模型名 |
| `--tensor-parallel-size` | `2` | 张量并行数，与 GPU 数量一致 |
| `--dtype` | `bfloat16` | 推理精度，A100/H100 推荐 |
| `--gpu-memory-utilization` | `0.9` | GPU 显存利用率上限 |
| `--max-model-len` | `16384` | 最大上下文长度（tokens） |
| `--max-num-seqs` | `64` | 最大并发请求数 |
| `--kv-cache-dtype` | `fp8` | KV Cache 精度（需 GPU 支持 FP8） |
| `--mm-encoder-tp-mode` | `data` | 视觉编码器使用数据并行 |
| `--mm-processor-cache-gb` | `2` | 多模态预处理器缓存大小 |
| `--limit-mm-per-prompt.image` | `2` | 每次请求最多处理图片数 |
| `--limit-mm-per-prompt.video` | `0` | 禁用视频输入（节省显存） |

> ⚠️ `--kv-cache-dtype fp8` 需要 A100 / H100 / L40S 等支持 FP8 的 GPU，若不支持请删除该参数。

> ⚠️ `--async-scheduling` 在 Qwen3-VL-8B 上存在已知崩溃 Bug（[#31679](https://github.com/vllm-project/vllm/issues/31679)），已禁用。

---

## GPU 配置

使用物理 GPU `1` 和 `6`（通过 `device_ids` 指定），容器内编号为 GPU `0`、`1`。

如需切换 GPU，修改 `docker-compose.yml` 中的 `device_ids` 字段：

```yaml
device_ids: [ "1","6" ]
```

如需单卡运行，同时将 `--tensor-parallel-size` 改为 `1`。

---

## API 调用示例

服务启动后，接口地址为 `http://<host>:9116/v1`。

### 文本 + 图片 URL

```python
import openai

client = openai.OpenAI(base_url="http://localhost:9116/v1", api_key="none")

resp = client.chat.completions.create(
    model="Qwen3-VL-8B-Instruct",
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url",
             "image_url": {"url": "https://example.com/image.jpg"}},
            {"type": "text", "text": "描述这张图片"}
        ]
    }]
)
print(resp.choices[0].message.content)
```

### 本地图片（Base64）

```python
import openai, base64

client = openai.OpenAI(base_url="http://localhost:9116/v1", api_key="none")

with open("photo.jpg", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

resp = client.chat.completions.create(
    model="Qwen3-VL-8B-Instruct",
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": "图中有什么内容？"}
        ]
    }]
)
print(resp.choices[0].message.content)
```

### 多图输入（最多 2 张）

```python
resp = client.chat.completions.create(
    model="Qwen3-VL-8B-Instruct",
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": "https://example.com/img1.jpg"}},
            {"type": "image_url", "image_url": {"url": "https://example.com/img2.jpg"}},
            {"type": "text", "text": "对比这两张图片的差异"}
        ]
    }]
)
```

### curl 快速验证

```bash
curl http://localhost:9116/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-VL-8B-Instruct",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "image_url", "image_url": {"url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/Cat03.jpg/320px-Cat03.jpg"}},
          {"type": "text", "text": "这是什么动物？"}
        ]
      }
    ]
  }'
```

---

## 支持的图像格式

| 格式 | MIME 类型 | 说明 |
|---|---|---|
| JPEG / JPG | `image/jpeg` | 推荐，最常用 |
| PNG | `image/png` | 支持透明通道 |
| WebP | `image/webp` | 高压缩率 |
| BMP | `image/bmp` | 无损位图 |
| GIF | `image/gif` | 仅取第一帧 |
| TIFF | `image/tiff` | 医学/遥感场景 |

传入方式：HTTP/HTTPS URL、Base64 Data URI、容器内本地路径（`file:///...`）

图像尺寸：最小 `28×28`，超出 `1280×1280` 自动缩放。

---

## 常见问题

**Q: 启动时显存不足？**  
降低 `--gpu-memory-utilization`（如 `0.85`）或缩短 `--max-model-len`（如 `8192`）。

**Q: GPU 不支持 FP8 报错？**  
删除 `--kv-cache-dtype fp8` 参数（适用于 RTX 3090 / 4090 等消费级显卡）。

**Q: 如何启用 Tool Call？**  
取消 `docker-compose.yml` 中以下注释：
```yaml
- --enable-auto-tool-choice
- --tool-call-parser
- hermes
```

**Q: 如何启用视频输入？**  
将 `--limit-mm-per-prompt.video` 改为正整数（如 `1`），注意会增加显存占用。
