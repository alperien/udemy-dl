from collections import deque
from unittest.mock import MagicMock, patch

from udemy_dl.app import Application, _TUIReporter
from udemy_dl.models import Course, DownloadProgress


class TestTUIReporter:
    def test_on_log_appends_to_buffer(self):
        mock_tui = MagicMock()
        log_buffer = deque(maxlen=100)

        reporter = _TUIReporter(mock_tui, log_buffer)
        reporter.on_log("Test message")

        assert len(log_buffer) == 1
        assert "Test message" in log_buffer[0]

    def test_on_log_includes_timestamp(self):
        mock_tui = MagicMock()
        log_buffer = deque(maxlen=100)

        reporter = _TUIReporter(mock_tui, log_buffer)
        reporter.on_log("Test")

        entry = log_buffer[0]
        assert entry.startswith("[") and "]" in entry

    def test_on_progress_calls_tui_render(self):
        mock_tui = MagicMock()
        log_buffer = deque(maxlen=100)

        reporter = _TUIReporter(mock_tui, log_buffer)
        progress = DownloadProgress(total_vids=10)
        progress.done_vids = 5

        reporter.on_progress(progress, 1, 3)

        mock_tui.render_dashboard.assert_called_once()

    def test_is_interrupted_defaults_false(self):
        mock_tui = MagicMock()
        log_buffer = deque(maxlen=100)

        reporter = _TUIReporter(mock_tui, log_buffer)

        assert reporter.is_interrupted() is False

    def test_is_interrupted_returns_true_when_set(self):
        mock_tui = MagicMock()
        log_buffer = deque(maxlen=100)

        reporter = _TUIReporter(mock_tui, log_buffer)
        reporter.interrupted = True

        assert reporter.is_interrupted() is True


class TestApplication:
    def test_application_initializes_components(self):
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()

        with (
            patch("udemy_dl.app.TUI", return_value=mock_tui),
            patch("udemy_dl.app.load_config") as mock_config,
            patch("udemy_dl.app.AppState") as mock_state,
        ):
            mock_config.return_value = MagicMock()
            app = Application(mock_stdscr)

            assert app.stdscr == mock_stdscr
            assert app.tui == mock_tui
            assert app.config == mock_config.return_value
            assert app.state == mock_state.return_value

    def test_setup_signal_handlers(self):
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()

        with (
            patch("udemy_dl.app.TUI", return_value=mock_tui),
            patch("udemy_dl.app.load_config") as mock_config,
            patch("udemy_dl.app.AppState"),
            patch("signal.signal") as mock_signal,
        ):
            mock_config.return_value = MagicMock()
            app = Application(mock_stdscr)
            app._setup_signal_handlers()

            assert mock_signal.call_count == 2
            calls = mock_signal.call_args_list
            assert calls[0][0][0] == 2
            assert calls[1][0][0] == 15

    def test_run_exits_when_ffmpeg_missing(self):
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()

        with (
            patch("udemy_dl.app.curses.curs_set"),
            patch("udemy_dl.app.TUI", return_value=mock_tui),
            patch("udemy_dl.app.load_config") as mock_config,
            patch("udemy_dl.app.AppState"),
            patch("shutil.which", return_value=None),
        ):
            mock_config.return_value = MagicMock()
            app = Application(mock_stdscr)
            app.run()

            mock_tui.show_error.assert_called_once()

    def test_run_exits_when_legal_declined(self):
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()
        mock_tui.show_legal_warning.return_value = False

        with (
            patch("udemy_dl.app.curses.curs_set"),
            patch("udemy_dl.app.TUI", return_value=mock_tui),
            patch("udemy_dl.app.load_config") as mock_config,
            patch("udemy_dl.app.AppState"),
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        ):
            mock_config.return_value = MagicMock()
            mock_config.return_value.validate.return_value = (True, None)
            app = Application(mock_stdscr)
            app.run()

            mock_tui.main_menu.assert_not_called()

    def test_run_exits_on_invalid_config(self):
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()
        mock_tui.show_legal_warning.return_value = True

        with (
            patch("udemy_dl.app.curses.curs_set"),
            patch("udemy_dl.app.TUI", return_value=mock_tui),
            patch("udemy_dl.app.load_config") as mock_config,
            patch("udemy_dl.app.AppState"),
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        ):
            mock_cfg = MagicMock()
            mock_cfg.validate.side_effect = [(False, "error"), (False, "error")]
            mock_config.return_value = mock_cfg

            app = Application(mock_stdscr)
            app.run()

            assert mock_tui.show_error.call_count == 2

    def test_run_clears_state_on_exit(self):
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()
        mock_tui.show_legal_warning.return_value = True
        mock_tui.main_menu.return_value = False

        mock_state = MagicMock()

        with (
            patch("udemy_dl.app.curses.curs_set"),
            patch("udemy_dl.app.TUI", return_value=mock_tui),
            patch("udemy_dl.app.load_config") as mock_config,
            patch("udemy_dl.app.AppState", return_value=mock_state),
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
            patch.object(Application, "_run_download_session"),
        ):
            mock_cfg = MagicMock()
            mock_cfg.validate.return_value = (True, None)
            mock_config.return_value = mock_cfg

            app = Application(mock_stdscr)
            app.run()

            mock_state.clear_state.assert_called_once()


