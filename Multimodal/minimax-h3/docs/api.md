# MiniMax-H3 FL2VA API

基于 [vLLM-Omni Videos API](https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/videos_api/) 与 [MiniMax-H3 Recipe](https://recipes.vllm.ai/MiniMaxAI/MiniMax-H3)。

当前服务加载 **FL2VA** 分区，支持：

| `task` | 说明 |
|--------|------|
| `t2va` | 纯文本 → 视频 + 立体声音频 |
| `fl2va` | 文本 + 首帧/尾帧（0/1/2 张图）→ 视频 + 音频 |

> Ref2VA（`ref2va`）需另起服务加载 `/media/llm/MiniMax/MiniMax-H3/Ref2VA`，本实例不支持。

## 基础信息

| 项 | 值 |
|----|-----|
| Base URL | `http://<host>:9111` |
| 容器端口 | `8000` |
| Content-Type | `multipart/form-data` |
| 推荐同步接口 | `POST /v1/videos/sync`（响应体直接是 MP4） |
| 异步接口 | `POST /v1/videos` → 轮询 `GET /v1/videos/{id}` → 下载 `GET /v1/videos/{id}/content` |
| 输出 | H.264 视频 + AAC 立体声（32 kHz），封装为 MP4 |
| 帧率 | **24 FPS**（固定） |
| 时长 | `extra_params.duration`：4–15 秒 |
| Prompt 上限 | 7000 字符 |

## 健康检查

```bash
curl --fail http://127.0.0.1:9111/health
```

## 推荐分辨率

`width` / `height` 须为 **32 的倍数**，短边常用 **768**（2K 短边 1440 视部署能力而定）：

| 比例 | 480p（短边 480） | 768p（短边 768） |
|------|------------------|------------------|
| 16:9 | **832 × 480** | 1344 × 768 |
| 9:16 | 480 × 832 | 768 × 1344 |
| 1:1  | 480 × 480 | 768 × 768 |

宽高须为 **32 的倍数**。FL2VA 带首帧时也可省略 `width`/`height`，按首帧宽高比生成。

---

## 1. 同步生成（推荐）

**端点**: `POST /v1/videos/sync`  
**响应**: 原始 MP4 字节流（`video/mp4`），用 `-o` 落盘即可。

### 请求参数

| 参数 | 类型 | 必填 | 推荐值 | 说明 |
|------|------|------|--------|------|
| `prompt` | string | 是 | - | 文本描述（含环境声/对白意图更好） |
| `width` | int | 否* | `1344` | 宽；*纯文生建议填写 |
| `height` | int | 否* | `768` | 高 |
| `fps` | int | 否 | `24` | 输出帧率（固定 24） |
| `num_inference_steps` | int | 否 | `50` | 推理步数，越大越慢、质量通常更好 |
| `flow_shift` | float | 否 | `12` | 视频 sigma shift |
| `seed` | int | 否 | 固定整数 | 可复现；不传则随机 |
| `input_reference` | file | 否 | - | 首帧图片（`fl2va`）；不传则为 `t2va` |
| `extra_params` | string(JSON) | 是 | 见下表 | 模型专有参数 |

**`extra_params` 字段**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task` | string | 是 | `t2va` 或 `fl2va`（须与输入一致） |
| `duration` | float | 是 | 时长秒数，4–15；服务端对齐到合法帧数 `17n+5` |
| `audio_flow_shift` | float | 否 | 音频 sigma shift，推荐 `3.0` |

---

### 1.1 文生视频+音频（T2VA）

```bash
curl --fail-with-body -sS \
  -X POST http://127.0.0.1:9111/v1/videos/sync \
  -F 'prompt=At night, three cats march into a bedroom playing tiny brass instruments, then abruptly file out, with synchronized room ambience.' \
  -F 'width=1344' \
  -F 'height=768' \
  -F 'fps=24' \
  -F 'num_inference_steps=50' \
  -F 'flow_shift=12' \
  -F 'seed=1101' \
  -F 'extra_params={"task":"t2va","duration":5.0,"audio_flow_shift":3.0}' \
  -o minimax-h3-t2va.mp4
```

校验输出：

```bash
ffprobe -v error -show_entries \
  stream=index,codec_name,width,height,r_frame_rate,sample_rate,channels \
  -of json minimax-h3-t2va.mp4
```

期望：H.264 视频 24 FPS + AAC 立体声约 32 kHz。

### 1.2 首帧图生视频+音频（FL2VA）

```bash
curl --fail-with-body -sS \
  -X POST http://127.0.0.1:9111/v1/videos/sync \
  -F 'prompt=The camera slowly pushes in as the character turns and smiles, soft ambient room tone.' \
  -F 'input_reference=@/path/to/first_frame.png' \
  -F 'fps=24' \
  -F 'num_inference_steps=50' \
  -F 'flow_shift=12' \
  -F 'seed=42' \
  -F 'extra_params={"task":"fl2va","duration":5.0,"audio_flow_shift":3.0}' \
  -o minimax-h3-fl2va.mp4
```

说明：

- 图片边长建议在 `[256, 5760]`，宽高比约 5:2～2:5
- 可不传 `width`/`height`，由首帧比例决定（短边默认 768）
- 也可显式指定尺寸，例如 `-F 'width=1344' -F 'height=768'`

### 1.3 480p / 10 秒（16:9）

```bash
curl --fail-with-body -sS \
  -X POST http://127.0.0.1:9111/v1/videos/sync \
  -F 'prompt=At night, three cats march into a bedroom playing tiny brass instruments, then abruptly file out, with synchronized room ambience.' \
  -F 'width=832' \
  -F 'height=480' \
  -F 'fps=24' \
  -F 'num_inference_steps=50' \
  -F 'flow_shift=12' \
  -F 'seed=1101' \
  -F 'extra_params={"task":"t2va","duration":10.0,"audio_flow_shift":3.0}' \
  -o minimax-h3-t2va-480p-10s.mp4
```

首帧图生（480p / 10s）：

```bash
curl --fail-with-body -sS \
  -X POST http://127.0.0.1:9111/v1/videos/sync \
  -F 'prompt=The camera slowly pushes in as the character turns and smiles, soft ambient room tone.' \
  -F 'input_reference=@/path/to/first_frame.png' \
  -F 'width=832' \
  -F 'height=480' \
  -F 'fps=24' \
  -F 'num_inference_steps=50' \
  -F 'flow_shift=12' \
  -F 'seed=42' \
  -F 'extra_params={"task":"fl2va","duration":10.0,"audio_flow_shift":3.0}' \
  -o minimax-h3-fl2va-480p-10s.mp4
```

### 1.4 竖屏 9:16 文生

```bash
curl --fail-with-body -sS \
  -X POST http://127.0.0.1:9111/v1/videos/sync \
  -F 'prompt=A barista pours latte art in a sunny cafe, gentle chatter and espresso machine hiss in the background.' \
  -F 'width=768' \
  -F 'height=1344' \
  -F 'fps=24' \
  -F 'num_inference_steps=50' \
  -F 'flow_shift=12' \
  -F 'seed=7' \
  -F 'extra_params={"task":"t2va","duration":8.0,"audio_flow_shift":3.0}' \
  -o minimax-h3-t2va-9x16.mp4
```

---

## 2. 异步生成

适合长任务、避免 HTTP 超时被中间代理断开。流程：创建 → 轮询 → 下载。

### 2.1 创建任务

```bash
curl --fail-with-body -sS \
  -X POST http://127.0.0.1:9111/v1/videos \
  -H 'Accept: application/json' \
  -F 'prompt=A cinematic drone shot over misty mountains at sunrise, wind and distant birds.' \
  -F 'width=1344' \
  -F 'height=768' \
  -F 'fps=24' \
  -F 'num_inference_steps=50' \
  -F 'flow_shift=12' \
  -F 'seed=1101' \
  -F 'extra_params={"task":"t2va","duration":5.0,"audio_flow_shift":3.0}'
```

响应中取 `id`（字段名以实际返回为准，常见为 `id`）。

### 2.2 查询状态

```bash
VIDEO_ID="<上一步返回的 id>"
curl -sS "http://127.0.0.1:9111/v1/videos/${VIDEO_ID}"
```

### 2.3 下载成品

```bash
curl -sS "http://127.0.0.1:9111/v1/videos/${VIDEO_ID}/content" \
  -o minimax-h3-async.mp4
```

带首帧的异步示例：

```bash
curl --fail-with-body -sS \
  -X POST http://127.0.0.1:9111/v1/videos \
  -H 'Accept: application/json' \
  -F 'prompt=The person waves and walks toward the camera, footsteps on wooden floor.' \
  -F 'input_reference=@/path/to/first_frame.jpg' \
  -F 'fps=24' \
  -F 'num_inference_steps=50' \
  -F 'flow_shift=12' \
  -F 'seed=42' \
  -F 'extra_params={"task":"fl2va","duration":5.0,"audio_flow_shift":3.0}'
```

---

## 3. Python 示例（同步）

```python
import requests

BASE = "http://127.0.0.1:9111"

resp = requests.post(
    f"{BASE}/v1/videos/sync",
    data={
        "prompt": "A fox trots through fresh snow, soft crunching footsteps and winter wind.",
        "width": 1344,
        "height": 768,
        "fps": 24,
        "num_inference_steps": 50,
        "flow_shift": 12,
        "seed": 1101,
        "extra_params": '{"task":"t2va","duration":5.0,"audio_flow_shift":3.0}',
    },
    timeout=3600,
)
resp.raise_for_status()
with open("minimax-h3-t2va.mp4", "wb") as f:
    f.write(resp.content)
```

首帧图生：

```python
import requests

BASE = "http://127.0.0.1:9111"

with open("/path/to/first_frame.png", "rb") as img:
    resp = requests.post(
        f"{BASE}/v1/videos/sync",
        data={
            "prompt": "The camera slowly pushes in as the character turns and smiles.",
            "fps": 24,
            "num_inference_steps": 50,
            "flow_shift": 12,
            "seed": 42,
            "extra_params": '{"task":"fl2va","duration":5.0,"audio_flow_shift":3.0}',
        },
        files={"input_reference": ("first_frame.png", img, "image/png")},
        timeout=3600,
    )
resp.raise_for_status()
with open("minimax-h3-fl2va.mp4", "wb") as f:
    f.write(resp.content)
```

---

## 注意事项

1. **超时**：单次生成可达数分钟；同步请求请把客户端 / 网关超时调到 ≥ 1800s（与 `VLLM_OMNI_VIDEO_SYNC_TIMEOUT` 对齐）。
2. **并发**：当前 diffusion 批次通常一次只跑一条生成任务。
3. **首请求**：若启用 regional compile，第一次请求含编译预热，后续更稳。
4. **task 与分区**：本服务是 FL2VA，`extra_params.task` 只能是 `t2va` / `fl2va`；`ref2va` 会失败。
5. **请求体大小**：整包建议 < 64MB；大图优先本地上传 `input_reference`，勿塞超大 base64。
6. **远程访问**：把 `127.0.0.1` 换成宿主机 IP，并确保防火墙放行 `9111`。

## 参考

- [MiniMax-H3 vLLM Recipe](https://recipes.vllm.ai/MiniMaxAI/MiniMax-H3)
- [vLLM-Omni Videos API](https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/videos_api/)
- 本目录部署：`../docker-compose.yml`
