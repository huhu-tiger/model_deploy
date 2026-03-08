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

# 文档简介

## [api_test.md](docs/api_test.md)
- 描述如何使用 `/v1/images/generations` 接口。
- 提供了使用 `curl` 测试接口的示例，包括返回 URL 和 base64 的两种情况。

## [product.md](docs/product.md)
- 详细说明了 `/v1/images/generations` 接口的请求参数和响应参数。
- 示例展示了如何构造请求体以及返回的图片 URL。

## [tech.md](docs/tech.md)
- 介绍了 Qwen-Image 的技术实现，包括依赖环境、接口定义和处理流程。
- 涵盖了 prompt 重写、推理调用和响应封装的技术细节。