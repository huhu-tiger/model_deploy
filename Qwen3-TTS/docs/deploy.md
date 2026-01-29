## Qwen3-TTS 部署教学文档（从 0 到可用接口）

本文档假设你拿到的是一台**干净的新机器**（没有现成的 conda 环境、没有代码目录、没有模型目录）。我们会从“机器准备”开始，一步步把 **OpenAI 风格**的 Qwen3-TTS 服务部署起来（支持 **CustomVoice / VoiceDesign / VoiceClone(Base)**），并将生成音频上传到 **MinIO** 后返回下载链接。

---

## 第一章 机器准备（配置要求 / GPU / SSH / 网络）

### 1.1 你将得到什么（部署目标）

完成部署后，你会得到一个 FastAPI 服务（默认端口 `6006`）：

- `GET /healthz`：健康检查
- `GET /v1/models`：模型列表（OpenAI 风格）
- `POST /v1/audio/speech`：CustomVoice 合成（预置 speaker + 可选 instruct）
- `POST /v1/audio/voice_design`：VoiceDesign 合成（instruct 驱动音色/风格）
- `POST /v1/audio/voice_clone`：Base VoiceClone（参考音频克隆音色）

所有音频结果都会：
- 先写入临时目录（默认 `/tmp/qwen3-tts-outputs`，见 `.env`）
- 上传至 MinIO（使用 `minio` 官方 Python SDK）
- 返回 MinIO 下载 URL（在响应字段 `output.choices[0].message.content[0].audio`）

### 1.2 官方仓库来源（建议先收藏）

本项目能力与模型说明可参考 Qwen 团队发布的官方仓库：
- `https://github.com/QwenLM/Qwen3-TTS`

如果你要“从官方仓库从零开始部署”，请优先以官方仓库 README/示例为基准，再结合本文档把服务化（API + MinIO）跑起来。

### 1.3 机器与网络前置条件（请先确认）

- **GPU**：建议使用 CUDA（可用 bfloat16），CPU 也可跑但速度慢且通常需 `float32`
- **MinIO**：需要可访问的 MinIO（Bucket / AK/SK 配置正确）
- **网络**：如果你用 HuggingFace Hub 下载模型，需要能访问 HF；否则请用离线模型目录

### 1.4 SSH 与端口要求（运维/交付常用）

教学建议你在开始前确认：
- **SSH 可登录**：能通过 `ssh user@host` 进入机器
- **端口开放**：默认服务端口 `6006` 需要在安全组/防火墙放行（按你们内网策略执行）
- **出网策略**：若需要从 HuggingFace 拉模型，机器需要具备对应出网权限；否则请走离线模型目录

---

## 第二章 安装基础工具（Python / conda / git 等）

本章目标：让新机器具备“拉代码 + 运行 Python 服务”的基本能力。

### 2.1 安装系统工具（git/ffmpeg/编译工具）

下面以 Linux 为例（Ubuntu/Debian 系）。你需要：
- `git`：拉代码
- `ffmpeg`（可选但推荐）：处理音频相关依赖时更省心
- `build-essential`（可选）：某些依赖编译时会用到

```bash
sudo apt update
sudo apt install -y git ffmpeg build-essential
```

> 教学提示：如果你的机器不是 Debian 系，换成对应发行版的包管理命令即可（例如 `yum`/`dnf`）。

### 2.2 安装 Miniconda（从 0 安装 conda）

如果你机器上已经有 conda，可跳过本节。

#### 2.2.1 下载并安装

（以 Linux x86_64 为例）

```bash
cd ~
curl -fsSL -o Miniconda3-latest-Linux-x86_64.sh \
  https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh -b -p ~/miniconda3
```

#### 2.2.2 初始化 conda（让 `conda activate` 生效）

```bash
~/miniconda3/bin/conda init bash
source ~/.bashrc
conda --version
```

> 教学提示：如果你用的是 zsh，把 `bash` 替换为 `zsh`。

### 2.3 创建 conda 环境（从 0 搭建 Python 运行环境）

下面以环境名 `qwen3-tts` 为例。

```bash
conda create -n qwen3-tts python=3.10 -y
conda activate qwen3-tts
```

### 2.4 安装 Python 依赖（教学：先跑起来，再优化）

