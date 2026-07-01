# PP-OCRv6 medium OCR 服务化部署

基于 [PaddleX 基础服务化部署](https://paddlepaddle.github.io/PaddleX/latest/pipeline_deploy/serving.html)，将 **PP-OCRv6_medium_det + PP-OCRv6_medium_rec** 封装为 HTTP OCR 服务。

| 项目 | 说明 |
|------|------|
| 产线 | 通用 OCR（`pipeline_name: OCR`） |
| 检测模型 | 宿主机 `/media/llm/PaddlePaddle/PP-OCRv6_medium_det`（只读挂载） |
| 识别模型 | 宿主机 `/media/llm/PaddlePaddle/PP-OCRv6_medium_rec`（只读挂载） |
| 对外端口 | 默认 `9410` → 容器 `8080` |
| API | `POST /ocr` |
| 接口文档 | [api.md](./api.md) |

---

## 模型下载

部署需 **检测（Det）+ 识别（Rec）** 两个推理模型，格式均为 Paddle 静态图（含 `inference.pdiparams` / `inference.yml` / `inference.json`）。

### 官方推理模型（推荐）

| 模型 | 推理包下载 | 大小 |
|------|-----------|------|
| PP-OCRv6_medium_det | https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv6_medium_det_infer.tar | ~59 MB |
| PP-OCRv6_medium_rec | https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv6_medium_rec_infer.tar | ~73 MB |

### 训练权重（微调用，非推理部署）

| 模型 | 下载地址 |
|------|----------|
| PP-OCRv6_medium_det | https://paddle-model-ecology.bj.bcebos.com/paddlex/official_pretrained_model/PP-OCRv6_medium_det_pretrained.pdparams |
| PP-OCRv6_medium_rec | https://paddle-model-ecology.bj.bcebos.com/paddlex/official_pretrained_model/PP-OCRv6_medium_rec_pretrained.pdparams |

### 其他来源

| 平台 | Det | Rec |
|------|-----|-----|
| HuggingFace | https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_det | https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_rec |
| ModelScope | https://www.modelscope.cn/models/PaddlePaddle/PP-OCRv6_medium_det | https://www.modelscope.cn/models/PaddlePaddle/PP-OCRv6_medium_rec |

### 下载到宿主机（与产线配置路径一致）

```bash
mkdir -p /media/llm/PaddlePaddle
cd /media/llm/PaddlePaddle

# 检测模型
wget https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv6_medium_det_infer.tar
tar -xf PP-OCRv6_medium_det_infer.tar
mv PP-OCRv6_medium_det_infer PP-OCRv6_medium_det

# 识别模型（若尚未下载）
wget https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv6_medium_rec_infer.tar
tar -xf PP-OCRv6_medium_rec_infer.tar
mv PP-OCRv6_medium_rec_infer PP-OCRv6_medium_rec
```

下载完成后目录结构：

```
/media/llm/PaddlePaddle/
├── PP-OCRv6_medium_det/
│   ├── inference.pdiparams
│   ├── inference.yml
│   └── inference.json
└── PP-OCRv6_medium_rec/
    ├── inference.pdiparams
    ├── inference.yml
    └── inference.json
```

当前部署已配置为使用上述本地路径，启动时无需联网下载模型。`./model_cache` 仅作 PaddleX 运行时可选缓存。

---

## 目录结构

```
PP-OCRv6/
├── OCR.yaml              # 产线配置（Rec 指向本地模型）
├── Dockerfile            # 基于 paddleocr offline GPU 镜像
├── docker-compose.yml
├── Makefile
├── test_curl.sh          # OCR 接口测试
├── api.md                # 接口文档
├── model_cache/          # PaddleX 运行时缓存（可选，gitignore）
└── readme.md
```

---

## 快速启动

```bash
cd /media/source/model_deploy/Multimodal/OCR/PaddlePaddle/PP-OCRv6

# 构建并启动（默认 GPU=0, PORT=9410）
make up

# 指定 GPU / 端口
make up GPU=4 PORT=9410

# 查看日志
make logs

# 健康检查
make health

# OCR 测试
make test

# 停止
make down
```

---

## API 调用

完整接口说明见 [api.md](./api.md)。

### 健康检查

```bash
curl http://localhost:9410/health
```

### 图片 URL

```bash
curl -X POST "http://localhost:9410/ocr" \
  -H "Content-Type: application/json" \
  -d '{
    "file": "https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/general_ocr_002.png",
    "visualize": false,
    "useDocOrientationClassify": false,
    "useDocUnwarping": false,
    "useTextlineOrientation": false
  }'
```

### 本地图片（Base64）

```bash
IMG_B64=$(base64 -w 0 /path/to/image.jpg)
curl -X POST "http://localhost:9410/ocr" \
  -H "Content-Type: application/json" \
  -d "{\"file\": \"${IMG_B64}\", \"fileType\": 1, \"visualize\": false}"
```

### Python 示例

```python
import base64
import requests

url = "http://localhost:9410/ocr"
with open("test.jpg", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

resp = requests.post(
    url,
    json={"file": img_b64, "fileType": 1, "visualize": False},
    timeout=120,
)
resp.raise_for_status()
data = resp.json()
print(data["result"]["ocrResults"])
```

---

## 配置说明

### 识别模型路径

`OCR.yaml` 中已配置：

```yaml
TextRecognition:
  model_name: PP-OCRv6_medium_rec
  model_dir: /media/llm/PaddlePaddle/PP-OCRv6_medium_rec
```

若模型路径变更，修改 `OCR.yaml` 后执行 `make restart`。

### 检测模型路径

`OCR.yaml` 中已配置：

```yaml
TextDetection:
  model_name: PP-OCRv6_medium_det
  model_dir: /media/llm/PaddlePaddle/PP-OCRv6_medium_det
```

### 启用文档预处理 / 文本行方向（可选）

默认关闭以加快启动、减少依赖模型下载。扫描件场景可在 `OCR.yaml` 中改为：

```yaml
use_doc_preprocessor: true
use_textline_orientation: true
```

并补充 `SubPipelines.DocPreprocessor` 配置（参考 [通用 OCR 产线文档](https://paddlepaddle.github.io/PaddleX/latest/pipeline_usage/tutorials/ocr_pipelines/OCR.html)）。

### 以 URL 返回可视化图（§3）

响应中含大图时，可在 `OCR.yaml` 的 `Serving` 节增加 BOS 配置，详见 [PaddleX 服务化部署 - URL 返回](https://paddlepaddle.github.io/PaddleX/latest/pipeline_deploy/serving.html#3-url)。

---

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `GPU` | `0` | 物理 GPU 编号 |
| `PORT` | `9410` | 宿主机映射端口 |
| `PADDLEOCR_IMAGE_TAG` | `latest-nvidia-gpu-offline` | 基础镜像 tag |
| `PADDLE_PDX_MODEL_SOURCE` | `BOS` | 模型下载源（国内推荐 BOS） |

---

## 注意事项

- **产线级部署**：PaddleX 服务化针对 OCR **产线**，不能单独部署 Rec 模块。
- **离线部署**：Det / Rec 模型均已挂载自 `/media/llm/PaddlePaddle/`，启动无需联网下载模型。
- **基础镜像**：使用 `paddleocr-vl:latest-nvidia-gpu-offline`（CCR 无独立 `paddleocr` 仓库），构建时升级至 paddleocr/paddlex ≥ 3.7 并安装 serving 插件。
- **与 PaddleOCR-VL 区别**：本方案为传统 OCR（检测+识别），非 VLM 文档解析。
