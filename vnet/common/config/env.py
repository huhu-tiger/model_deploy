import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

_DEFAULT_DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"
_ENV_LOADED = False


def load_env(dotenv_path: Optional[str] = None, override: bool = False) -> Optional[Path]:
    """
    加载 .env 配置到环境变量。
    """
    global _ENV_LOADED
    if _ENV_LOADED and not override:
        return _DEFAULT_DOTENV_PATH if _DEFAULT_DOTENV_PATH.exists() else None

    target_path = Path(dotenv_path) if dotenv_path else _DEFAULT_DOTENV_PATH
    if target_path.is_file():
        load_dotenv(dotenv_path=target_path, override=override)
        _ENV_LOADED = True
        return target_path

    return None



def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """
    读取单个环境变量。
    """
    if not _ENV_LOADED:
        load_env()
    return os.getenv(name, default)




