from pathlib import Path
from unittest.mock import MagicMock, patch

from udemy_dl.config import Config
from udemy_dl.models import Course, DownloadProgress
from udemy_dl.pipeline import DownloadPipeline
from udemy_dl.state import AppState


class MockReporter:
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
        assert state.current_course_state is None

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
    def test_skips_completed_lecture_when_file_exists(self):
        pipeline, api, dl, state, rep = _make_pipeline()
        state.current_course_state = MagicMock()
        dl.download_subtitles.return_value = []
        dl.download_materials.return_value = []

        import tempfile

        from udemy_dl.models import Lecture

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            temp_path = Path(f.name)

        try:
            lecture = Lecture(id=42, title="Done", url="http://x", file_path=temp_path)
            course = Course(id=1, title="Test")
            progress = DownloadProgress(total_vids=1)

            pipeline._download_lecture(lecture, course, progress, 1, 1, {42})

            assert progress.done_vids == 1
            assert any("CACHE" in log for log in rep.logs)
        finally:
            temp_path.unlink()

    def test_re_downloads_missing_file_when_in_completed_state(self):
        pipeline, api, dl, state, rep = _make_pipeline()
        state.current_course_state = MagicMock()
        dl.download_subtitles.return_value = []
        dl.download_materials.return_value = []

        from udemy_dl.models import Lecture

        lecture = Lecture(
            id=42, title="Done", url="http://x", file_path=Path("/tmp/nonexistent_test_file.mp4")
        )
        course = Course(id=1, title="Test")
        progress = DownloadProgress(total_vids=1)

        pipeline._download_lecture(lecture, course, progress, 1, 1, {42})

        cache_messages = [log for log in rep.logs if "CACHE" in log]
        assert (
            len(cache_messages) == 0
        ), f"Should not skip when file missing, but got: {cache_messages}"

    def test_skips_no_video_stream_lecture(self):
        pipeline, api, dl, state, rep = _make_pipeline()
        state.current_course_state = MagicMock()
        dl.download_subtitles.return_value = []
        dl.download_materials.return_value = []

        from udemy_dl.models import Lecture

        lecture = Lecture(
            id=10, title="Text Only", url="", file_path=Path("/tmp/test.mp4"), asset_type="Video"
        )
        course = Course(id=1, title="Test")
        progress = DownloadProgress(total_vids=1)

        with patch.object(Path, "mkdir"), patch.object(state, "save_state"):
            pipeline._download_lecture(lecture, course, progress, 1, 1, set())

        assert progress.done_vids == 1
        assert any("No downloadable asset" in log for log in rep.logs)

    def test_no_downloadable_asset_logs_info(self):
        pipeline, api, dl, state, rep = _make_pipeline()
        state.current_course_state = MagicMock()
        dl.download_subtitles.return_value = []
        dl.download_materials.return_value = []

        from udemy_dl.models import Lecture

        lecture = Lecture(
            id=60,
            title="External Lab",
            url="",
            file_path=Path("/tmp/test.html"),
            asset_type="ImportedContent",
        )
        course = Course(id=1, title="Test")
        progress = DownloadProgress(total_vids=1)

        with patch.object(Path, "mkdir"), patch.object(state, "save_state"):
            pipeline._download_lecture(lecture, course, progress, 1, 1, set())

        assert progress.done_vids == 1
        assert any("No downloadable asset" in log for log in rep.logs)

    def test_routes_file_type_to_download_file(self):
        pipeline, api, dl, state, rep = _make_pipeline()
        state.current_course_state = MagicMock()
        dl.download_file.return_value = True
        dl.download_subtitles.return_value = []
        dl.download_materials.return_value = []

        from udemy_dl.models import Lecture

        lecture = Lecture(
            id=50,
            title="Slides",
            url="http://x/s.pdf",
            file_path=Path("/tmp/test.pdf"),
            asset_type="Presentation",
        )
        course = Course(id=1, title="Test")
        progress = DownloadProgress(total_vids=1)

        with patch.object(Path, "mkdir"), patch.object(
            Path, "exists", return_value=False
        ), patch.object(state, "save_state"):
            pipeline._download_lecture(lecture, course, progress, 1, 1, set())

        dl.download_file.assert_called_once()
        assert progress.done_vids == 1
        assert any("DONE" in log for log in rep.logs)

    def test_caches_existing_file_type(self):
        pipeline, api, dl, state, rep = _make_pipeline()
        state.current_course_state = MagicMock()
        dl.download_subtitles.return_value = []
        dl.download_materials.return_value = []

        from udemy_dl.models import Lecture

        lecture = Lecture(
            id=51,
            title="Notes",
            url="http://x/n.pdf",
            file_path=Path("/tmp/test.pdf"),
            asset_type="File",
        )
        course = Course(id=1, title="Test")
        progress = DownloadProgress(total_vids=1)

        mock_stat = MagicMock()
        mock_stat.st_size = 50000

        with patch.object(Path, "mkdir"), patch.object(
            Path, "exists", return_value=True
        ), patch.object(Path, "stat", return_value=mock_stat), patch.object(state, "save_state"):
            pipeline._download_lecture(lecture, course, progress, 1, 1, set())

        dl.download_file.assert_not_called()
        assert progress.done_vids == 1
        assert any("CACHE" in log for log in rep.logs)

    def test_article_body_saved_to_disk(self):
        pipeline, api, dl, state, rep = _make_pipeline()
        state.current_course_state = MagicMock()
        dl.download_subtitles.return_value = []
        dl.download_materials.return_value = []

        from udemy_dl.models import Lecture

        lecture = Lecture(
            id=70,
            title="Welcome Note",
            url="",
            file_path=Path("/tmp/note.html"),
            asset_type="Article",
            body="<p>Hello students</p>",
        )
        course = Course(id=1, title="Test")
        progress = DownloadProgress(total_vids=1)

        with patch.object(Path, "mkdir"), patch.object(
            Path, "write_text"
        ) as mock_write, patch.object(state, "save_state"):
            pipeline._download_lecture(lecture, course, progress, 1, 1, set())

        mock_write.assert_called_once_with("<p>Hello students</p>", encoding="utf-8")
        assert progress.done_vids == 1
        assert any("Saved article" in log for log in rep.logs)

    def test_builds_file_type_lecture_with_correct_extension(self):
        pipeline, api, dl, state, rep = _make_pipeline()
        api.get_course_curriculum.return_value = [
            {"_class": "chapter", "title": "Chapter 1"},
            {
                "_class": "lecture",
                "title": "Course Notes",
                "id": 201,
                "asset": {
                    "asset_type": "File",
                    "filename": "notes.pdf",
                    "download_urls": {"File": [{"file": "http://x/notes.pdf"}]},
                },
            },
        ]
        dl.get_asset_download_url.return_value = "http://x/notes.pdf"

        progress = DownloadProgress()
        course = Course(id=1, title="Test")
        state.current_course_state = MagicMock()
        state.current_course_state.total_lectures = 0

        queue = pipeline._build_download_queue(course, progress)
        assert len(queue) == 1
        assert queue[0].asset_type == "File"
        assert queue[0].file_path.suffix == ".pdf"
        assert queue[0].url == "http://x/notes.pdf"

    def test_article_lecture_has_no_url_and_html_extension(self):
        pipeline, api, dl, state, rep = _make_pipeline()
        api.get_course_curriculum.return_value = [
            {
                "_class": "lecture",
                "title": "Welcome",
                "id": 301,
                "asset": {"asset_type": "Article", "body": "<p>Hello</p>"},
            },
        ]

        progress = DownloadProgress()
        course = Course(id=1, title="Test")
        state.current_course_state = MagicMock()
        state.current_course_state.total_lectures = 0

        queue = pipeline._build_download_queue(course, progress)
        assert queue[0].asset_type == "Article"
        assert queue[0].url == ""
        assert queue[0].file_path.suffix == ".html"
        assert queue[0].body == "<p>Hello</p>"
