from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .utils import CONFIG_DIR, _ensure_config_dir, get_logger

logger = get_logger(__name__)
STATE_FILE = str(CONFIG_DIR / "download_state.json")


@dataclass
class DownloadState:
    course_id: int | None = None
    course_title: str = ""
    completed_lectures: set[int] = field(default_factory=set)
    total_lectures: int = 0
    last_updated: str = ""

    def to_dict(self) -> dict:
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
    def from_dict(cls, data: dict) -> DownloadState:
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
        self.interrupted: bool = False
        self.current_course_state: DownloadState | None = None

    def load_state(self) -> DownloadState | None:
        state_path = Path(STATE_FILE)
        if state_path.exists():
            try:
                data = json.loads(state_path.read_text(encoding="utf-8"))
                return DownloadState.from_dict(data)
            except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
                logger.error(f"Failed to load download state: {e}")
                return None
        return None

    def save_state(self) -> None:
        if self.current_course_state is None:
            return
        _ensure_config_dir()
        state_path = Path(STATE_FILE)
        self.current_course_state.last_updated = datetime.now().isoformat()
        tmp_path: str | None = None
        try:
            fd, tmp_path = tempfile.mkstemp(dir=state_path.parent, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.current_course_state.to_dict(), f, indent=4)
            except Exception:
                os.close(fd)
                raise
            Path(tmp_path).chmod(0o600)
            Path(tmp_path).replace(state_path)
            logger.debug("Download state saved")
        except OSError as e:
            logger.error(f"Failed to save download state: {e}")
            if tmp_path:
                with suppress(OSError):
                    Path(tmp_path).unlink()

    def clear_state(self) -> None:
        state_path = Path(STATE_FILE)
        if state_path.exists():
            try:
                state_path.unlink()
                logger.debug("Download state cleared")
            except OSError as e:
                logger.error(f"Failed to clear download state: {e}")
        self.current_course_state = None
