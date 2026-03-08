from collections import deque
from unittest.mock import MagicMock, patch

from udemy_dl.app import Application, _TUIReporter
from udemy_dl.models import Course, DownloadProgress


class TestTUIReporter:
    """Tests for _TUIReporter class."""

    def test_on_log_appends_to_buffer(self):
        """Test that on_log adds message to log buffer."""
        mock_tui = MagicMock()
        log_buffer = deque(maxlen=100)

        reporter = _TUIReporter(mock_tui, log_buffer)
        reporter.on_log("Test message")

        assert len(log_buffer) == 1
        assert "Test message" in log_buffer[0]

    def test_on_log_includes_timestamp(self):
        """Test that on_log includes timestamp in format [HH:MM:SS]."""
        mock_tui = MagicMock()
        log_buffer = deque(maxlen=100)

        reporter = _TUIReporter(mock_tui, log_buffer)
        reporter.on_log("Test")

        entry = log_buffer[0]
        # Check format [HH:MM:SS] message
        assert entry.startswith("[") and "]" in entry

    def test_on_progress_calls_tui_render(self):
        """Test that on_progress renders dashboard."""
        mock_tui = MagicMock()
        log_buffer = deque(maxlen=100)

        reporter = _TUIReporter(mock_tui, log_buffer)
        progress = DownloadProgress(total_vids=10)
        progress.done_vids = 5

        reporter.on_progress(progress, 1, 3)

        mock_tui.render_dashboard.assert_called_once()

    def test_is_interrupted_defaults_false(self):
        """Test that is_interrupted defaults to False."""
        mock_tui = MagicMock()
        log_buffer = deque(maxlen=100)

        reporter = _TUIReporter(mock_tui, log_buffer)

        assert reporter.is_interrupted() is False

    def test_is_interrupted_returns_true_when_set(self):
        """Test that is_interrupted returns True when interrupted flag is set."""
        mock_tui = MagicMock()
        log_buffer = deque(maxlen=100)

        reporter = _TUIReporter(mock_tui, log_buffer)
        reporter.interrupted = True

        assert reporter.is_interrupted() is True


class TestApplication:
    """Tests for Application class."""

    def test_application_initializes_components(self):
        """Test that Application initializes all components."""
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()

        with patch("udemy_dl.app.TUI", return_value=mock_tui), patch(
            "udemy_dl.app.load_config"
        ) as mock_config, patch("udemy_dl.app.AppState") as mock_state:
            mock_config.return_value = MagicMock()
            app = Application(mock_stdscr)

            assert app.stdscr == mock_stdscr
            assert app.tui == mock_tui
            assert app.config == mock_config.return_value
            assert app.state == mock_state.return_value

    def test_setup_signal_handlers(self):
        """Test that signal handlers are set up."""
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()

        with patch("udemy_dl.app.TUI", return_value=mock_tui), patch(
            "udemy_dl.app.load_config"
        ) as mock_config, patch("udemy_dl.app.AppState"), patch("signal.signal") as mock_signal:
            mock_config.return_value = MagicMock()
            app = Application(mock_stdscr)
            app._setup_signal_handlers()

            # Should register SIGINT and SIGTERM handlers
            assert mock_signal.call_count == 2
            # Get all calls to signal.signal
            calls = mock_signal.call_args_list
            # First call should be SIGINT, second SIGTERM
            assert calls[0][0][0] == 2  # SIGINT
            assert calls[1][0][0] == 15  # SIGTERM

    def test_run_exits_when_ffmpeg_missing(self):
        """Test that run exits when ffmpeg is not installed."""
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()

        with patch("udemy_dl.app.TUI", return_value=mock_tui), patch(
            "udemy_dl.app.load_config"
        ) as mock_config, patch("udemy_dl.app.AppState"), patch("shutil.which", return_value=None):
            mock_config.return_value = MagicMock()
            app = Application(mock_stdscr)
            app.run()

            mock_tui.show_error.assert_called_once()

    def test_run_exits_when_legal_declined(self):
        """Test that run exits when user declines legal terms."""
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()
        mock_tui.show_legal_warning.return_value = False

        with patch("udemy_dl.app.TUI", return_value=mock_tui), patch(
            "udemy_dl.app.load_config"
        ) as mock_config, patch("udemy_dl.app.AppState"), patch(
            "shutil.which", return_value="/usr/bin/ffmpeg"
        ):
            mock_config.return_value = MagicMock()
            mock_config.return_value.validate.return_value = (True, None)
            app = Application(mock_stdscr)
            app.run()

            # Should not call main_menu since legal was declined
            mock_tui.main_menu.assert_not_called()

    def test_run_exits_on_invalid_config(self):
        """Test that run exits when config is invalid and can't be fixed."""
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()
        mock_tui.show_legal_warning.return_value = True

        with patch("udemy_dl.app.TUI", return_value=mock_tui), patch(
            "udemy_dl.app.load_config"
        ) as mock_config, patch("udemy_dl.app.AppState"), patch(
            "shutil.which", return_value="/usr/bin/ffmpeg"
        ):
            mock_cfg = MagicMock()
            # First validate fails, second also fails
            mock_cfg.validate.side_effect = [(False, "error"), (False, "error")]
            mock_config.return_value = mock_cfg

            app = Application(mock_stdscr)
            app.run()

            # Should show error about invalid config
            assert mock_tui.show_error.call_count == 2

    def test_run_clears_state_on_exit(self):
        """Test that state is cleared when exiting."""
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()
        mock_tui.show_legal_warning.return_value = True
        mock_tui.main_menu.return_value = False  # Exit immediately

        mock_state = MagicMock()

        with patch("udemy_dl.app.TUI", return_value=mock_tui), patch(
            "udemy_dl.app.load_config"
        ) as mock_config, patch("udemy_dl.app.AppState", return_value=mock_state), patch(
            "shutil.which", return_value="/usr/bin/ffmpeg"
        ), patch.object(
            Application, "_run_download_session"
        ):
            mock_cfg = MagicMock()
            mock_cfg.validate.return_value = (True, None)
            mock_config.return_value = mock_cfg

            app = Application(mock_stdscr)
            app.run()

            # Should clear state on exit
            mock_state.clear_state.assert_called_once()


