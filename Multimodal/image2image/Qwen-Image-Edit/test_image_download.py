#!/usr/bin/env python3
"""
测试图片下载功能的脚本
"""

import requests
import base64
import os

# API配置
API_BASE_URL = "http://localhost:8000"

def test_image_download():
    """测试图片下载功能"""
    print("🧪 测试图片下载功能")
    print("=" * 40)
    
    # 检查API是否可用
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print("❌ API服务不可用")
            return
    except:
        print("❌ 无法连接到API服务")
        return
    
    # 准备测试图像
    test_image_path = "cat_sitting.jpg"
    if not os.path.exists(test_image_path):
        print(f"❌ 测试图像不存在: {test_image_path}")
        return
    
    # 编码图像
    with open(test_image_path, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode('utf-8')
    
    # 发送编辑请求
    print("📤 发送图像编辑请求...")
    payload = {
        "prompt": "make the cat wear a red hat",
        "image": image_base64,
        "n": 1
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/v1/images/edits",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 图像编辑成功!")
            print(f"响应ID: {result['id']}")
            
            # 测试图片下载
            for i, data in enumerate(result['data']):
                image_url = data['url']
                print(f"图片URL: {image_url}")
                
                # 构建完整下载URL
                download_url = f"{API_BASE_URL}{image_url}"
                print(f"完整下载URL: {download_url}")
                
                # 下载图片
                print("📥 下载图片...")
                img_response = requests.get(download_url)
                
                if img_response.status_code == 200:
                    # 保存图片
                    output_filename = f"test_download_{i}.png"
                    with open(output_filename, "wb") as f:
                        f.write(img_response.content)
                    print(f"✅ 图片已下载: {output_filename}")
                    
                    # 检查文件大小
                    file_size = len(img_response.content)
                    print(f"文件大小: {file_size} 字节")
                else:
                    print(f"❌ 下载失败: {img_response.status_code}")
                    
        else:
            print(f"❌ 图像编辑失败: {response.status_code}")
            print(f"错误信息: {response.text}")
            
    except Exception as e:
        print(f"❌ 请求失败: {str(e)}")

def test_direct_download():
    """测试直接下载端点"""
    print("\n🔗 测试直接下载端点")
    print("=" * 40)
    
    # 这里需要先有一个存在的图片文件名
    # 在实际使用中，这个文件名来自之前的编辑请求
    test_filename = "edit_test.png"
    
    try:
        response = requests.get(f"{API_BASE_URL}/images/{test_filename}")
        if response.status_code == 200:
            print(f"✅ 直接下载成功: {test_filename}")
        elif response.status_code == 404:
            print(f"ℹ️  文件不存在: {test_filename} (这是正常的，因为文件可能已被清理)")
        else:
            print(f"❌ 下载失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 下载请求失败: {str(e)}")

if __name__ == "__main__":
    test_image_download()
    test_direct_download()
    print("\n🎉 测试完成!") 