先进入项目目录（代码在第三章拉取）后，再执行依赖安装。这里先给出“你会用到的依赖清单”：
- FastAPI：`fastapi`、`uvicorn`
- 数据与校验：`pydantic`
- 音频写文件：`soundfile`
- 推理：`torch`（按 CUDA 环境安装合适版本）
- MinIO SDK：`minio`
- `.env`：`python-dotenv`

> 教学建议：torch 安装请按你们团队内的 CUDA 版本标准来；避免现场临时选 wheel 导致不兼容。

### 2.5 安装依赖并验证导入（推荐执行一次）

在 `~/model_deploy/Qwen3-TTS` 执行：

```bash
conda activate qwen3-tts
pip install -U pip
pip install fastapi uvicorn pydantic soundfile python-dotenv minio
pip install -r requirements.txt || true
python -c "import api; print('api import ok')"
```

> 教学提示：`pip install -r requirements.txt` 如果文件不存在会失败，这里用 `|| true` 只是为了教学文档可复制；实际以你仓库是否提供 requirements 为准。

---

## 第三章 拉取官方代码 / 下载模型 / 配置 .env

本服务代码就是 **Qwen3-TTS** 仓库本身（包含 FastAPI 服务、推理逻辑、MinIO 上传封装）。

### 3.1 拉取官方代码（QwenLM/Qwen3-TTS）

选择一个工作目录（示例用 `~/model_deploy`）：

```bash
mkdir -p ~/model_deploy
cd ~/model_deploy
git clone https://github.com/QwenLM/Qwen3-TTS Qwen3-TTS
```

### 3.2 进入项目目录

```bash
cd ~/model_deploy/Qwen3-TTS
ls
```

你应当能看到 `api.py`、`qwen_tts/`、`services/`、`docs/` 等目录/文件。

### 3.3 下载/准备模型（最重要）

Qwen3-TTS 的三种能力对应三套模型（你也可以只部署其中一部分）：

- **CustomVoice**：例如 `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`
- **VoiceDesign**：例如 `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`
- **Base(VoiceClone)**：例如 `Qwen/Qwen3-TTS-12Hz-1.7B-Base`

#### 3.3.1 方式 A：使用本地模型目录（推荐生产环境）

你把模型下载到本地某个目录，例如：

- `/media/llm/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice/`
- `/media/llm/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign/`
- `/media/llm/Qwen/Qwen3-TTS-12Hz-1.7B-Base/`

然后在 `.env` 里配置对应的 `*_MODEL_PATH`（见 3.4）。

#### 3.3.2 方式 B：直接填 HuggingFace 模型 ID（适合实验）

如果服务器能访问 HF，你可以把 `.env` 中的 `*_MODEL_PATH` 留空/等于模型 ID，让代码运行时自动从 Hub 拉取。

> 教学建议：实验阶段用 B，正式部署用 A。

### 3.4 配置 `.env`（模型 + MinIO + 运行参数）

项目会在 `api.py` 中自动加载 `.env`（见 `load_env(...)`）。

你需要重点关心 3 类配置：

#### 3.4.1 模型配置

以你当前项目的 `.env` 为例（路径按实际修改）：

- `TTS_MODEL_ID` / `TTS_MODEL_PATH`：CustomVoice
- `TTS_VOICE_DESIGN_MODEL_ID` / `TTS_VOICE_DESIGN_MODEL_PATH`：VoiceDesign
- `TTS_BASE_MODEL_ID` / `TTS_BASE_MODEL_PATH`：Base/VoiceClone

#### 3.4.2 设备与精度

- `TTS_DEVICE`：例如 `cuda:2` 或 `cuda:0`，没有 GPU 就用 `cpu`
- `TTS_DTYPE`：
  - CUDA 推荐：`bfloat16`
  - CPU 推荐：`float32`
- `TTS_ATTN_IMPL`：默认 `flash_attention_2`（若环境不支持可改为其他实现）

#### 3.4.3 MinIO 配置