class TestApplicationDownloadSession:
    """Tests for _run_download_session method."""

    def test_session_fails_on_api_error(self):
        """Test that session handles API initialization errors."""
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()

        with patch("udemy_dl.app.TUI", return_value=mock_tui), patch(
            "udemy_dl.app.load_config"
        ) as mock_config, patch("udemy_dl.app.AppState"), patch(
            "shutil.which", return_value="/usr/bin/ffmpeg"
        ), patch(
            "udemy_dl.app.UdemyAPI", side_effect=OSError("Network error")
        ):
            mock_cfg = MagicMock()
            mock_cfg.validate.return_value = (True, None)
            mock_config.return_value = mock_cfg

            app = Application(mock_stdscr)
            app.run()

            # Should show error about failed initialization
            mock_tui.show_error.assert_called()

    def test_session_handles_no_courses(self):
        """Test that session handles when no courses are found."""
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()
        mock_tui.show_legal_warning.return_value = True
        mock_tui.main_menu.return_value = True  # Continue to download

        mock_state = MagicMock()

        with patch("udemy_dl.app.TUI", return_value=mock_tui), patch(
            "udemy_dl.app.load_config"
        ) as mock_config, patch("udemy_dl.app.AppState", return_value=mock_state), patch(
            "shutil.which", return_value="/usr/bin/ffmpeg"
        ), patch(
            "udemy_dl.app.UdemyAPI"
        ) as mock_api, patch.object(
            Application, "_run_download_session"
        ):
            mock_cfg = MagicMock()
            mock_cfg.validate.return_value = (True, None)
            mock_config.return_value = mock_cfg

            # API returns empty list
            mock_api_instance = MagicMock()
            mock_api_instance.fetch_owned_courses.return_value = []
            mock_api.return_value = mock_api_instance

            app = Application(mock_stdscr)
            app.run()

            # Should show error about no courses
            mock_tui.show_error.assert_called()

    def test_session_handles_user_cancels_course_selection(self):
        """Test that session handles when user cancels course selection."""
        mock_stdscr = MagicMock()
        mock_tui = MagicMock()
        mock_tui.show_legal_warning.return_value = True
        mock_tui.main_menu.return_value = True  # Continue to download

        mock_state = MagicMock()

        with patch("udemy_dl.app.TUI", return_value=mock_tui), patch(
            "udemy_dl.app.load_config"
        ) as mock_config, patch("udemy_dl.app.AppState", return_value=mock_state), patch(
            "shutil.which", return_value="/usr/bin/ffmpeg"
        ), patch(
            "udemy_dl.app.UdemyAPI"
        ) as mock_api, patch.object(
            Application, "_run_download_session"
        ):
            mock_cfg = MagicMock()
            mock_cfg.validate.return_value = (True, None)
            mock_config.return_value = mock_cfg

            # API returns courses but user cancels selection
            mock_api_instance = MagicMock()
            mock_api_instance.fetch_owned_courses.return_value = [Course(id=1, title="Test Course")]
            mock_api.return_value = mock_api_instance

            # User cancels selection
            mock_tui.select_courses.return_value = []

            app = Application(mock_stdscr)
            app.run()

            # _run_download_session should not be called
            # (skipped because no courses selected)
