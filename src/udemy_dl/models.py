"""Typed data models for API responses and download state.

Replaces the raw ``Dict`` structures that were previously threaded through
the codebase, providing compile-time type safety and self-documenting field
names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Course:
    """A Udemy course identified by its numeric ID and human-readable title."""

    id: int
    title: str

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> Optional["Course"]:
        """Parse a course from an API response dict.

        Returns ``None`` when the *id* or *title* field is missing /
        falsy, mirroring the previous filter that silently dropped
        incomplete records.
        """
        course_id = data.get("id")
        title = data.get("title")
        if course_id and title:
            return cls(id=int(course_id), title=str(title))
        return None


@dataclass(frozen=True)
class Lecture:
    """A single downloadable lecture within a course curriculum."""

    id: Optional[int]
    title: str
    url: str
    file_path: Path

    @property
    def has_video(self) -> bool:
        """Return ``True`` if the lecture has a downloadable video URL."""
        return bool(self.url)


@dataclass
class DownloadProgress:
    """Mutable progress state for the download dashboard.

    Used by both the TUI renderer and the headless progress printer so that
    progress logic is decoupled from presentation.
    """

    course_title: str = ""
    total_vids: int = 0
    done_vids: int = 0
    current_file: str = "Initializing..."
    vid_duration_secs: int = 0
    vid_current_secs: int = 0

    @property
    def overall_percent(self) -> float:
        """Percentage of videos completed (0–100)."""
        if self.total_vids <= 0:
            return 0.0
        return self.done_vids / self.total_vids * 100

    @property
    def video_percent(self) -> float:
        """Percentage of the *current* video downloaded (0–100)."""
        if self.vid_duration_secs <= 0:
            return 0.0
        return self.vid_current_secs / self.vid_duration_secs * 100
