"""Download-progress persistence for crash recovery and resume.

State is written atomically via a temporary file + ``os.replace`` so that a
crash mid-write cannot corrupt the state file.  The format is a single JSON
object (see :class:`DownloadState`).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Set

from .utils import CONFIG_DIR, get_logger

logger = get_logger(__name__)
STATE_FILE = str(CONFIG_DIR / "download_state.json")


@dataclass
class DownloadState:
    """Tracks which lectures in a single course have been downloaded.

    Attributes:
        course_id: Udemy numeric course identifier.
        course_title: Human-readable course title (for log messages).
        completed_lectures: Set of lecture IDs that finished downloading.
        total_lectures: Expected total number of lectures in the course.
        last_updated: ISO-8601 timestamp of the most recent save.
    """

    course_id: Optional[int] = None
    course_title: str = ""
    completed_lectures: Set[int] = field(default_factory=set)
    total_lectures: int = 0
    last_updated: str = ""

    def to_dict(self) -> Dict:
        """Serialise to a JSON-compatible dict (sets → sorted lists)."""
        return {
            "course_id": self.course_id,
            "course_title": self.course_title,
            "completed_lectures": sorted(self.completed_lectures),
            "total_lectures": self.total_lectures,
            "last_updated": self.last_updated,
        }

    def mark_completed(self, lecture_id: int) -> None:
        """Record *lecture_id* as successfully downloaded."""
        self.completed_lectures.add(lecture_id)

    @classmethod
    def from_dict(cls, data: Dict) -> "DownloadState":
        """Reconstruct from a dict produced by :meth:`to_dict`.

        Unknown keys are silently ignored so that older state files remain
        forward-compatible.
        """
        completed = data.get("completed_lectures", [])
        return cls(
            course_id=data.get("course_id"),
            course_title=data.get("course_title", ""),
            completed_lectures=set(completed) if isinstance(completed, list) else set(),
            total_lectures=data.get("total_lectures", 0),
            last_updated=data.get("last_updated", ""),
        )


class AppState:
    """Application-level state wrapper that manages persistence.

    Holds the current :class:`DownloadState` and provides helpers to
    load / save / clear it from disk.
    """

    def __init__(self) -> None:
        self.interrupted: bool = False
        self.current_course_state: Optional[DownloadState] = None

    def load_state(self) -> Optional[DownloadState]:
        """Load the saved download state from disk.

        Returns ``None`` if no state file exists or if it is corrupted.
        """
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
        """Atomically persist the current course state to disk.

        Uses a temporary file + ``os.replace`` to prevent partial writes.
        Does nothing if :attr:`current_course_state` is ``None``.
        """
        if self.current_course_state is None:
            return
        state_path = Path(STATE_FILE)
        self.current_course_state.last_updated = datetime.now().isoformat()
        tmp_path: str | None = None
        try:
            fd, tmp_path = tempfile.mkstemp(dir=state_path.parent, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.current_course_state.to_dict(), f, indent=4)
            os.replace(tmp_path, str(state_path))
            os.chmod(state_path, 0o600)
            logger.debug("Download state saved")
        except OSError as e:
            logger.error(f"Failed to save download state: {e}")
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def clear_state(self) -> None:
        """Delete the state file and reset in-memory state."""
        state_path = Path(STATE_FILE)
        if state_path.exists():
            try:
                state_path.unlink()
                logger.debug("Download state cleared")
            except IOError as e:
                logger.error(f"Failed to clear download state: {e}")
        self.current_course_state = None
