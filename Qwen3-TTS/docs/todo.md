- [x] 参考示例目录 example， 编写 符合openai格式的音频生成接口
    1. 输出的结果文件要从上传至minio 返回 minio下载地址。代码在 vnet/common/storage/dal/minio/minio_conn.py
    2. 先实现 test_model_12hz_custom_voice.py 示例中的 接口
- [x] 在api.py 编写音频接口，参考 test_model_12hz_voice_design.py