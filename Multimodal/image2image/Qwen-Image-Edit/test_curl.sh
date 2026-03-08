#!/bin/bash

# Qwen Image Edit API - cURL 测试脚本

API_BASE_URL="http://localhost:8000"

echo "🧪 测试 Qwen Image Edit API - cURL 命令"
echo "=========================================="

# 检查API是否可用
echo "1. 检查API健康状态..."
HEALTH_RESPONSE=$(curl -s "$API_BASE_URL/health")
if [[ $? -eq 0 ]]; then
    echo "✅ API服务正常"
else
    echo "❌ API服务不可用，请确保服务正在运行"
    exit 1
fi

# 检查测试图片是否存在
echo ""
echo "2. 检查测试图片..."
if [[ -f "cat_sitting.jpg" ]]; then
    echo "✅ 找到测试图片: cat_sitting.jpg"
    TEST_IMAGE="cat_sitting.jpg"
elif [[ -f "neon_sign.png" ]]; then
    echo "✅ 找到测试图片: neon_sign.png"
    TEST_IMAGE="neon_sign.png"
elif [[ -f "pie.png" ]]; then
    echo "✅ 找到测试图片: pie.png"
    TEST_IMAGE="pie.png"
else
    echo "❌ 未找到测试图片，请确保项目目录中有示例图片"
    exit 1
fi

# 基本图片编辑测试
echo ""
echo "3. 测试基本图片编辑..."
RESPONSE=$(curl -s -X POST "$API_BASE_URL/v1/images/edits" \
  -F "image=@$TEST_IMAGE" \
  -F "prompt=make the image more colorful" \
  -F "n=1" \
  -F "guidance_scale=4.0")

if [[ $? -eq 0 ]]; then
    echo "✅ 图片编辑请求成功"
    echo "响应: $RESPONSE"
    
    # 提取图片URL并下载
    if command -v jq &> /dev/null; then
        IMAGE_URL=$(echo "$RESPONSE" | jq -r '.data[0].url // empty')
        if [[ -n "$IMAGE_URL" ]]; then
            echo "图片URL: $IMAGE_URL"
            
            # 下载图片
            echo "下载生成的图片..."
            curl -s -X GET "$API_BASE_URL$IMAGE_URL" -o "test_output.png"
            if [[ $? -eq 0 ]]; then
                echo "✅ 图片下载成功: test_output.png"
            else
                echo "❌ 图片下载失败"
            fi
        else
            echo "⚠️  无法提取图片URL"
        fi
    else
        echo "⚠️  未安装jq工具，无法自动下载图片"
        echo "请手动从响应中提取图片URL并下载"
    fi
else
    echo "❌ 图片编辑请求失败"
fi

# 测试多图片生成
echo ""
echo "4. 测试多图片生成..."
RESPONSE2=$(curl -s -X POST "$API_BASE_URL/v1/images/edits" \
  -F "image=@$TEST_IMAGE" \
  -F "prompt=add a magical effect" \
  -F "n=2" \
  -F "guidance_scale=4.0" \
  -F "seed=42")

if [[ $? -eq 0 ]]; then
    echo "✅ 多图片生成请求成功"
    if command -v jq &> /dev/null; then
        IMAGE_COUNT=$(echo "$RESPONSE2" | jq '.data | length')
        echo "生成了 $IMAGE_COUNT 张图片"
    fi
else
    echo "❌ 多图片生成请求失败"
fi

# 测试禁用提示词重写
echo ""
echo "5. 测试禁用提示词重写..."
RESPONSE3=$(curl -s -X POST "$API_BASE_URL/v1/images/edits" \
  -F "image=@$TEST_IMAGE" \
  -F "prompt=original prompt without rewriting" \
  -F "n=1" \
  -F "rewrite_prompt=false")

if [[ $? -eq 0 ]]; then
    echo "✅ 禁用提示词重写测试成功"
else
    echo "❌ 禁用提示词重写测试失败"
fi

echo ""
echo "🎉 cURL 测试完成!"
echo ""
echo "📝 使用说明:"
echo "- 基本命令: curl -X POST \"$API_BASE_URL/v1/images/edits\" -F \"image=@your_image.jpg\" -F \"prompt=your_prompt\""
echo "- 查看完整示例: cat curl_examples.md"
echo "- API文档: $API_BASE_URL/docs" 