from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from vnet.common.storage.dal.minio.minio_conn import minio_handler


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

