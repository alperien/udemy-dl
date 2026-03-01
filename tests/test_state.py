"""Tests for udemy_dl.state module."""

from unittest.mock import patch

from udemy_dl.state import AppState, DownloadState


class TestDownloadState:
    def test_to_dict_roundtrip(self):
        state = DownloadState(
            course_id=12345,
            course_title="Python Bootcamp",
            completed_lectures=[1, 2, 3],
            total_lectures=10,
            last_updated="2026-01-01T00:00:00",
        )
        d = state.to_dict()
        restored = DownloadState.from_dict(d)
        assert restored.course_id == 12345
        assert restored.course_title == "Python Bootcamp"
        assert restored.completed_lectures == [1, 2, 3]
        assert restored.total_lectures == 10

    def test_from_dict_ignores_unknown_keys(self):
        data = {
            "course_id": 99,
            "course_title": "Test",
            "completed_lectures": [],
            "total_lectures": 5,
            "last_updated": "",
            "unknown_field": "should be ignored",
        }
        state = DownloadState.from_dict(data)
        assert state.course_id == 99
        assert not hasattr(state, "unknown_field")

    def test_default_values(self):
        state = DownloadState()
        assert state.course_id is None
        assert state.course_title == ""
        assert state.completed_lectures == []
        assert state.total_lectures == 0


class TestAppState:
    def test_save_and_load_state(self, tmp_path):
        state_file = tmp_path / "download_state.json"
        app_state = AppState()
        app_state.current_course_state = DownloadState(
            course_id=42,
            course_title="Test Course",
            completed_lectures=[10, 20],
            total_lectures=5,
        )

        with patch("udemy_dl.state.STATE_FILE", str(state_file)):
            app_state.save_state()
            assert state_file.exists()

            loaded = app_state.load_state()
            assert loaded is not None
            assert loaded.course_id == 42
            assert loaded.course_title == "Test Course"
            assert loaded.completed_lectures == [10, 20]

    def test_load_state_returns_none_when_no_file(self, tmp_path):
        app_state = AppState()
        with patch("udemy_dl.state.STATE_FILE", str(tmp_path / "nonexistent.json")):
            result = app_state.load_state()
        assert result is None

    def test_load_state_handles_corrupt_json(self, tmp_path):
        state_file = tmp_path / "download_state.json"
        state_file.write_text("not valid json", encoding="utf-8")
        app_state = AppState()
        with patch("udemy_dl.state.STATE_FILE", str(state_file)):
            result = app_state.load_state()
        assert result is None

    def test_save_state_does_nothing_when_no_current_state(self, tmp_path):
        state_file = tmp_path / "download_state.json"
        app_state = AppState()
        with patch("udemy_dl.state.STATE_FILE", str(state_file)):
            app_state.save_state()  # should not raise
        assert not state_file.exists()

    def test_clear_state_removes_file(self, tmp_path):
        state_file = tmp_path / "download_state.json"
        state_file.write_text("{}", encoding="utf-8")
        app_state = AppState()
        app_state.current_course_state = DownloadState()
        with patch("udemy_dl.state.STATE_FILE", str(state_file)):
            app_state.clear_state()
        assert not state_file.exists()
        assert app_state.current_course_state is None

    def test_clear_state_no_error_when_no_file(self, tmp_path):
        app_state = AppState()
        with patch("udemy_dl.state.STATE_FILE", str(tmp_path / "nonexistent.json")):
            app_state.clear_state()  # should not raise
