import requests
import time
import numpy as np
import wave
import io

# 发送请求到流式接口
url = "http://localhost:5788/tts_clone/stream"
payload = {
    "input": "这是一个较长的测试文本，用于测试流式接口是否能够正确传输多个音频块。如果只收到第一秒的音频，那么可能是流式传输出现了问题。",
    "voice": "tt"
}

print("开始请求流式接口...")
start_time = time.time()

# 使用stream=True参数来接收流式响应
response = requests.post(url, json=payload, stream=True)

# 保存流式响应到文件
with open("stream_output.wav", "wb") as f:
    chunk_count = 0
    total_bytes = 0
    
    for chunk in response.iter_content(chunk_size=1024):
        if chunk:
            chunk_count += 1
            chunk_size = len(chunk)
            total_bytes += chunk_size
            elapsed = time.time() - start_time
            print(f"收到块 {chunk_count}: {chunk_size} 字节, 总计: {total_bytes} 字节, 时间: {elapsed:.2f}秒")
            f.write(chunk)

print(f"\n总共收到 {chunk_count} 个数据块, {total_bytes} 字节")
print(f"请求完成，总耗时: {time.time() - start_time:.2f}秒")
print(f"音频文件已保存为 stream_output.wav")

# 分析生成的WAV文件
try:
    with wave.open("stream_output.wav", "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        frame_rate = wav.getframerate()
        n_frames = wav.getnframes()
        duration = n_frames / frame_rate
        
        print(f"\nWAV文件分析:")
        print(f"声道数: {channels}")
        print(f"采样宽度: {sample_width} 字节")
        print(f"采样率: {frame_rate} Hz")
        print(f"总帧数: {n_frames}")
        print(f"音频时长: {duration:.2f} 秒")
except Exception as e:
    print(f"无法分析WAV文件: {e}")