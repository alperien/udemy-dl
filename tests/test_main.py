"""Tests for udemy_dl.main module (headless mode and CLI parsing)."""

import sys
from unittest.mock import patch

import pytest
from udemy_dl.config import Config


class TestParseArgs:
    def test_default_args(self):
        with patch.object(sys, "argv", ["udemy-dl"]):
            from udemy_dl.main import _parse_args

            args = _parse_args()
        assert args.headless is False
        assert args.course_id is None
        assert args.quality is None
        assert args.no_subtitles is False
        assert args.no_materials is False

    def test_headless_flag(self):
        with patch.object(sys, "argv", ["udemy-dl", "--headless"]):
            from udemy_dl.main import _parse_args

            args = _parse_args()
        assert args.headless is True

    def test_course_id(self):
        with patch.object(sys, "argv", ["udemy-dl", "--course-id", "12345"]):
            from udemy_dl.main import _parse_args

            args = _parse_args()
        assert args.course_id == 12345

    def test_quality_override(self):
        with patch.object(sys, "argv", ["udemy-dl", "--headless", "--quality", "720"]):
            from udemy_dl.main import _parse_args

            args = _parse_args()
        assert args.quality == "720"

    def test_no_subtitles_flag(self):
        with patch.object(sys, "argv", ["udemy-dl", "--headless", "--no-subtitles"]):
            from udemy_dl.main import _parse_args

            args = _parse_args()
        assert args.no_subtitles is True

    def test_no_materials_flag(self):
        with patch.object(sys, "argv", ["udemy-dl", "--headless", "--no-materials"]):
            from udemy_dl.main import _parse_args

            args = _parse_args()
        assert args.no_materials is True

    def test_invalid_quality_rejected(self):
        with patch.object(sys, "argv", ["udemy-dl", "--quality", "999"]):
            from udemy_dl.main import _parse_args

            with pytest.raises(SystemExit):
                _parse_args()


class TestGetVersion:
    def test_returns_version_string(self):
        from udemy_dl.main import _get_version

        version = _get_version()
        assert version != "unknown"
        assert "." in version


class TestRunDispatch:
    def test_headless_dispatches_to_run_headless(self):
        with patch.object(sys, "argv", ["udemy-dl", "--headless"]):
            with patch("udemy_dl.main._run_headless") as mock_headless:
                from udemy_dl.main import run

                run()
                mock_headless.assert_called_once()

    def test_course_id_implies_headless(self):
        with patch.object(sys, "argv", ["udemy-dl", "--course-id", "123"]):
            with patch("udemy_dl.main._run_headless") as mock_headless:
                from udemy_dl.main import run

                run()
                mock_headless.assert_called_once()

    def test_default_dispatches_to_curses(self):
        with patch.object(sys, "argv", ["udemy-dl"]):
            with patch("udemy_dl.main.curses") as mock_curses:
                from udemy_dl.main import run

                run()
                mock_curses.wrapper.assert_called_once()


class TestHeadlessValidation:
    def test_exits_on_invalid_config(self):
        with patch.object(sys, "argv", ["udemy-dl", "--headless"]):
            from udemy_dl.main import _parse_args

            args = _parse_args()

        with patch("udemy_dl.config.load_config") as mock_load:
            mock_load.return_value = Config(token="", client_id="")
            with patch("udemy_dl.main.setup_logging"):
                with pytest.raises(SystemExit):
                    from udemy_dl.main import _run_headless

                    _run_headless(args)

    def test_exits_when_ffmpeg_missing(self):
        with patch.object(sys, "argv", ["udemy-dl", "--headless"]):
            from udemy_dl.main import _parse_args

            args = _parse_args()

        with patch("udemy_dl.config.load_config") as mock_load:
            mock_load.return_value = Config(token="t" * 20, client_id="c" * 10)
            with patch("udemy_dl.main.setup_logging"):
                with patch("shutil.which", return_value=None):
                    with pytest.raises(SystemExit):
                        from udemy_dl.main import _run_headless

                        _run_headless(args)