`.env` 里一般会有：
- `MINIO_IP`
- `MINIO_UPLOAD_PORT`
- `MINIO_UPLOAD_URL`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`
- `MINIO_BUCKET_NAME`
- `TTS_MINIO_UPLOAD_DIR`（桶内前缀目录，默认 `qwen3-tts`）

> 教学提醒：MinIO 连接由 `services/minio_uploader.py` 负责（`minio` 官方 SDK）。若 MinIO 不通，接口会返回 500 并带上错误信息。

---

## 第四章 编写核心代码（说明逻辑 / 关键文件）

本章回答一个核心问题：**为什么这套服务能跑？它是怎么把文本变成音频，并上传 MinIO 的？**

### 4.1 API 层：`api.py`

`api.py` 做三件事：
- 定义请求/响应 Pydantic 模型（尽量贴近 OpenAI 风格）
- 提供 FastAPI 路由（`/v1/audio/speech`、`/v1/audio/voice_design`、`/v1/audio/voice_clone`）
- 将推理工作交给 `services/`，并把结果组织成统一返回格式

### 4.2 业务层：`services/`

`services/` 目录把三种推理方式拆成 3 个文件：
- `services/custom_voice_service.py`：`generate_custom_voice(...)`
- `services/voice_design_service.py`：`generate_voice_design(...)`
- `services/base_voice_clone_service.py`：`generate_voice_clone(...)`

三者共同套路：
- 生成 waveform（numpy）+ sample_rate
- 写入临时文件（`TTS_OUTPUT_DIR`）
- 上传 MinIO
- 删除本地临时文件
- 返回：`minio_path + download_url + duration + sr`

### 4.3 核心逻辑代码片段（建议先看这几段）

（以下片段为真实源码引用，可直接在仓库中定位）

#### 片段 A：CustomVoice 推理 → 临时文件 → 上传 → 清理

```39:97:services/custom_voice_service.py
def synthesize_custom_voice_to_minio(
    *,
    model_path: str,
    device: str,
    dtype_str: str,
    attn_impl: str,
    text: str,
    language: str,
    speaker: str,
    instruct: str,
    response_format: str,
    output_dir: Path,
    minio_upload_dir: str,
    max_new_tokens: Optional[int] = None,
) -> Tuple[str, str, float, int]:
    """Return (minio_path, download_url, duration_sec, sample_rate)."""
    model = load_custom_voice_model(
        model_path=model_path,
        device=device,
        dtype_str=dtype_str,
        attn_impl=attn_impl,
    )

    gen_kwargs = {}
    if max_new_tokens:
        gen_kwargs["max_new_tokens"] = max_new_tokens

    wavs, sr = model.generate_custom_voice(
        text=text,
        language=language,
        speaker=speaker,
        instruct=instruct or "",
        **gen_kwargs,
    )

    if not wavs:
        raise RuntimeError("No audio generated")

    waveform = wavs[0]
    output_dir.mkdir(parents=True, exist_ok=True)
    ext = "wav" if response_format == "url" else response_format
    file_name = f"{uuid.uuid4().hex}.{ext}"
    file_path = output_dir / file_name
    sf.write(file_path, waveform, sr)
    duration = len(waveform) / float(sr) if sr else 0.0

    try:
        minio_path, download_url = upload_to_minio(
            file_path=file_path,
            upload_dir=minio_upload_dir,
            object_name=file_path.name,
        )
    finally:
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass

    return minio_path, download_url, duration, sr
