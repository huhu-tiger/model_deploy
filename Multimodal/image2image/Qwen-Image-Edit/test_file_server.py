#!/usr/bin/env python3
"""
测试FastAPI文件服务器功能
"""

import requests
import time
import os

# API配置
API_BASE_URL = "http://localhost:8000"

def test_file_server_endpoints():
    """测试文件服务器端点"""
    print("🧪 测试FastAPI文件服务器功能")
    print("=" * 50)
    
    # 检查API是否可用
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print("❌ API服务不可用")
            return
    except:
        print("❌ 无法连接到API服务")
        return
    
    # 1. 测试获取图片统计信息
    print("\n1. 测试获取图片统计信息...")
    try:
        response = requests.get(f"{API_BASE_URL}/images/stats")
        if response.status_code == 200:
            stats = response.json()
            print("✅ 获取统计信息成功!")
            print(f"   总图片数: {stats['total_images']}")
            print(f"   总大小: {stats['total_size_mb']} MB")
            print(f"   目录: {stats['directory']}")
        else:
            print(f"❌ 获取统计信息失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 获取统计信息出错: {str(e)}")
    
    # 2. 测试获取图片列表
    print("\n2. 测试获取图片列表...")
    try:
        response = requests.get(f"{API_BASE_URL}/images")
        if response.status_code == 200:
            images_data = response.json()
            print("✅ 获取图片列表成功!")
            print(f"   总图片数: {images_data['total']}")
            
            if images_data['total'] > 0:
                print("   最新图片:")
                for i, image in enumerate(images_data['images'][:3]):  # 显示前3张
                    print(f"     {i+1}. {image['filename']} ({image['size']} bytes)")
            else:
                print("   暂无图片")
        else:
            print(f"❌ 获取图片列表失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 获取图片列表出错: {str(e)}")
    
    # 3. 测试下载图片（如果有图片的话）
    print("\n3. 测试下载图片...")
    try:
        response = requests.get(f"{API_BASE_URL}/images")
        if response.status_code == 200:
            images_data = response.json()
            
            if images_data['total'] > 0:
                # 下载第一张图片
                first_image = images_data['images'][0]
                filename = first_image['filename']
                
                print(f"   尝试下载: {filename}")
                download_response = requests.get(f"{API_BASE_URL}/images/{filename}")
                
                if download_response.status_code == 200:
                    # 保存到测试目录
                    test_dir = "test_downloads"
                    os.makedirs(test_dir, exist_ok=True)
                    
                    test_file_path = os.path.join(test_dir, filename)
                    with open(test_file_path, "wb") as f:
                        f.write(download_response.content)
                    
                    file_size = len(download_response.content)
                    print(f"   ✅ 下载成功: {test_file_path} ({file_size} bytes)")
                else:
                    print(f"   ❌ 下载失败: {download_response.status_code}")
            else:
                print("   暂无图片可下载")
        else:
            print(f"❌ 获取图片列表失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 下载图片出错: {str(e)}")
    
    # 4. 测试删除图片（如果有图片的话）
    print("\n4. 测试删除图片...")
    try:
        response = requests.get(f"{API_BASE_URL}/images")
        if response.status_code == 200:
            images_data = response.json()
            
            if images_data['total'] > 0:
                # 删除第一张图片
                first_image = images_data['images'][0]
                filename = first_image['filename']
                
                print(f"   尝试删除: {filename}")
                delete_response = requests.delete(f"{API_BASE_URL}/images/{filename}")
                
                if delete_response.status_code == 200:
                    result = delete_response.json()
                    print(f"   ✅ 删除成功: {result['message']}")
                    
                    # 验证删除
                    verify_response = requests.get(f"{API_BASE_URL}/images/{filename}")
                    if verify_response.status_code == 404:
                        print("   ✅ 删除验证成功")
                    else:
                        print("   ⚠️  删除验证失败")
                else:
                    print(f"   ❌ 删除失败: {delete_response.status_code}")
            else:
                print("   暂无图片可删除")
        else:
            print(f"❌ 获取图片列表失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 删除图片出错: {str(e)}")
    
    # 5. 测试不存在的图片
    print("\n5. 测试访问不存在的图片...")
    try:
        response = requests.get(f"{API_BASE_URL}/images/nonexistent_image.png")
        if response.status_code == 404:
            print("✅ 正确处理了不存在的图片")
        else:
            print(f"⚠️  意外的响应状态码: {response.status_code}")
    except Exception as e:
        print(f"❌ 测试不存在图片时出错: {str(e)}")

def test_static_file_access():
    """测试静态文件访问"""
    print("\n6. 测试静态文件访问...")
    
    # 检查是否有图片文件
    try:
        response = requests.get(f"{API_BASE_URL}/images")
        if response.status_code == 200:
            images_data = response.json()
            
            if images_data['total'] > 0:
                first_image = images_data['images'][0]
                filename = first_image['filename']
                
                # 测试静态文件访问
                static_url = f"{API_BASE_URL}/images/{filename}"
                print(f"   测试静态文件访问: {static_url}")
                
                response = requests.get(static_url)
                if response.status_code == 200:
                    print("   ✅ 静态文件访问成功")
                    print(f"   Content-Type: {response.headers.get('content-type', 'N/A')}")
                    print(f"   Content-Length: {response.headers.get('content-length', 'N/A')}")
                else:
                    print(f"   ❌ 静态文件访问失败: {response.status_code}")
            else:
                print("   暂无图片文件可测试")
        else:
            print(f"❌ 获取图片列表失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 测试静态文件访问时出错: {str(e)}")

def main():
    """主函数"""
    print("🚀 FastAPI文件服务器功能测试")
    print("=" * 50)
    
    # 运行测试
    test_file_server_endpoints()
    test_static_file_access()
    
    print("\n🎉 文件服务器功能测试完成!")
    print("\n📝 使用说明:")
    print("- 查看API文档: http://localhost:8000/docs")
    print("- 查看图片列表: http://localhost:8000/images")
    print("- 查看统计信息: http://localhost:8000/images/stats")

if __name__ == "__main__":
    main() 