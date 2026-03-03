"""Tests for the TUI using a mock curses window."""

from unittest.mock import MagicMock, patch

from udemy_dl.models import DownloadProgress
from udemy_dl.tui import COLOR_DEFAULT, COLOR_ERROR, TUI


class MockCursesWindow:
    """Minimal mock of curses.window for testing."""

    def __init__(self, height=24, width=80):
        self.height = height
        self.width = width
        self.written = []

    def getmaxyx(self):
        return (self.height, self.width)

    def addstr(self, y, x, text, attr=0):
        self.written.append((y, x, text, attr))

    def erase(self):
        self.written.clear()

    def clear(self):
        self.written.clear()

    def refresh(self):
        pass

    def getch(self):
        return ord("q")

    def timeout(self, ms):
        pass


class TestSafeAddstr:
    def test_truncates_long_text(self):
        win = MockCursesWindow()
        with patch("udemy_dl.tui.curses") as mock_curses:
            mock_curses.color_pair.return_value = 0
            mock_curses.A_REVERSE = 0
            mock_curses.A_BOLD = 0
            mock_curses.COLOR_GREEN = 2
            mock_curses.COLOR_CYAN = 6
            mock_curses.COLOR_YELLOW = 3
            mock_curses.COLOR_RED = 1
            mock_curses.COLOR_BLUE = 4
            mock_curses.error = Exception
            tui = TUI.__new__(TUI)
            tui.stdscr = win
            tui.safe_addstr(0, 0, "Hello World", COLOR_DEFAULT, 0, 5)
            assert len(win.written) == 1
            text = win.written[0][2]
            assert len(text) <= 5

    def test_handles_zero_width(self):
        win = MockCursesWindow()
        with patch("udemy_dl.tui.curses") as mock_curses:
            mock_curses.error = Exception
            tui = TUI.__new__(TUI)
            tui.stdscr = win
            tui.safe_addstr(0, 0, "Hello", COLOR_DEFAULT, 0, 0)
            assert len(win.written) == 0


class TestRenderDashboard:
    def test_renders_without_error(self):
        win = MockCursesWindow(height=20, width=80)
        with patch("udemy_dl.tui.curses") as mock_curses:
            mock_curses.color_pair.return_value = 0
            mock_curses.A_REVERSE = 0
            mock_curses.A_BOLD = 0
            mock_curses.error = Exception
            tui = TUI.__new__(TUI)
            tui.stdscr = win

            state = DownloadProgress(
                course_title="Test Course",
                total_vids=10,
                done_vids=5,
                current_file="lecture.mp4",
                vid_duration_secs=100,
                vid_current_secs=50,
            )
            tui.render_dashboard(state, 1, 1, ["[12:00:00] Test log"])
            assert len(win.written) > 0

    def test_handles_small_terminal(self):
        win = MockCursesWindow(height=5, width=20)
        with patch("udemy_dl.tui.curses") as mock_curses:
            mock_curses.color_pair.return_value = 0
            mock_curses.A_REVERSE = 0
            mock_curses.A_BOLD = 0
            mock_curses.error = Exception
            tui = TUI.__new__(TUI)
            tui.stdscr = win

            state = DownloadProgress()
            tui.render_dashboard(state, 1, 1, [])
            texts = [w[2] for w in win.written]
            assert any("too small" in t for t in texts)