```

#### 片段 B：Base(VoiceClone) 推理（ref_audio/ref_text/x_vector_only_mode）

```39:99:services/base_voice_clone_service.py
def synthesize_voice_clone_to_minio(
    *,
    model_path: str,
    device: str,
    dtype_str: str,
    attn_impl: str,
    text: str,
    language: str,
    ref_audio: Union[str, list[str]],
    ref_text: Optional[Union[str, list[Optional[str]]]],
    x_vector_only_mode: Union[bool, list[bool]] = False,
    response_format: str,
    output_dir: Path,
    minio_upload_dir: str,
    max_new_tokens: Optional[int] = None,
) -> Tuple[str, str, float, int]:
    """Return (minio_path, download_url, duration_sec, sample_rate)."""
    model = load_base_model(
        model_path=model_path,
        device=device,
        dtype_str=dtype_str,
        attn_impl=attn_impl,
    )

    gen_kwargs = {}
    if max_new_tokens:
        gen_kwargs["max_new_tokens"] = max_new_tokens

    wavs, sr = model.generate_voice_clone(
        text=text,
        language=language,
        ref_audio=ref_audio,
        ref_text=ref_text,
        x_vector_only_mode=x_vector_only_mode,
        **gen_kwargs,
    )

    if not wavs:
        raise RuntimeError("No audio generated")

    waveform = wavs[0]
    output_dir.mkdir(parents=True, exist_ok=True)
    ext = "wav" if response_format == "url" else response_format
    file_name = f"{uuid.uuid4().hex}.{ext}"
    file_path = output_dir / file_name
    sf.write(file_path, waveform, sr)
    duration = len(waveform) / float(sr) if sr else 0.0

    try:
        minio_path, download_url = upload_to_minio(
            file_path=file_path,
            upload_dir=minio_upload_dir,
            object_name=file_path.name,
        )
    finally:
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass

    return minio_path, download_url, duration, sr
```

#### 片段 C：API 层如何调用 service，并拼出 OpenAI 风格响应

```116:208:api.py
class VoiceCloneRequest(BaseModel):
	model: str = Field(default=BASE_MODEL_ID, description="Base model id or local path")
	input: str = Field(..., min_length=1, description="Text to synthesize")
	language: str = Field(default="Auto", description="Language hint")
	ref_audio: Union[str, List[str]] = Field(..., description="Reference audio: URL/local path/base64, or list")
	ref_text: Optional[Union[str, List[Optional[str]]]] = Field(
		default=None,
		description="Reference transcript(s). Required when x_vector_only_mode=False (ICL).",
	)
	x_vector_only_mode: Union[bool, List[bool]] = Field(
		default=False,
		description="True: speaker embedding only; False: ICL mode (requires ref_text).",
	)
	response_format: Literal["url", "wav", "flac"] = Field(default="url")
	stream: bool = Field(default=False, description="Streaming is not supported yet")
	max_new_tokens: Optional[int] = Field(default=None, gt=0, description="Optional generation limit")


@app.post("/v1/audio/speech", response_model=AudioSpeechResponse)
async def create_speech(req: SpeechRequest):
	if req.model.lower() != MODEL_ID.lower():
		raise HTTPException(status_code=400, detail=f"Model not available: {MODEL_ID}")

	if req.stream:
		raise HTTPException(status_code=400, detail="stream is not supported; set stream to false")

	try:
		minio_path, download_url, duration, _ = await asyncio.to_thread(
			synthesize_custom_voice_to_minio,
			model_path=MODEL_PATH,
			device=DEVICE,
			dtype_str=DTYPE_STR,
			attn_impl=ATTN_IMPL,
			text=req.input,
			language=req.language,
			speaker=req.voice,
			instruct=req.instruct or "",
			response_format=req.response_format,
			output_dir=OUTPUT_DIR,
			minio_upload_dir=MINIO_UPLOAD_DIR,
			max_new_tokens=req.max_new_tokens,
		)
	except Exception as exc:  # noqa: BLE001
		raise HTTPException(status_code=500, detail=str(exc)) from exc

	content = AudioContent(
		audio=download_url,
		format="wav" if req.response_format == "url" else req.response_format,
		minio_path=minio_path,
		duration=duration,
	)

	output = AudioOutput(
		choices=[
			AudioChoice(
				index=0,
				finish_reason="stop",
				message=ChoiceMessage(content=[content]),
			)
		],
		task_metric=TaskMetric(FAILED=0, SUCCEEDED=1, TOTAL=1),
	)

	usage = AudioUsage(duration=duration, input_length=len(req.input))

	resp = AudioSpeechResponse(
		id=str(uuid.uuid4()),
		object="audio.speech",
		created=int(time.time()),
		model=req.model,
		voice=req.voice,
		output=output,
		usage=usage,
		request_id=str(uuid.uuid4()),
	)
	return resp
