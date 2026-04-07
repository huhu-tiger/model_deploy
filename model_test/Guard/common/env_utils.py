import os
from pathlib import Path

from dotenv import load_dotenv


def resolve_preferred_path(relative_path: str, script_dir: Path) -> Path:
    candidates = [script_dir / relative_path, Path.cwd() / relative_path]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def load_env_by_priority(script_dir: Path, env_file: str | None = None) -> Path:
    if env_file:
        env_path = Path(env_file)
    else:
        env_path = resolve_preferred_path(".env", script_dir)

    load_dotenv(dotenv_path=env_path, override=False)
    return env_path


def get_env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)
