from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional, Tuple

import soundfile as sf
import torch

from qwen_tts import Qwen3TTSModel
from services.minio_uploader import upload_to_minio


def _resolve_dtype(dtype_str: str) -> torch.dtype:
    try:
        return getattr(torch, dtype_str)
    except Exception:
        return torch.float32


_custom_voice_model: Optional[Qwen3TTSModel] = None


def load_custom_voice_model(*, model_path: str, device: str, dtype_str: str, attn_impl: str) -> Qwen3TTSModel:
    global _custom_voice_model
    if _custom_voice_model is not None:
        return _custom_voice_model

    dtype = _resolve_dtype(dtype_str)
    _custom_voice_model = Qwen3TTSModel.from_pretrained(
        model_path,
        device_map=device,
        dtype=dtype,
        attn_implementation=attn_impl,
    )
    return _custom_voice_model


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

