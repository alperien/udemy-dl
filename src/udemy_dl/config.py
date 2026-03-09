from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path

from .utils import CONFIG_DIR, _ensure_config_dir, get_logger, set_secure_permissions

logger = get_logger(__name__)

CONFIG_FILE = str(CONFIG_DIR / "config.json")

QUALITY_OPTIONS = ["2160", "1440", "1080", "720", "480", "360"]

MIN_TOKEN_LENGTH = 10

MIN_CLIENT_ID_LENGTH = 5


@dataclass
class Config:
    domain: str = "https://www.udemy.com"
    token: str = ""
    client_id: str = ""
    dl_path: str = str(Path.home() / "Downloads" / "udemy-dl")
    quality: str = "1080"
    download_subtitles: bool = True
    download_materials: bool = True

    def validate(self) -> tuple[bool, str]:
        if not self.token or len(self.token) < MIN_TOKEN_LENGTH:
            return False, "Invalid or missing access token"
        if not self.client_id or len(self.client_id) < MIN_CLIENT_ID_LENGTH:
            return False, "Invalid or missing client_id"
        if not self.domain.startswith("https://"):
            return False, "Invalid domain URL (must start with https://)"
        if self.quality not in QUALITY_OPTIONS:
            return False, f"Invalid quality option. Choose from: {QUALITY_OPTIONS}"
        dl_path = Path(self.dl_path)
        if not dl_path.is_absolute():
            validated_dl_path = str(Path.home() / dl_path)
            dl_path = Path(validated_dl_path)
        if not dl_path.parent.exists():
            return False, f"Download path parent does not exist: {dl_path.parent}"
        return True, ""

    def to_dict(self) -> dict:
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
    if isinstance(val, bool):
        return val
    return str(val).lower() in ("true", "1", "yes")


def _merge_saved_config(config: Config) -> None:
    config_path = Path(CONFIG_FILE)
    if not config_path.exists():
        return

    try:
        saved = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load config file: {e}")
        return

    for env_key, field_name in _ENV_FIELD_MAP.items():
        if not os.getenv(env_key):
            val = saved.get(field_name)
            # Only override if saved value is non-empty
            if val and isinstance(val, str) and val.strip():
                setattr(config, field_name, val.strip())

    for env_key, field_name in _BOOL_ENV_FIELD_MAP.items():
        if not os.getenv(env_key):
            raw = saved.get(field_name, getattr(config, field_name))
            setattr(config, field_name, _parse_bool(raw))


def load_config() -> Config:
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
    _ensure_config_dir()
    config_path = Path(CONFIG_FILE)
    tmp_path: str | None = None
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=config_path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=4)
        Path(tmp_path).replace(config_path)
        set_secure_permissions(config_path)
        logger.info("Configuration saved successfully")
        return True
    except OSError as e:
        logger.error(f"Failed to save config: {e}")
        if tmp_path:
            with suppress(OSError):
                Path(tmp_path).unlink()
        return False
