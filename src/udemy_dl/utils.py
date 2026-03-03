"""Shared utilities: logging, filename sanitization, and video validation.

This module provides cross-cutting concerns used by every other module in
the package.  It is intentionally kept dependency-free (no imports from
sibling modules) to avoid circular-import issues.
"""

from __future__ import annotations

import enum
import functools
import logging
import os
import re
import shutil
from pathlib import Path



CONFIG_DIR = Path(os.getenv("UDEMY_DL_CONFIG_DIR", Path.home() / ".config" / "udemy-dl"))
try:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

LOG_FILE = str(CONFIG_DIR / "downloader.log")



_WINDOWS_RESERVED = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)

MAX_FILENAME_LENGTH = 200
"""Conservative cross-platform filename length limit (bytes)."""




@functools.lru_cache(maxsize=1)
def is_ffprobe_available() -> bool:
    """Return ``True`` if *ffprobe* is on ``$PATH``."""
    return shutil.which("ffprobe") is not None







def get_logger(name: str) -> logging.Logger:
    """Obtain a logger using the canonical ``udemy_dl.*`` namespace.

    When the package is invoked via ``python -m src.udemy_dl`` during
    development the module name may contain ``src.`` prefixes; this helper
    normalises them away so all log records are consistently namespaced.
    """
    canonical = name.replace("src.udemy_dl.", "udemy_dl.").replace("src.", "")
    return logging.getLogger(canonical)


def setup_logging() -> logging.Logger:
    """Initialise the root ``udemy_dl`` logger.

    Attaches a file handler (``INFO`` level) writing to :data:`LOG_FILE`.
    Idempotent – subsequent calls return the existing logger unchanged.
    """
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
    """Replace filesystem-unsafe characters and enforce safety constraints.

    * Replaces ``< > : " / \\ | ? *`` and C0 control characters with ``-``.
    * Strips leading / trailing whitespace and leading dots (hidden files).
    * Prefixes Windows reserved device names (``CON``, ``NUL``, …).
    * Truncates to :data:`MAX_FILENAME_LENGTH`.
    * Returns ``"unknown"`` for empty input.
    """
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", str(name)).strip()
    if not sanitized:
        return "unknown"

    sanitized = sanitized.lstrip(".")
    if not sanitized:
        return "unknown"

    stem = sanitized.split(".")[0].upper()
    if stem in _WINDOWS_RESERVED:
        sanitized = f"_{sanitized}"

    if len(sanitized) > MAX_FILENAME_LENGTH:
        sanitized = sanitized[:MAX_FILENAME_LENGTH]

    return sanitized





def time_string_to_seconds(time_str: str) -> int:
    """Parse an ``HH:MM:SS[.frac]`` string into total seconds.

    Returns ``0`` for any unparseable input rather than raising.
    """
    try:
        clean_time = time_str.strip().split(".")[0]
        h, m, s = clean_time.split(":")
        return int(h) * 3600 + int(m) * 60 + int(s)
    except (ValueError, AttributeError):
        return 0





def set_secure_permissions(file_path: Path) -> None:
    """Set file permissions to owner-only read/write (``0o600``).

    Fails silently on platforms where ``chmod`` is not supported (e.g. older
    Windows builds).
    """
    try:
        os.chmod(file_path, 0o600)
    except OSError:
        pass





class ValidationResult(enum.Enum):
    """Tri-state outcome of :func:`validate_video`."""

    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN = "unknown"
    """ffprobe is not available – validity could not be determined."""


def validate_video(path: Path) -> ValidationResult:
    """Probe *path* with ffprobe and return whether the file is playable.

    Returns :attr:`ValidationResult.UNKNOWN` when ffprobe is not installed,
    allowing callers to decide whether to trust file-size heuristics alone
    instead of silently treating every file as valid.
    """
    if not is_ffprobe_available():
        return ValidationResult.UNKNOWN

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
        duration = float(result.stdout.strip())
        return ValidationResult.VALID if duration > 0 else ValidationResult.INVALID
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        return ValidationResult.INVALID
