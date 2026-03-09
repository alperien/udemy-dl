import sys
from unittest.mock import MagicMock, patch

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
        with (
            patch.object(sys, "argv", ["udemy-dl", "--headless"]),
            patch("udemy_dl.main._run_headless") as mock_headless,
        ):
            from udemy_dl.main import run

            run()
            mock_headless.assert_called_once()

    def test_course_id_implies_headless(self):
        with (
            patch.object(sys, "argv", ["udemy-dl", "--course-id", "123"]),
            patch("udemy_dl.main._run_headless") as mock_headless,
        ):
            from udemy_dl.main import run

            run()
            mock_headless.assert_called_once()

    def test_default_dispatches_to_curses(self):
        with patch.object(sys, "argv", ["udemy-dl"]), patch("udemy_dl.main.curses") as mock_curses:
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
            with patch("udemy_dl.main.setup_logging"), pytest.raises(SystemExit):
                from udemy_dl.main import _run_headless

                _run_headless(args)

    def test_exits_when_ffmpeg_missing(self):
        with patch.object(sys, "argv", ["udemy-dl", "--headless"]):
            from udemy_dl.main import _parse_args

            args = _parse_args()

        with (
            patch("udemy_dl.config.load_config") as mock_load,
            patch("udemy_dl.main.setup_logging"),
            patch("shutil.which", return_value=None),
            pytest.raises(SystemExit),
        ):
            mock_load.return_value = Config(token="t" * 20, client_id="c" * 10)
            from udemy_dl.main import _run_headless

            _run_headless(args)


class TestHeadlessReporter:
    def test_on_log_prints_message(self):
        from udemy_dl.main import _HeadlessReporter

        reporter = _HeadlessReporter()

        with patch("builtins.print") as mock_print:
            reporter.on_log("test message")
            mock_print.assert_called_once_with("  test message")

    def test_on_progress_does_nothing(self):
        from udemy_dl.main import _HeadlessReporter
        from udemy_dl.models import DownloadProgress

        reporter = _HeadlessReporter()
        progress = DownloadProgress(total_vids=10)

        reporter.on_progress(progress, 1, 3)

    def test_is_interrupted_defaults_false(self):
        from udemy_dl.main import _HeadlessReporter

        reporter = _HeadlessReporter()
        assert reporter.is_interrupted() is False

    def test_is_interrupted_returns_true_when_set(self):
        from udemy_dl.main import _HeadlessReporter

        reporter = _HeadlessReporter()
        reporter._interrupted = True
        assert reporter.is_interrupted() is True


