#!/usr/bin/env python3
"""
Qwen Image Edit API 客户端示例

演示如何使用符合OpenAI格式的FastAPI接口进行图像编辑
"""

import requests
import base64
import json
from PIL import Image
import io
import os

# API配置
API_BASE_URL = "http://localhost:8000"

def encode_image_to_base64(image_path):
    """将图像文件编码为base64字符串"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def download_image_from_url(base_url, image_url, output_path):
    """从URL下载图像文件"""
    try:
        # 构建完整的下载URL
        if image_url.startswith('/'):
            full_url = f"{base_url}{image_url}"
        else:
            full_url = image_url
            
        response = requests.get(full_url)
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            print(f"图像已下载到: {output_path}")
        else:
            print(f"下载失败: {response.status_code}")
    except Exception as e:
        print(f"下载图像时出错: {str(e)}")

def test_json_api():
    """测试JSON格式的API"""
    print("=== 测试JSON格式API ===")
    
    # 准备请求数据
    image_path = "cat_sitting.jpg"  # 使用项目中的示例图像
    if not os.path.exists(image_path):
        print(f"错误: 找不到图像文件 {image_path}")
        return
    
    # 编码图像
    image_base64 = encode_image_to_base64(image_path)
    
    # 准备请求
    payload = {
        "model": "qwen-image-edit",
        "prompt": "make the cat floating in the air and holding a sign that reads 'this is fun' written with a blue crayon",
        "image": image_base64,
        "n": 1,
        "size": "1024x1024",
        "quality": "standard",
        "seed": 42,
        "guidance_scale": 4.0,
        "num_inference_steps": 50,
        "rewrite_prompt": True
    }
    
    # 发送请求
    try:
        response = requests.post(
            f"{API_BASE_URL}/v1/images/edits",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ API调用成功!")
            print(f"响应ID: {result['id']}")
            print(f"模型: {result['model']}")
            print(f"创建时间: {result['created']}")
            
            # 下载生成的图像
            for i, data in enumerate(result['data']):
                output_path = f"output_json_{i}.png"
                download_image_from_url(API_BASE_URL, data['url'], output_path)
                print(f"修订后的提示词: {data.get('revised_prompt', 'N/A')}")
        else:
            print(f"❌ API调用失败: {response.status_code}")
            print(f"错误信息: {response.text}")
            
    except Exception as e:
        print(f"❌ 请求失败: {str(e)}")

def test_upload_api():
    """测试文件上传格式的API"""
    print("\n=== 测试文件上传API ===")
    
    # 准备文件
    image_path = "neon_sign.png"  # 使用项目中的示例图像
    if not os.path.exists(image_path):
        print(f"错误: 找不到图像文件 {image_path}")
        return
    
    # 准备表单数据
    files = {
        'image': ('neon_sign.png', open(image_path, 'rb'), 'image/png')
    }
    
    data = {
        'prompt': "change the text to read 'Qwen Image Edit is here'",
        'model': 'qwen-image-edit',
        'n': '1',
        'size': '1024x1024',
        'quality': 'standard',
        'seed': '123',
        'guidance_scale': '4.0',
        'num_inference_steps': '50',
        'rewrite_prompt': 'true'
    }
    
    # 发送请求
    try:
        response = requests.post(
            f"{API_BASE_URL}/v1/images/edits",
            files=files,
            data=data
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 文件上传API调用成功!")
            print(f"响应ID: {result['id']}")
            print(f"模型: {result['model']}")
            print(f"创建时间: {result['created']}")
            
            # 下载生成的图像
            for i, data in enumerate(result['data']):
                output_path = f"output_upload_{i}.png"
                download_image_from_url(API_BASE_URL, data['url'], output_path)
                print(f"修订后的提示词: {data.get('revised_prompt', 'N/A')}")
        else:
            print(f"❌ 文件上传API调用失败: {response.status_code}")
            print(f"错误信息: {response.text}")
            
    except Exception as e:
        print(f"❌ 请求失败: {str(e)}")

def test_health_check():
    """测试健康检查端点"""
    print("\n=== 测试健康检查 ===")
    
    try:
        response = requests.get(f"{API_BASE_URL}/health")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 健康检查通过!")
            print(f"状态: {result['status']}")
            print(f"模型已加载: {result['model_loaded']}")
            print(f"设备: {result['device']}")
        else:
            print(f"❌ 健康检查失败: {response.status_code}")
            
    except Exception as e:
        print(f"❌ 健康检查请求失败: {str(e)}")

def test_root_endpoint():
    """测试根端点"""
    print("\n=== 测试根端点 ===")
    
    try:
        response = requests.get(f"{API_BASE_URL}/")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 根端点访问成功!")
            print(f"消息: {result['message']}")
            print(f"版本: {result['version']}")
            print("可用端点:")
            for endpoint, description in result['endpoints'].items():
                print(f"  {endpoint}: {description}")
        else:
            print(f"❌ 根端点访问失败: {response.status_code}")
            
    except Exception as e:
        print(f"❌ 根端点请求失败: {str(e)}")

def main():
    """主函数"""
    print("🚀 Qwen Image Edit API 客户端示例")
    print("=" * 50)
    
    # 检查API是否可用
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print(f"❌ API服务不可用，状态码: {response.status_code}")
            print("请确保API服务正在运行: python api.py")
            return
    except requests.exceptions.RequestException:
        print("❌ 无法连接到API服务")
        print("请确保API服务正在运行: python api.py")
        return
    
    # 运行测试
    test_health_check()
    test_root_endpoint()
    test_json_api()
    test_upload_api()
    
    print("\n🎉 所有测试完成!")

if __name__ == "__main__":
    main() 