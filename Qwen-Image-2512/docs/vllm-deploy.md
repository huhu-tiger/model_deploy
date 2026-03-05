# 启动模型

```
cd Qwen-Image-2512/
docker-compose -f docker-compose-vllm.yml up -d
```

# 启动gateway
```
conda activate qwen-image-2512
python api-for-vllm.py
```