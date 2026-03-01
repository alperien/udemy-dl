import functools
import logging
import os
import re
import shutil
from pathlib import Path

LOG_FILE = "downloader.log"


@functools.lru_cache(maxsize=1)
def _ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def get_logger(name: str) -> logging.Logger:
    canonical = name.replace("src.udemy_dl.", "udemy_dl.").replace("src.", "")
    logger = logging.getLogger(canonical)
    return logger


def setup_logging() -> logging.Logger:
    root = logging.getLogger("udemy_dl")
    if root.handlers:
        return root
    root.setLevel(logging.DEBUG)
    root.propagate = False
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(file_handler)
    return root


def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "-", str(name)).strip() or "unknown"


def time_string_to_seconds(time_str: str) -> int:
    try:
        clean_time = time_str.strip().split(".")[0]
        h, m, s = clean_time.split(":")
        return int(h) * 3600 + int(m) * 60 + int(s)
    except (ValueError, AttributeError):
        return 0


def set_secure_permissions(file_path: Path) -> None:
    try:
        os.chmod(file_path, 0o600)
    except OSError:
        pass


def validate_video(path: Path) -> bool:
    if not _ffprobe_available():
        return True

    import subprocess

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return float(result.stdout.strip()) > 0
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        return False