class TestRunHeadless:
    def test_headless_fetches_courses(self):
        args = MagicMock()
        args.headless = True
        args.course_id = None
        args.quality = None
        args.no_subtitles = False
        args.no_materials = False

        mock_config = MagicMock()
        mock_config.validate.return_value = (True, None)

        mock_api = MagicMock()
        mock_api.fetch_owned_courses.return_value = [MagicMock()]

        mock_downloader = MagicMock()

        with (
            patch("udemy_dl.config.load_config", return_value=mock_config),
            patch("udemy_dl.main.setup_logging"),
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("udemy_dl.api.UdemyAPI", return_value=mock_api),
            patch("udemy_dl.dl.VideoDownloader", return_value=mock_downloader),
            patch("udemy_dl.pipeline.DownloadPipeline"),
        ):
            from udemy_dl.main import _run_headless

            _run_headless(args)

        mock_api.fetch_owned_courses.assert_called_once()

    def test_headless_prints_course_count(self):
        args = MagicMock()
        args.headless = True
        args.course_id = None
        args.quality = None
        args.no_subtitles = False
        args.no_materials = False

        mock_config = MagicMock()
        mock_config.validate.return_value = (True, None)

        mock_api = MagicMock()
        mock_api.fetch_owned_courses.return_value = [MagicMock(), MagicMock()]

        mock_downloader = MagicMock()

        with (
            patch("udemy_dl.config.load_config", return_value=mock_config),
            patch("udemy_dl.main.setup_logging"),
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("udemy_dl.api.UdemyAPI", return_value=mock_api),
            patch("udemy_dl.dl.VideoDownloader", return_value=mock_downloader),
            patch("udemy_dl.pipeline.DownloadPipeline"),
            patch("builtins.print") as mock_print,
        ):
            from udemy_dl.main import _run_headless

            _run_headless(args)

        assert any("Found" in str(c) and "course" in str(c) for c in mock_print.call_args_list)

    def test_headless_exits_when_no_courses(self):
        args = MagicMock()
        args.headless = True
        args.course_id = None
        args.quality = None
        args.no_subtitles = False
        args.no_materials = False

        mock_config = MagicMock()
        mock_config.validate.return_value = (True, None)

        mock_api = MagicMock()
        mock_api.fetch_owned_courses.return_value = []

        mock_downloader = MagicMock()

        with (
            patch("udemy_dl.config.load_config", return_value=mock_config),
            patch("udemy_dl.main.setup_logging"),
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("udemy_dl.api.UdemyAPI", return_value=mock_api),
            patch("udemy_dl.dl.VideoDownloader", return_value=mock_downloader),
            patch("udemy_dl.pipeline.DownloadPipeline"),
            pytest.raises(SystemExit) as exc_info,
        ):
            from udemy_dl.main import _run_headless

            _run_headless(args)

        assert exc_info.value.code == 1

    def test_headless_uses_specific_course_id(self):
        args = MagicMock()
        args.headless = False
        args.course_id = 12345
        args.quality = None
        args.no_subtitles = False
        args.no_materials = False

        mock_config = MagicMock()
        mock_config.validate.return_value = (True, None)

        mock_api = MagicMock()
        mock_downloader = MagicMock()

        with (
            patch("udemy_dl.config.load_config", return_value=mock_config),
            patch("udemy_dl.main.setup_logging"),
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("udemy_dl.api.UdemyAPI", return_value=mock_api),
            patch("udemy_dl.dl.VideoDownloader", return_value=mock_downloader),
            patch("udemy_dl.pipeline.DownloadPipeline"),
            patch("builtins.print") as mock_print,
        ):
            from udemy_dl.main import _run_headless

            _run_headless(args)

        mock_api.fetch_owned_courses.assert_not_called()
        assert not any("Fetching" in str(c) for c in mock_print.call_args_list)

    def test_headless_keyboard_interrupt(self):
        args = MagicMock()
        args.headless = True
        args.course_id = None
        args.quality = None
        args.no_subtitles = False
        args.no_materials = False

        mock_config = MagicMock()
        mock_config.validate.return_value = (True, None)

        mock_api = MagicMock()
        mock_downloader = MagicMock()

        mock_pipeline = MagicMock()
        mock_pipeline.download_courses.side_effect = KeyboardInterrupt()

        with (
            patch("udemy_dl.config.load_config", return_value=mock_config),
            patch("udemy_dl.main.setup_logging"),
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("udemy_dl.api.UdemyAPI", return_value=mock_api),
            patch("udemy_dl.dl.VideoDownloader", return_value=mock_downloader),
            patch("udemy_dl.pipeline.DownloadPipeline", return_value=mock_pipeline),
            patch("udemy_dl.main.AppState"),
            patch("builtins.print") as mock_print,
            pytest.raises(SystemExit) as exc_info,
        ):
            from udemy_dl.main import _run_headless

            _run_headless(args)

        assert exc_info.value.code == 130
        assert any("Interrupted" in str(c) for c in mock_print.call_args_list)


class TestMainFunction:
    def test_main_handles_keyboard_interrupt(self):
        with patch("udemy_dl.main.setup_logging"), patch("udemy_dl.app.Application") as mock_app:
            mock_app.side_effect = KeyboardInterrupt()

            from udemy_dl.main import _main

            _main(MagicMock())

    def test_main_handles_exception(self):
        with patch("udemy_dl.main.setup_logging"), patch("udemy_dl.app.Application") as mock_app:
            mock_app.side_effect = ValueError("test error")

            with patch("sys.exit") as mock_exit:
                from udemy_dl.main import _main

                _main(MagicMock())

                mock_exit.assert_called_once_with(1)
