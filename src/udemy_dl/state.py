import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .utils import CONFIG_DIR, get_logger

logger = get_logger(__name__)
STATE_FILE = str(CONFIG_DIR / "download_state.json")


@dataclass
class DownloadState:
    course_id: Optional[int] = None
    course_title: str = ""
    completed_lectures: List[int] = field(default_factory=list)
    total_lectures: int = 0
    last_updated: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "DownloadState":
        valid_keys = set(cls.__dataclass_fields__)
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class AppState:
    def __init__(self) -> None:
        self.interrupted = False
        self.current_course_state: Optional[DownloadState] = None

    def load_state(self) -> Optional[DownloadState]:
        state_path = Path(STATE_FILE)
        if state_path.exists():
            try:
                data = json.loads(state_path.read_text(encoding="utf-8"))
                return DownloadState.from_dict(data)
            except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
                logger.error(f"Failed to load download state: {e}")
                return None
        return None

    def save_state(self) -> None:
        if self.current_course_state is None:
            return
        state_path = Path(STATE_FILE)
        self.current_course_state.last_updated = datetime.now().isoformat()
        try:
            state_path.write_text(
                json.dumps(self.current_course_state.to_dict(), indent=4),
                encoding="utf-8",
            )
            os.chmod(state_path, 0o600)
            logger.debug("Download state saved")
        except IOError as e:
            logger.error(f"Failed to save download state: {e}")

    def clear_state(self) -> None:
        state_path = Path(STATE_FILE)
        if state_path.exists():
            try:
                state_path.unlink()
                logger.debug("Download state cleared")
            except IOError as e:
                logger.error(f"Failed to clear download state: {e}")
        self.current_course_state = None
