import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Tuple

from .utils import CONFIG_DIR, get_logger, set_secure_permissions

logger = get_logger(__name__)

CONFIG_FILE = str(CONFIG_DIR / "config.json")

QUALITY_OPTIONS = ["2160", "1440", "1080", "720", "480", "360"]


@dataclass
class Config:
    domain: str = "https://www.udemy.com"
    token: str = ""
    client_id: str = ""
    dl_path: str = str(Path.home() / "Downloads" / "udemy-dl")
    quality: str = "1080"
    download_subtitles: bool = True
    download_materials: bool = True

    def validate(self) -> Tuple[bool, str]:
        if not self.token or len(self.token) < 10:
            return False, "Invalid or missing access token"
        if not self.client_id or len(self.client_id) < 5:
            return False, "Invalid or missing client_id"
        if not self.domain.startswith("https://"):
            return False, "Invalid domain URL (must start with https://)"
        if self.quality not in QUALITY_OPTIONS:
            return False, f"Invalid quality option. Choose from: {QUALITY_OPTIONS}"
        return True, ""

    def to_dict(self) -> dict:
        return asdict(self)


def load_config() -> Config:
    config = Config(
        domain=os.getenv("UDEMY_DOMAIN", "https://www.udemy.com"),
        token=os.getenv("UDEMY_TOKEN", ""),
        client_id=os.getenv("UDEMY_CLIENT_ID", ""),
        dl_path=os.getenv("UDEMY_DL_PATH", str(Path.home() / "Downloads" / "udemy-dl")),
        quality=os.getenv("UDEMY_QUALITY", "1080"),
        download_subtitles=os.getenv("UDEMY_DOWNLOAD_SUBTITLES", "true").lower() == "true",
        download_materials=os.getenv("UDEMY_DOWNLOAD_MATERIALS", "true").lower() == "true",
    )
    config_path = Path(CONFIG_FILE)
    if config_path.exists():
        try:
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            if not os.getenv("UDEMY_DOMAIN"):
                config.domain = str(saved.get("domain") or config.domain).strip()
            if not os.getenv("UDEMY_TOKEN"):
                config.token = str(saved.get("token") or config.token).strip()
            if not os.getenv("UDEMY_CLIENT_ID"):
                config.client_id = str(saved.get("client_id") or config.client_id).strip()
            if not os.getenv("UDEMY_DL_PATH"):
                saved_dl_path = str(saved.get("dl_path") or config.dl_path).strip()
                if saved_dl_path == "downloads":
                    config.dl_path = str(Path.home() / "Downloads" / "udemy-dl")
                else:
                    config.dl_path = saved_dl_path
            if not os.getenv("UDEMY_QUALITY"):
                config.quality = str(saved.get("quality") or config.quality).strip()
            if not os.getenv("UDEMY_DOWNLOAD_SUBTITLES"):
                config.download_subtitles = saved.get(
                    "download_subtitles", config.download_subtitles
                )
            if not os.getenv("UDEMY_DOWNLOAD_MATERIALS"):
                config.download_materials = saved.get(
                    "download_materials", config.download_materials
                )
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load config file: {e}")
    return config


def save_config(config: Config) -> None:
    config_path = Path(CONFIG_FILE)
    try:
        config_path.write_text(json.dumps(config.to_dict(), indent=4), encoding="utf-8")
        set_secure_permissions(config_path)
        logger.info("Configuration saved successfully")
    except IOError as e:
        logger.error(f"Failed to save config: {e}")