class TestApplicationDownloadSession:
    def test_session_fails_on_api_error(self):
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()
        mock_tui.show_legal_warning.return_value = True
        mock_tui.main_menu.return_value = True

        with (
            patch("udemy_dl.app.curses.curs_set"),
            patch("udemy_dl.app.TUI", return_value=mock_tui),
            patch("udemy_dl.app.load_config") as mock_config,
            patch("udemy_dl.app.AppState"),
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("udemy_dl.app.UdemyAPI", side_effect=OSError("Network error")),
        ):
            mock_cfg = MagicMock()
            mock_cfg.validate.return_value = (True, None)
            mock_config.return_value = mock_cfg

            app = Application(mock_stdscr)
            app.run()

            mock_tui.show_error.assert_called()

    def test_session_handles_no_courses(self):
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()
        mock_tui.show_legal_warning.return_value = True
        mock_tui.main_menu.return_value = True

        mock_state = MagicMock()

        with (
            patch("udemy_dl.app.curses.curs_set"),
            patch("udemy_dl.app.TUI", return_value=mock_tui),
            patch("udemy_dl.app.load_config") as mock_config,
            patch("udemy_dl.app.AppState", return_value=mock_state),
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("udemy_dl.app.UdemyAPI") as mock_api,
            patch.object(Application, "_run_download_session"),
        ):
            mock_cfg = MagicMock()
            mock_cfg.validate.return_value = (True, None)
            mock_config.return_value = mock_cfg

            mock_api_instance = MagicMock()
            mock_api_instance.fetch_owned_courses.return_value = []
            mock_api.return_value = mock_api_instance

            app = Application(mock_stdscr)
            app.run()

            mock_tui.show_error.assert_called()

    def test_session_handles_user_cancels_course_selection(self):
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()
        mock_tui.show_legal_warning.return_value = True
        mock_tui.main_menu.return_value = True

        mock_state = MagicMock()

        with (
            patch("udemy_dl.app.curses.curs_set"),
            patch("udemy_dl.app.TUI", return_value=mock_tui),
            patch("udemy_dl.app.load_config") as mock_config,
            patch("udemy_dl.app.AppState", return_value=mock_state),
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("udemy_dl.app.UdemyAPI") as mock_api,
            patch.object(Application, "_run_download_session"),
        ):
            mock_cfg = MagicMock()
            mock_cfg.validate.return_value = (True, None)
            mock_config.return_value = mock_cfg

            mock_api_instance = MagicMock()
            mock_api_instance.fetch_owned_courses.return_value = [Course(id=1, title="Test Course")]
            mock_api.return_value = mock_api_instance

            mock_tui.select_courses.return_value = []

            app = Application(mock_stdscr)
            app.run()
