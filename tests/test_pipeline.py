"""Tests for the unified download pipeline."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from udemy_dl.config import Config
from udemy_dl.models import Course, DownloadProgress
from udemy_dl.pipeline import DownloadPipeline
from udemy_dl.state import AppState


class MockReporter:
    """In-memory progress reporter for testing."""

    def __init__(self):
        self.logs = []
        self.progress_updates = []
        self._interrupted = False

    def on_log(self, message):
        self.logs.append(message)

    def on_progress(self, progress, ci, tc):
        self.progress_updates.append((progress, ci, tc))

    def is_interrupted(self):
        return self._interrupted


def _make_pipeline(reporter=None, config=None):
    cfg = config or Config(token="t" * 20, client_id="c" * 10)
    api = MagicMock()
    downloader = MagicMock()
    state = AppState()
    rep = reporter or MockReporter()
    return DownloadPipeline(cfg, api, downloader, state, rep), api, downloader, state, rep


class TestDownloadCourses:
    def test_clears_state_on_completion(self):
        pipeline, api, dl, state, rep = _make_pipeline()
        api.get_course_curriculum.return_value = []
        courses = [Course(id=1, title="Test")]

        pipeline.download_courses(courses)
        assert state.current_course_state is None  # cleared

    def test_saves_state_on_interrupt(self):
        rep = MockReporter()
        pipeline, api, dl, state, _ = _make_pipeline(reporter=rep)
        api.get_course_curriculum.return_value = []

        rep._interrupted = True
        courses = [Course(id=1, title="Test")]
        result = pipeline.download_courses(courses)
        assert result is False


class TestBuildDownloadQueue:
    def test_builds_queue_from_curriculum(self):
        pipeline, api, dl, state, rep = _make_pipeline()
        api.get_course_curriculum.return_value = [
            {"_class": "chapter", "title": "Chapter 1"},
            {"_class": "lecture", "title": "Lecture 1", "id": 101, "asset": None},
            {"_class": "lecture", "title": "Lecture 2", "id": 102, "asset": None},
        ]
        dl.get_quality_video_url.return_value = ""

        progress = DownloadProgress(course_title="Test")
        course = Course(id=1, title="Test")
        state.current_course_state = MagicMock()
        state.current_course_state.total_lectures = 0

        queue = pipeline._build_download_queue(course, progress)
        assert len(queue) == 2
        assert queue[0].title == "Lecture 1"
        assert queue[1].title == "Lecture 2"
        assert progress.total_vids == 2

    def test_uncategorized_chapter_for_orphan_lectures(self):
        pipeline, api, dl, state, rep = _make_pipeline()
        api.get_course_curriculum.return_value = [
            {"_class": "lecture", "title": "Orphan", "id": 1, "asset": None},
        ]
        dl.get_quality_video_url.return_value = ""

        progress = DownloadProgress()
        course = Course(id=1, title="Test")
        state.current_course_state = MagicMock()
        state.current_course_state.total_lectures = 0

        queue = pipeline._build_download_queue(course, progress)
        assert "00 - Uncategorized" in str(queue[0].file_path)


class TestDownloadLecture:
    def test_skips_completed_lecture(self):
        pipeline, api, dl, state, rep = _make_pipeline()
        state.current_course_state = MagicMock()
        dl.download_subtitles.return_value = []
        dl.download_materials.return_value = []

        from udemy_dl.models import Lecture

        lecture = Lecture(id=42, title="Done", url="http://x", file_path=Path("/tmp/test.mp4"))
        course = Course(id=1, title="Test")
        progress = DownloadProgress(total_vids=1)

        pipeline._download_lecture(lecture, course, progress, 1, 1, {42})

        assert progress.done_vids == 1
        assert any("CACHE" in log for log in rep.logs)

    def test_skips_no_video_lecture(self):
        pipeline, api, dl, state, rep = _make_pipeline()
        state.current_course_state = MagicMock()
        dl.download_subtitles.return_value = []
        dl.download_materials.return_value = []

        from udemy_dl.models import Lecture

        lecture = Lecture(id=10, title="Text Only", url="", file_path=Path("/tmp/test.mp4"))
        course = Course(id=1, title="Test")
        progress = DownloadProgress(total_vids=1)

        with patch.object(Path, "mkdir"):
            pipeline._download_lecture(lecture, course, progress, 1, 1, set())

        assert progress.done_vids == 1
        assert any("No video" in log for log in rep.logs)
