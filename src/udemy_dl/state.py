import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Set

from .utils import CONFIG_DIR, get_logger

logger = get_logger(__name__)
STATE_FILE = str(CONFIG_DIR / "download_state.json")


@dataclass
class DownloadState:
    course_id: Optional[int] = None
    course_title: str = ""
    completed_lectures: Set[int] = field(default_factory=set)
    total_lectures: int = 0
    last_updated: str = ""

    def to_dict(self) -> Dict:
        return {
            "course_id": self.course_id,
            "course_title": self.course_title,
            "completed_lectures": sorted(self.completed_lectures),
            "total_lectures": self.total_lectures,
            "last_updated": self.last_updated,
        }

    def mark_completed(self, lecture_id: int) -> None:
        self.completed_lectures.add(lecture_id)

    @classmethod
    def from_dict(cls, data: Dict) -> "DownloadState":
        completed = data.get("completed_lectures", [])
        return cls(
            course_id=data.get("course_id"),
            course_title=data.get("course_title", ""),
            completed_lectures=set(completed) if isinstance(completed, list) else set(),
            total_lectures=data.get("total_lectures", 0),
            last_updated=data.get("last_updated", ""),
        )


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
