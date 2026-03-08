from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

DIRECT_DOWNLOAD_TYPES: frozenset[str] = frozenset({"File", "Presentation", "Audio", "E-Book"})


@dataclass(frozen=True)
class Course:
    id: int
    title: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Course | None:
        course_id = data.get("id")
        title = data.get("title")
        if course_id and title:
            return cls(id=int(course_id), title=str(title))
        return None


@dataclass(frozen=True)
class Lecture:
    id: int | None
    title: str
    url: str
    file_path: Path
    asset_type: str = "Video"
    body: str = ""

    @property
    def has_video(self) -> bool:
        return self.asset_type == "Video" and bool(self.url)

    @property
    def has_url_based_download(self) -> bool:
        """True if lecture has a URL-based download (video stream or file asset)."""
        return bool(self.url)

    @property
    def is_direct_download(self) -> bool:
        """True for file-type assets that use HTTP download instead of ffmpeg."""
        return self.asset_type in DIRECT_DOWNLOAD_TYPES and bool(self.url)


@dataclass
class DownloadProgress:
    """Tracks download progress for a course.

    .. note::

       ``total_vids`` and ``done_vids`` count **all** lecture assets
       (video, file, article, …), not only videos.  The names are kept
       for backward compatibility.
    """

    course_title: str = ""
    total_vids: int = 0
    done_vids: int = 0
    current_file: str = "Initializing..."
    vid_duration_secs: int = 0
    vid_current_secs: int = 0

    @property
    def overall_percent(self) -> float:
        if self.total_vids <= 0:
            return 0.0
        return self.done_vids / self.total_vids * 100

    @property
    def video_percent(self) -> float:
        if self.vid_duration_secs <= 0:
            return 0.0
        return self.vid_current_secs / self.vid_duration_secs * 100
