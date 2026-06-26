```
curl --location --request POST 'http://10.20.201.215:6010/v1/embeddings' \
--header 'Content-Type: application/json' \
--header 'Authorization: Bearer sk-aaabbbcccdddeeefffggghhhiiijjjkkk' \
--data-raw '{
  "input": ["Your text string goes here"],
  "model": "Qwen3-Embedding-0.6B",
  "encoding_format":"base64"

}'
```