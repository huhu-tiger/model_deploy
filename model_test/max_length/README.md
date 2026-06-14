# max_length — 模型最大输入/输出长度探测

无需 tokenizer，通过向 OpenAI 兼容接口发送**递增字数的汉字填充文本**，阶梯式探测模型实际支持的最大输入与输出 token 数。

> **原理**：汉字「测」经常见中文模型编码后约 **1 字 ≈ 1 token**，字数档位与 token 数高度接近，误差通常 ≤ 1%。

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `test_max_length.py` | 核心探测脚本（Python 3.8+，仅用标准库） |
| `run.sh` | Shell 封装，通过环境变量传参 |
| `Makefile` | Make 封装，提供常用预设目标 |

---

## 快速上手

```bash
cd model_test/max_length

# 查看帮助
make help

# 使用默认参数（30003 端口 / Qwen3.6-35B-A3B）
make test

# 指定 MiniMax M2.7
make test-minimax-2.7
```

---

## 三种测试模式

### 1. 最大输入测试

发送逐渐增大的填充文本，直到服务端返回 context length 错误为止。

```bash
make test-input \
  API_URL=http://127.0.0.1:30003/v1/chat/completions \
  MODEL_NAME=/nvme01/MiniMax/MiniMax-M2.7
```

输出示例：

```
[输入] 阶梯探测 16K → 199K（步进: 翻倍，约 1024 字/K），报错即停
   16K  (~  16384 字)  OK  prompt_tokens=16428    elapsed=0.2s
   32K  (~  32768 字)  OK  prompt_tokens=32812    elapsed=0.5s
   64K  (~  65536 字)  OK  prompt_tokens=65580    elapsed=1.2s
  128K  (~ 131072 字)  OK  prompt_tokens=131116   elapsed=3.3s
  199K  (~ 203776 字)  OK  prompt_tokens=203820   elapsed=9.1s

>>> 最大输入（本脚本阶梯）: 199K (约 203776 字, prompt_tokens=203820)
    模型 context 上限 204800 tokens，粗估还可再增大约 980 tokens
```

### 2. 最大输出测试（短输入）

使用极短的输入，阶梯式增大 `max_tokens`，测出模型在输入极小时最多能生成多少 token。

```bash
make test-output \
  API_URL=http://127.0.0.1:30003/v1/chat/completions \
  MODEL_NAME=/nvme01/MiniMax/MiniMax-M2.7
```

### 3. 联合测试：固定输入 N K，探最大输出

实际业务中输入和输出共享同一个 context 窗口：

```
input_tokens + output_tokens ≤ max_model_len
```

当输入 192K 时，理论最大输出 = `204800 − 196662 ≈ 8138 tokens`。

```bash
make test \
  API_URL=http://127.0.0.1:30003/v1/chat/completions \
  MODEL_NAME=/nvme01/MiniMax/MiniMax-M2.7 \
  SKIP_INPUT=1 SKIP_OUTPUT=1 \
  JOINT_INPUT_K=192
```

**实测输出（MiniMax-M2.7，2026-06-14）：**

```
[联合] 固定输入 192K (~196608 字)，prompt_tokens=196662
       理论最大输出 = 204800 - 196662 = 8138 tokens
       阶梯探测 max_tokens: 1K → 7K，步进=翻倍
     1K  (max_tokens=1024   )  OK  completion_tokens=1024     elapsed=8.9s
     2K  (max_tokens=2048   )  OK  completion_tokens=2048     elapsed=17.6s
     4K  (max_tokens=4096   )  OK  completion_tokens=4096     elapsed=34.9s

>>> [联合] 输入 192K 时最大输出: max_tokens=4096，实际 completion_tokens=4096
    理论值 8138 tokens，实测最大档位 4096
```

**结果摘要 JSON：**

```json
{
  "url": "http://127.0.0.1:30003/v1/chat/completions",
  "model": "/nvme01/MiniMax/MiniMax-M2.7",
  "k_unit": 1024,
  "max_model_len": 204800,
  "joint": {
    "fixed_input_k": 192,
    "actual_prompt_tokens": 196662,
    "theory_max_output_tokens": 8138,
    "last_ok": {
      "step_k": 4,
      "max_tokens": 4096,
      "prompt_tokens": 196662,
      "completion_tokens": 4096,
      "elapsed_s": 34.86
    },
    "fail_at": null,
    "max_output_max_tokens": 4096,
    "max_output_completion_tokens": 4096
  }
}
```