```

### 4.4 MinIO 上传：`services/minio_uploader.py`

```9:27:services/minio_uploader.py
def upload_to_minio(
    *,
    file_path: Path,
    upload_dir: str,
    object_name: Optional[str] = None,
) -> Tuple[str, str]:
    """Upload a local file to MinIO and return (minio_path, download_url)."""
    upload_result = minio_handler.upload_file(
        file_path=str(file_path),
        upload_dir=upload_dir,
        object_name=object_name or file_path.name,
    )

    if upload_result.get("error"):
        raise RuntimeError(upload_result.get("error_str", "MinIO upload failed"))

    minio_path = upload_result.get("minio_put_path")
    download_url = minio_handler.generate_download_url(minio_path)
    return minio_path, download_url
```

---

## 第五章 接口说明（接口示例 / curl）

### 5.1 启动服务

#### 方式 A：直接运行 api.py

```bash
cd ~/model_deploy/Qwen3-TTS
conda activate qwen3-tts
python api.py
```

#### 方式 B：用 uvicorn 启动

```bash
cd ~/model_deploy/Qwen3-TTS
conda activate qwen3-tts
uvicorn api:app --host 0.0.0.0 --port 6006
```

### 5.2 健康检查

```bash
curl http://127.0.0.1:6006/healthz
```

### 5.3 CustomVoice：`POST /v1/audio/speech`

```bash
curl -X POST http://127.0.0.1:6006/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "input": "请用温柔的语气读下面这句话，祝你有美好的一天。",
    "voice": "Vivian",
    "language": "Chinese",
    "instruct": "温柔，微笑，放松",
    "response_format": "url",
    "stream": false,
    "max_new_tokens": 2048
  }'
```

### 5.4 VoiceDesign：`POST /v1/audio/voice_design`

```bash
curl -X POST http://127.0.0.1:6006/v1/audio/voice_design \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "input": "哥哥，你回来啦，人家等了你好久好久了，要抱抱！",
    "language": "Chinese",
    "instruct": "体现撒娇稚嫩的萝莉女声，音调偏高且起伏明显",
    "response_format": "url",
    "stream": false,
    "max_new_tokens": 2048
  }'
```

### 5.5 VoiceClone(Base)：`POST /v1/audio/voice_clone`

> 教学提示：`ref_audio` 支持 URL / 本地路径 / base64 音频字符串。ICL 模式（`x_vector_only_mode=false`）通常需要 `ref_text`。

```bash
curl -X POST http://127.0.0.1:6006/v1/audio/voice_clone \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    "input": "Good one. Okay, fine, I\u0027m just gonna leave this sock monkey here. Goodbye.",
    "language": "Auto",
    "ref_audio": "/path/to/clone_2.wav",
    "ref_text": "Okay. Yeah. I resent you. I love you. I respect you. But you know what? You blew it! And thanks to you.",
    "x_vector_only_mode": false,
    "response_format": "url",
    "stream": false,
    "max_new_tokens": 2048
  }'
```

---

## 第六章 常见报错与运维（排错 / 建议）

### 6.1 `python: command not found`

有些系统只提供 `python3`。你可以：
- 直接用 `python3 ...`
- 或在 conda 环境里 `which python` 检查

### 6.2 500：MinIO upload failed

请检查：
- `.env` 里 MinIO 的 `IP/PORT/AK/SK/BUCKET` 是否正确
- MinIO 是否可达（网络/防火墙）
- Bucket 是否存在/权限是否允许写入

### 6.3 400：model 不可用

请求体里的 `model` 必须严格匹配：
- `/v1/audio/speech` → `TTS_MODEL_ID`
- `/v1/audio/voice_design` → `TTS_VOICE_DESIGN_MODEL_ID`
- `/v1/audio/voice_clone` → `TTS_BASE_MODEL_ID`

### 6.4 CUDA / dtype / attention 报错

教学建议按顺序尝试：
- 把 `.env` 的 `TTS_DTYPE` 改成 `float32`
- 把 `TTS_ATTN_IMPL` 改成更保守的实现（视你的 transformers/环境支持情况）
- 确认 `TTS_DEVICE` 指向存在的 GPU（如 `cuda:0`）

### 6.5 运维建议（教学版）

- **进程管理**：生产建议用 `systemd`/`supervisor` 托管 uvicorn 进程，避免 SSH 断开后服务退出
- **日志**：建议将 uvicorn 输出重定向到文件，并配置 logrotate
- **健康检查**：可用 `GET /healthz` 做探活

