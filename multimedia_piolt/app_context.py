import logging
import os
import sys
from pathlib import Path

# Ensure project root on path for vnet imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load environment variables early so downstream imports see them
from vnet.common.config.env import load_env, get_env  # noqa: E402

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_env(str(ENV_PATH), override=False)

# Resolve log paths from env
LOG_LEVEL = get_env("LOG_LEVEL", "INFO")
LOG_DIR = Path(get_env("LOG_DIR", "logs"))
LOG_FILE_NAME = get_env("LOG_FILE_NAME", "api.log")
LOG_DIR_ABS = Path(__file__).resolve().parent / LOG_DIR
LOG_DIR_ABS.mkdir(parents=True, exist_ok=True)
LOG_FILE_PATH = LOG_DIR_ABS / LOG_FILE_NAME

# Initialize Logger
logger = None
try:
    from vnet.common.logger import BaseLogger  # noqa: E402
    _log_instance = BaseLogger(
        name=None,
        level=LOG_LEVEL,
        log_to_file=True,
        log_file_path=str(LOG_FILE_PATH),
        log_prefix="API",
        max_days=int(get_env("LOG_MAX_DAYS", "7"))
    )
    logger = _log_instance
except ImportError:
    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logger = logging.getLogger("api")
    logger.warning("Could not import BaseLogger from vnet.common.logger, using default logging")

try:
    from vnet.common.tools.http_utils import download_file_via_http  # noqa: E402
except ImportError:
    logger.warning("Could not import download_file_via_http from vnet.common.tools.http_utils")
    download_file_via_http = None

try:
    from vnet.common.storage.dal.minio.minio_conn import minio_handler  # noqa: E402
except ImportError:
    logger.warning("Could not import minio_handler from vnet.common.storage.dal.minio.minio_conn")
    minio_handler = None
except Exception as e:
    logger.warning(f"Failed to initialize minio_handler: {e}")
    minio_handler = None

DATA_ROOT = Path(get_env("DATA_ROOT", "data"))
VIDEO_DIR = Path(get_env("VIDEO_DIR", str(DATA_ROOT / "video")))
VIDEO_OUTPUT_DIR = Path(get_env("VIDEO_OUTPUT_DIR", str(VIDEO_DIR / "output")))
VIDEO_DOWNLOAD_DIR = Path(get_env("VIDEO_DOWNLOAD_DIR", str(VIDEO_DIR / "download")))
VIDEO_TEMP_DIR = Path(get_env("VIDEO_TEMP_DIR", str(VIDEO_DIR / "temp")))
RESOURCE_DIR = Path(get_env("RESOURCE_DIR", "resources"))
RESOURCE_AUDIO_DIR = Path(get_env("RESOURCE_AUDIO_DIR", str(RESOURCE_DIR / "audio")))
RESOURCE_TTF_DIR = Path(get_env("RESOURCE_TTF_DIR", str(RESOURCE_DIR / "ttf")))
RESOURCE_VIDEO_DIR = Path(get_env("RESOURCE_VIDEO_DIR", str(RESOURCE_DIR / "video")))

for path in [
    DATA_ROOT,
    VIDEO_DIR,
    VIDEO_OUTPUT_DIR,
    VIDEO_DOWNLOAD_DIR,
    VIDEO_TEMP_DIR,
    RESOURCE_DIR,
    RESOURCE_AUDIO_DIR,
    RESOURCE_TTF_DIR,
    RESOURCE_VIDEO_DIR,
]:
    path.mkdir(parents=True, exist_ok=True)

# Backward-compatible aliases
TEMP_DIR = str(VIDEO_TEMP_DIR)
OUTPUT_DIR = str(VIDEO_OUTPUT_DIR)
DOWNLOAD_DIR = str(VIDEO_DOWNLOAD_DIR)
RESOURCE_PATH = str(RESOURCE_DIR)
RESOURCE_AUDIO_PATH = str(RESOURCE_AUDIO_DIR)
RESOURCE_TTF_PATH = str(RESOURCE_TTF_DIR)
RESOURCE_VIDEO_PATH = str(RESOURCE_VIDEO_DIR)
