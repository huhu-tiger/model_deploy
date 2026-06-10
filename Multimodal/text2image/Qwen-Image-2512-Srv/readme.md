# 启动命令

## 环境准备
1. 确保已安装 Python 和必要的依赖库。
2. 激活虚拟环境：
```bash
conda activate /media/conda/envs/qwen-image-2512
```
3. 安装依赖：
```bash
pip install -r requirements.txt
pip install -r ../vnet/pip.txt
```


## 启动服务
在项目根目录下运行以下命令：
```bash
python3 ./api.py
```
服务将默认启动在 `http://127.0.0.1:6002`。

## vLLM 部署（推荐）

```bash
docker-compose -f docker-compose-vllm.yml up -d
```

服务地址：`http://localhost:9111`，模型名：`qwen-image`

可选启动百炼兼容网关：

```bash
python api-for-vllm.py
```

网关地址：`http://localhost:6003`

# 文档简介

## [api-reference.md](docs/api-reference.md)
- **完整接口文档**，涵盖 vLLM 直连（OpenAI 兼容）和网关（百炼兼容）两种访问方式。
- 包含部署、参数说明、请求/响应示例、错误码和环境变量配置。

## [api-vllm.md](docs/api-vllm.md)
- vLLM 直连接口 `POST /v1/images/generations` 补充说明。

## [api-vllm-gateway.md](docs/api-vllm-gateway.md)
- 网关接口 `POST /api/v1/services/aigc/multimodal-generation/generation` 补充说明。

## [vllm-deploy.md](docs/vllm-deploy.md)
- Docker 部署与网关启动快速指引。