> **说明**：脚本阶梯步进为翻倍（1K→2K→4K→7K），4K 档通过后下一档为 7K（理论上限 8138 折算），7K 请求超时被中断，最终确认实测可用上限为 **4096 tokens**。若需确认 4K～8K 之间的精确边界，可用等步进细探：
> ```bash
> make test SKIP_INPUT=1 SKIP_OUTPUT=1 JOINT_INPUT_K=192 \
>   MODEL_NAME=/nvme01/MiniMax/MiniMax-M2.7 \
>   START_K=4 MAX_K=8 STEP_K=1
> ```

---

## 全部参数

### Makefile 变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `API_URL` | `http://127.0.0.1:30003/v1/chat/completions` | 接口地址 |
| `MODEL_NAME` | `Qwen3.6-35B-A3B` | 模型名称（需与服务端注册名一致） |
| `API_KEY` | 空 | Bearer Token，空则不携带 |
| `START_K` | `16` | 输入探测起始档位（K） |
| `MAX_K` | `512` | 输入探测最大档位（K），自动按 `max_model_len` 封顶 |
| `STEP_K` | `0` | 步进：`0`=翻倍，正整数=等步进（如 `16` 表示每次 +16K） |
| `K_UNIT` | `1024` | 1K 对应字符数（1024 = 二进制 K） |
| `TIMEOUT` | `600` | 单次请求超时（秒） |
| `JOINT_INPUT_K` | `0` | 联合测试固定输入大小（K），`0`=不做 |
| `SKIP_INPUT` | `0` | `1`=跳过输入测试 |
| `SKIP_OUTPUT` | `0` | `1`=跳过输出测试 |
| `EXTRA_BODY` | 见下 | 附加请求体 JSON，默认 `{"chat_template_kwargs":{"enable_thinking":false}}` |

### Python 参数（与变量对应）

```
--url               对应 API_URL
--model             对应 MODEL_NAME
--api-key           对应 API_KEY
--start-k           对应 START_K
--max-k             对应 MAX_K
--step-k            对应 STEP_K
--k-unit            对应 K_UNIT
--timeout           对应 TIMEOUT
--joint-input-k     对应 JOINT_INPUT_K
--skip-input        对应 SKIP_INPUT=1
--skip-output       对应 SKIP_OUTPUT=1
--extra-body        对应 EXTRA_BODY
--output-start-k    输出探测起始档位（K），默认与 START_K 相同
--output-max-k      输出探测最大档位（K），默认与 MAX_K 相同
--no-auto-cap-max-k 禁止自动按 max_model_len 压低探测上限
--no-fetch-model-info 不查询 /v1/models
```

---

## 常用示例

```bash
# MiniMax M2.7 仅测输入
make test-input MODEL_NAME=/nvme01/MiniMax/MiniMax-M2.7

# 等步进 +16K，精细探测 128K～200K 区间
make test-input \
  MODEL_NAME=/nvme01/MiniMax/MiniMax-M2.7 \
  START_K=128 MAX_K=200 STEP_K=16

# 联合测试：128K 输入时最大输出是多少
make test \
  MODEL_NAME=/nvme01/MiniMax/MiniMax-M2.7 \
  SKIP_INPUT=1 SKIP_OUTPUT=1 \
  JOINT_INPUT_K=128

# 经 nginx 代理测 MiniMax M3
make test-minimax-m3

# 关闭 thinking 模式（默认已关闭），或自定义 extra_body
EXTRA_BODY='{}' make test MODEL_NAME=/nvme01/MiniMax/MiniMax-M2.7
```

---

## Makefile 预设目标

| 目标 | 说明 |
|------|------|
| `make test` | 输入 + 输出全测 |
| `make test-input` | 仅测最大输入 |
| `make test-output` | 仅测最大输出（短输入） |
| `make test-minimax-2.7` | MiniMax M2.7，直连 SGLang 30003 |
| `make test-minimax-m3` | MiniMax M3，经 nginx 30001 |
| `make test-qwen` | Qwen3.6-35B-A3B，默认 30003 |
| `make help` | 显示帮助与当前变量值 |

---

## 注意事项

- **模型名称**需与服务端 `/v1/models` 返回的 `id` 完全一致，否则 API 报 404。  
  可用 `curl -s http://127.0.0.1:30003/v1/models | python3 -m json.tool` 查看。
- 填充文本为纯汉字重复，**1 字 ≈ 1 token** 仅适用于常见中文 BPE tokenizer（如 MiniMax、Qwen、DeepSeek 系列），英文或其他语言模型误差会更大。
- 联合测试（`JOINT_INPUT_K`）因需实际发送大文本并等待输出，耗时较长，建议设置足够的 `TIMEOUT`（默认 600s）。
- nginx 代理默认 `proxy_read_timeout 300s`，大上下文测试建议直连 SGLang 端口（30003）。
