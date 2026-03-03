"""Application configuration: loading, validation, and persistence.

Configuration values are resolved in priority order:

1. Environment variables (``UDEMY_TOKEN``, ``UDEMY_CLIENT_ID``, …)
2. Saved configuration file (``~/.config/udemy-dl/config.json``)
3. Built-in defaults
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Tuple

from .utils import CONFIG_DIR, get_logger, set_secure_permissions

logger = get_logger(__name__)

CONFIG_FILE = str(CONFIG_DIR / "config.json")

QUALITY_OPTIONS = ["2160", "1440", "1080", "720", "480", "360"]
"""Supported video quality labels, highest-to-lowest."""

MIN_TOKEN_LENGTH = 10
"""Minimum character count for an access token to be considered plausible."""

MIN_CLIENT_ID_LENGTH = 5
"""Minimum character count for a client_id to be considered plausible."""


@dataclass
class Config:
    """Runtime configuration for the downloader.

    All fields have sensible defaults so a bare ``Config()`` can be
    instantiated for testing.  Call :meth:`validate` before using the
    configuration for network operations.
    """

    domain: str = "https://www.udemy.com"
    token: str = ""
    client_id: str = ""
    dl_path: str = str(Path.home() / "Downloads" / "udemy-dl")
    quality: str = "1080"
    download_subtitles: bool = True
    download_materials: bool = True

    def validate(self) -> Tuple[bool, str]:
        """Check that all required fields are present and well-formed.

        Returns:
            A ``(ok, message)`` tuple.  *ok* is ``True`` when the
            configuration is valid; otherwise *message* explains the
            first validation failure encountered.
        """
        if not self.token or len(self.token) < MIN_TOKEN_LENGTH:
            return False, "Invalid or missing access token"
        if not self.client_id or len(self.client_id) < MIN_CLIENT_ID_LENGTH:
            return False, "Invalid or missing client_id"
        if not self.domain.startswith("https://"):
            return False, "Invalid domain URL (must start with https://)"
        if self.quality not in QUALITY_OPTIONS:
            return False, f"Invalid quality option. Choose from: {QUALITY_OPTIONS}"
        return True, ""

    def to_dict(self) -> dict:
        """Serialise the configuration to a plain ``dict``."""
        return asdict(self)




_ENV_FIELD_MAP = {
    "UDEMY_DOMAIN": "domain",
    "UDEMY_TOKEN": "token",
    "UDEMY_CLIENT_ID": "client_id",
    "UDEMY_DL_PATH": "dl_path",
    "UDEMY_QUALITY": "quality",
}

_BOOL_ENV_FIELD_MAP = {
    "UDEMY_DOWNLOAD_SUBTITLES": "download_subtitles",
    "UDEMY_DOWNLOAD_MATERIALS": "download_materials",
}


def _parse_bool(val: object, default: bool = True) -> bool:
    """Coerce a JSON/env value to ``bool``."""
    if isinstance(val, bool):
        return val
    return str(val).lower() in ("true", "1", "yes")


def _merge_saved_config(config: Config) -> None:
    """Overlay previously saved values where environment variables are absent."""
    config_path = Path(CONFIG_FILE)
    if not config_path.exists():
        return

    try:
        saved = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load config file: {e}")
        return

    for env_key, field_name in _ENV_FIELD_MAP.items():
        if not os.getenv(env_key):
            val = str(saved.get(field_name) or getattr(config, field_name)).strip()
            setattr(config, field_name, val)

    if not os.getenv("UDEMY_DL_PATH") and config.dl_path == "downloads":
        config.dl_path = str(Path.home() / "Downloads" / "udemy-dl")

    for env_key, field_name in _BOOL_ENV_FIELD_MAP.items():
        if not os.getenv(env_key):
            raw = saved.get(field_name, getattr(config, field_name))
            setattr(config, field_name, _parse_bool(raw))


def load_config() -> Config:
    """Build a :class:`Config` from environment variables and saved file.

    Environment variables take precedence; see module docstring for the
    full resolution order.
    """
    config = Config(
        domain=os.getenv("UDEMY_DOMAIN", "https://www.udemy.com"),
        token=os.getenv("UDEMY_TOKEN", ""),
        client_id=os.getenv("UDEMY_CLIENT_ID", ""),
        dl_path=os.getenv("UDEMY_DL_PATH", str(Path.home() / "Downloads" / "udemy-dl")),
        quality=os.getenv("UDEMY_QUALITY", "1080"),
        download_subtitles=_parse_bool(os.getenv("UDEMY_DOWNLOAD_SUBTITLES", "true")),
        download_materials=_parse_bool(os.getenv("UDEMY_DOWNLOAD_MATERIALS", "true")),
    )
    _merge_saved_config(config)
    return config





def save_config(config: Config) -> bool:
    """Atomically persist *config* to disk.

    Uses a temporary file + ``os.replace`` so a crash mid-write cannot
    corrupt the config file.  Sets ``0o600`` permissions on success.

    Returns:
        ``True`` if the file was written successfully, ``False`` otherwise.
    """
    config_path = Path(CONFIG_FILE)
    tmp_path: str | None = None
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=config_path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=4)
        os.replace(tmp_path, str(config_path))
        set_secure_permissions(config_path)
        logger.info("Configuration saved successfully")
        return True
    except OSError as e:
        logger.error(f"Failed to save config: {e}")
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return False
