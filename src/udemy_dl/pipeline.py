from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

from .api import UdemyAPI
from .config import Config
from .dl import VideoDownloader
from .exceptions import CurriculumFetchError
from .models import DIRECT_DOWNLOAD_TYPES, Course, DownloadProgress, Lecture
from .state import AppState, DownloadState
from .utils import (
    ValidationResult,
    get_logger,
    is_ffprobe_available,
    sanitize_filename,
    time_string_to_seconds,
    validate_video,
)

logger = get_logger(__name__)

DURATION_REGEX = re.compile(r"duration:\s*(?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?)")
STATS_REGEX = re.compile(r"time=(?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?)")


class ProgressReporter(Protocol):
    def on_log(self, message: str) -> None:
        ...

    def on_progress(
        self,
        progress: DownloadProgress,
        course_index: int,
        total_courses: int,
    ) -> None:
        ...

    def is_interrupted(self) -> bool:
        ...


class DownloadPipeline:
    def __init__(
        self,
        config: Config,
        api: UdemyAPI,
        downloader: VideoDownloader,
        state: AppState,
        reporter: ProgressReporter,
    ) -> None:
        self.config = config
        self.api = api
        self.downloader = downloader
        self.state = state
        self.reporter = reporter

    def download_courses(self, courses: list[Course]) -> bool:
        for i, course in enumerate(courses, 1):
            self._download_course(course, i, len(courses))
            if self.reporter.is_interrupted():
                self.state.save_state()
                return False

        self.state.clear_state()
        return True

    def _download_course(self, course: Course, index: int, total: int) -> None:
        self.state.current_course_state = DownloadState(
            course_id=course.id,
            course_title=course.title,
            total_lectures=0,
        )

        progress = DownloadProgress(course_title=course.title)

        try:
            download_queue = self._build_download_queue(course, progress)
        except CurriculumFetchError as e:
            self.reporter.on_log(f"[ERROR] {e }")
            self.reporter.on_progress(progress, index, total)
            return

        saved_state = self.state.load_state()
        completed_lectures: set[int] = set()
        if saved_state and saved_state.course_id == course.id:
            all_completed = set(saved_state.completed_lectures)
            # Filter to only include lectures where file actually exists
            completed_lectures = {
                lec.id
                for lec in download_queue
                if lec.id in all_completed and lec.file_path.exists()
            }
            missing_count = len(all_completed) - len(completed_lectures)
            if missing_count > 0:
                self.reporter.on_log(
                    f"[RESUME] Found {len (completed_lectures )} completed lectures "
                    f"({missing_count } files missing, will re-download)"
                )
            elif completed_lectures:
                self.reporter.on_log(
                    f"[RESUME] Found {len (completed_lectures )} previously completed lectures"
                )

        for lecture in download_queue:
            if self.reporter.is_interrupted():
                self.reporter.on_log("[WARN] Download interrupted. Saving progress...")
                self.state.save_state()
                break
            self._download_lecture(lecture, course, progress, index, total, completed_lectures)

    def _build_download_queue(self, course: Course, progress: DownloadProgress) -> list[Lecture]:
        curriculum = self.api.get_course_curriculum(course.id)
        download_queue: list[Lecture] = []
        chapter_index = 0
        lecture_index = 0
        current_chapter_dir: Path | None = None
        base_dir = Path(self.config.dl_path) / sanitize_filename(course.title)

        for item in curriculum:
            item_type = item.get("_class")
            clean_title = sanitize_filename(str(item.get("title") or "Unknown"))

            if item_type == "chapter":
                chapter_index += 1
                lecture_index = 0
                current_chapter_dir = base_dir / f"{chapter_index :02d} - {clean_title }"
            elif item_type == "lecture":
                lecture_index += 1
                lecture_id = item.get("id")
                asset = item.get("asset")
                asset_type = (asset.get("asset_type") or "Video") if asset else "Video"

                if asset_type == "Video":
                    url = self.downloader.get_quality_video_url(asset) if asset else ""
                    ext = ".mp4"
                elif asset_type in DIRECT_DOWNLOAD_TYPES:
                    url = self.downloader.get_asset_download_url(asset) if asset else ""
                    filename = (asset.get("filename") or "") if asset else ""
                    file_ext = Path(filename).suffix.lower() if filename else ""
                    ext = (
                        file_ext
                        if file_ext
                        else {
                            "File": ".pdf",
                            "Presentation": ".pdf",
                            "Audio": ".mp3",
                            "E-Book": ".pdf",
                        }.get(asset_type, ".bin")
                    )
                elif asset_type == "Article":
                    url = ""
                    ext = ".html"
                else:
                    url = str(asset.get("external_url") or "") if asset else ""
                    ext = ".html"

                article_body = ""
                if asset_type == "Article" and asset:
                    article_body = asset.get("body", "") or ""

                if not current_chapter_dir:
                    current_chapter_dir = base_dir / "00 - Uncategorized"
                file_path = current_chapter_dir / f"{lecture_index :03d} - {clean_title }{ext }"
                download_queue.append(
                    Lecture(
                        id=lecture_id,
                        title=clean_title,
                        url=url,
                        file_path=file_path,
                        asset_type=asset_type,
                        body=article_body,
                    )
                )
                progress.total_vids += 1
                if self.state.current_course_state:
                    self.state.current_course_state.total_lectures += 1

        return download_queue

    def _download_lecture(
        self,
        lecture: Lecture,
        course: Course,
        progress: DownloadProgress,
        course_index: int,
        total_courses: int,
        completed_lectures: set[int],
    ) -> None:
        progress.current_file = lecture.title
        self.reporter.on_progress(progress, course_index, total_courses)

        out_path = lecture.file_path
        out_path.parent.mkdir(parents=True, exist_ok=True)

        def download_extras() -> None:
            if self.config.download_subtitles and lecture.id:
                subs = self.downloader.download_subtitles(course.id, lecture.id, out_path)
                if subs:
                    self.reporter.on_log(f"[SUBS] Downloaded {len (subs )} subtitle track(s)")
            if self.config.download_materials and lecture.id:
                mats = self.downloader.download_materials(
                    course.id,
                    lecture.id,
                    out_path,
                    self.reporter.is_interrupted,
                )
                if mats:
                    self.reporter.on_log(f"[MATS] Downloaded {len (mats )} material file(s)")

        if lecture.id and lecture.id in completed_lectures:
            # Check if file actually exists before skipping
            file_exists = lecture.file_path.exists()
            logger.debug(
                f"[DEBUG] State cache check - lecture_id={lecture.id}, "
                f"in_completed_set=True, file_exists={file_exists}, "
                f"path={lecture.file_path}"
            )
            if not file_exists:
                # File was deleted but still in state - need to re-download
                logger.info(
                    f"[INFO] File missing but in completed state - will re-download: {lecture.title}"
                )
                # Don't skip - fall through to download logic
            else:
                self.reporter.on_log(f"[CACHE] Skipping completed lecture: {lecture.title[:30]}...")
                progress.done_vids += 1
                if self.state.current_course_state:
                    self.state.current_course_state.mark_completed(lecture.id)
                download_extras()
                return

        # --- Asset-type routing ---

        # Case 1: No downloadable content at all
        if not lecture.has_url_based_download:
            if lecture.asset_type == "Article" and lecture.body:
                self.reporter.on_log(f"[DOWNLOAD] Saving article: {lecture .title [:30 ]}...")
                try:
                    out_path.write_text(lecture.body, encoding="utf-8")
                    self.reporter.on_log(f"[DONE] Saved article: {lecture .title [:30 ]}")
                except OSError as e:
                    self.reporter.on_log(f"[ERROR] Failed to save article: {e }")
            else:
                self.reporter.on_log(
                    f"[INFO] No downloadable asset for: {lecture .title [:30 ]}..."
                )
            progress.done_vids += 1
            if lecture.id and self.state.current_course_state:
                self.state.current_course_state.mark_completed(lecture.id)
                self.state.save_state()
            download_extras()
            return

        # Case 2: Direct HTTP download (PDF, Presentation, Audio, E-Book)
        if lecture.is_direct_download:
            if out_path.exists() and out_path.stat().st_size > 500:
                size_mb = out_path.stat().st_size / (1024 * 1024)
                self.reporter.on_log(
                    f"[CACHE] Skipping existing {lecture .asset_type }: "
                    f"{lecture .title [:20 ]}... ({size_mb :.1f}MB)"
                )
                progress.done_vids += 1
                if lecture.id and self.state.current_course_state:
                    self.state.current_course_state.mark_completed(lecture.id)
                    self.state.save_state()
                download_extras()
                return

            self.reporter.on_log(
                f"[DOWNLOAD] Fetching {lecture .asset_type }: {lecture .title [:30 ]}..."
            )
            success = self.downloader.download_file(
                lecture.url, out_path, self.reporter.is_interrupted
            )
            if self.reporter.is_interrupted():
                return
            if success:
                progress.done_vids += 1
                self.reporter.on_log(
                    f"[DONE] Saved {lecture .asset_type }: {lecture .title [:30 ]}"
                )
                if lecture.id and self.state.current_course_state:
                    self.state.current_course_state.mark_completed(lecture.id)
                    self.state.save_state()
            else:
                self.reporter.on_log(f"[ERROR] Download failed: {lecture .title [:30 ]}")
            download_extras()
            return

        # Case 3: Video download via ffmpeg
        if not lecture.has_video:
            # Safety net: no video URL but asset_type claims Video
            self.reporter.on_log(f"[INFO] No video stream for: {lecture .title [:30 ]}...")
            progress.done_vids += 1
            if lecture.id and self.state.current_course_state:
                self.state.current_course_state.mark_completed(lecture.id)
                self.state.save_state()
            download_extras()
            return

        if out_path.exists() and out_path.stat().st_size > 1024:
            validity = validate_video(out_path)
            if validity in (ValidationResult.VALID, ValidationResult.UNKNOWN):
                size_mb = out_path.stat().st_size / (1024 * 1024)
                self.reporter.on_log(
                    f"[CACHE] Skipping existing file: "
                    f"{lecture .title [:20 ]}... ({size_mb :.1f}MB)"
                )
                progress.done_vids += 1
                if lecture.id and self.state.current_course_state:
                    self.state.current_course_state.mark_completed(lecture.id)
                    self.state.save_state()
                download_extras()
                return
            self.reporter.on_log(
                f"[WARN] Invalid file detected, re-downloading: " f"{lecture .title [:20 ]}"
            )
            out_path.unlink()
        elif out_path.exists():
            self.reporter.on_log(f"[WARN] Overwriting partial file: {lecture .title [:20 ]}")

        self.reporter.on_log(f"[DOWNLOAD] Starting: {lecture .title [:30 ]}...")
        proc = self.downloader.download_video(lecture.url, out_path)

        progress.vid_duration_secs = 0
        progress.vid_current_secs = 0

        try:
            for line in self.downloader.read_ffmpeg_output(proc):
                if self.reporter.is_interrupted():
                    proc.terminate()
                    self.reporter.on_log("[WARN] FFmpeg terminated by user")
                    break
                if progress.vid_duration_secs == 0:
                    match = DURATION_REGEX.search(line)
                    if match:
                        time_val = match.group("time").split(".")[0]
                        progress.vid_duration_secs = time_string_to_seconds(time_val)
                if match := STATS_REGEX.search(line):
                    time_val = match.group("time").split(".")[0]
                    progress.vid_current_secs = min(
                        time_string_to_seconds(time_val),
                        progress.vid_duration_secs,
                    )
                self.reporter.on_progress(progress, course_index, total_courses)
        except (OSError, ValueError) as e:
            logger.error(f"Error reading ffmpeg output: {e }")

        returncode = self.downloader.wait_for_download(proc)

        if self.reporter.is_interrupted():
            return

        validity = validate_video(out_path)
        is_valid = validity in (ValidationResult.VALID, ValidationResult.UNKNOWN)
        if returncode != 0:
            self.reporter.on_log(f"[WARN] FFmpeg exited with code {returncode }")
            if not is_ffprobe_available():
                is_valid = False

        if out_path.exists() and is_valid:
            progress.done_vids += 1
            self.reporter.on_log(f"[DONE] Finished: {lecture .title [:30 ]}")
            if lecture.id and self.state.current_course_state:
                self.state.current_course_state.mark_completed(lecture.id)
                self.state.save_state()
            download_extras()
        else:
            self.reporter.on_log(
                f"[ERROR] Download failed or invalid file: {lecture .title [:30 ]}"
            )
            if out_path.exists():
                out_path.unlink()
