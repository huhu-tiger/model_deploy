## 支持A800

## 支持Function Calling
```
curl --location --request POST 'http://39.155.179.5:30002/v1/chat/completions' \
--header 'Content-Type: application/json' \
--header 'Authorization: Bearer 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' \
--data-raw '{
    "model": "DeepSeek-V3.2",
    "messages": [
      {
        "role": "user",
        "content": "北京的天气怎么样？"
      }
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_weather",
          "description": "获取指定城市的天气信息",
          "parameters": {
            "type": "object",
            "properties": {
              "location": {
                "type": "string",
                "description": "城市名称，如：北京、上海"
              }
            },
            "required": ["location"]
          }
        }
      }
    ],
    "tool_choice": {
      "type": "function",
      "function": {
        "name": "get_weather"
      }
    }
  }'
```