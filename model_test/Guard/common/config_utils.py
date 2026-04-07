import os


def get_concurrency(env_key: str, cli_concurrency: int | None, default: int = 1) -> int:
    if cli_concurrency is not None:
        return max(1, cli_concurrency)

    raw = os.getenv(env_key, str(default))
    try:
        value = int(raw.strip())
    except ValueError:
        value = default

    return max(1, value)
