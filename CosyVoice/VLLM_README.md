# CosyVoice vLLM 多GPU推理环境

本目录包含使用vLLM进行CosyVoice多GPU推理的环境和脚本。

## 环境设置

已使用uv创建了名为`.venv_vllm`的虚拟环境，并安装了以下关键依赖：

- PyTorch 2.7.0
- vLLM 0.9.0
- 其他CosyVoice所需的依赖

## 使用方法

### 1. 激活虚拟环境

```bash
source .venv_vllm/bin/activate
```

### 2. 测试环境

运行测试脚本，确认环境设置正确：

```bash
python test_vllm_env.py
```

### 3. 运行多GPU推理

使用提供的脚本启动多GPU推理：

```bash
# 使用默认设置（2个GPU，内存利用率0.7）
./run_multi_gpu_vllm.sh

# 自定义GPU数量和内存利用率
./run_multi_gpu_vllm.sh 4 0.8  # 使用4个GPU，内存利用率0.8
```

## 参数说明

- `tensor_parallel_size`: 张量并行大小，即使用的GPU数量
- `gpu_memory_utilization`: GPU内存利用率，范围0.0-1.0

## 注意事项

1. 确保模型文件已正确下载到`pretrained_models/CosyVoice2-0.5B`目录
2. 确保示例音频文件`asset/zero_shot_prompt.wav`存在
3. 根据实际GPU数量调整`tensor_parallel_size`参数

## 故障排除

如果遇到问题，请尝试以下步骤：

1. 检查CUDA是否可用：`python -c "import torch; print(torch.cuda.is_available())"`
2. 检查可用GPU数量：`python -c "import torch; print(torch.cuda.device_count())"`
3. 确认vLLM版本：`python -c "import vllm; print(vllm.__version__)"`

## 参考资料

- [CosyVoice GitHub](https://github.com/FunAudioLLM/CosyVoice)
- [vLLM 文档](https://docs.vllm.ai/) 