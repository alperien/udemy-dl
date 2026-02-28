import logging
import os
import re
from pathlib import Path

LOG_FILE = "downloader.log"

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        logger.propagate = False
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logger.addHandler(file_handler)
    return logger

def setup_logging() -> logging.Logger:
    logger = logging.getLogger("udemy_downloader")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(file_handler)
    return logger

def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '-', str(name)).strip() or "unknown"

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
    import subprocess
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=10
        )
        return float(result.stdout.strip()) > 0
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        return False
