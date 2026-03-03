"""Interactive TUI application for downloading Udemy courses.

This module wires together the curses-based :class:`~udemy_dl.tui.TUI`
with the shared :class:`~udemy_dl.pipeline.DownloadPipeline`, acting as
a thin presentation-layer adapter.
"""

from __future__ import annotations

import curses
import shutil
import signal
from collections import deque
from datetime import datetime
from typing import List

from .api import UdemyAPI
from .config import load_config
from .dl import VideoDownloader
from .models import Course, DownloadProgress
from .pipeline import DownloadPipeline
from .state import AppState
from .tui import COLOR_DIM, COLOR_SUCCESS, TUI
from .utils import get_logger

logger = get_logger(__name__)


class _TUIReporter:
    """Adapts the TUI to the :class:`~udemy_dl.pipeline.ProgressReporter` protocol."""

    def __init__(self, tui: TUI, log_buffer: deque) -> None:  # type: ignore[type-arg]
        self.tui = tui
        self.log_buffer = log_buffer
        self.interrupted = False

    def on_log(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {message}"
        self.log_buffer.append(entry)
        logger.info(message)

    def on_progress(
        self,
        progress: DownloadProgress,
        course_index: int,
        total_courses: int,
    ) -> None:
        self.tui.render_dashboard(
            progress, course_index, total_courses, list(self.log_buffer)
        )

    def is_interrupted(self) -> bool:
        return self.interrupted


class Application:
    """Top-level interactive application.

    Presents the main menu, legal disclaimer, course picker, and then
    delegates all download work to :class:`DownloadPipeline`.

    Args:
        stdscr: The root curses window provided by :func:`curses.wrapper`.
    """

    def __init__(self, stdscr: "curses.window") -> None:
        self.stdscr = stdscr
        self.tui = TUI(stdscr)
        self.config = load_config()
        self.state = AppState()
        self.log_buffer: deque = deque(maxlen=100)  # type: ignore[type-arg]
        self.reporter = _TUIReporter(self.tui, self.log_buffer)

    def _setup_signal_handlers(self) -> None:
        """Install SIGINT / SIGTERM handlers that set the interrupt flag."""

        def handler(sig: int, frame: object) -> None:
            self.reporter.interrupted = True
            self.state.interrupted = True

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def run(self) -> None:
        """Main entry point: show legal screen, menu loop, download loop."""
        curses.curs_set(0)

        if not shutil.which("ffmpeg"):
            self.tui.show_error("ffmpeg is not installed or not in PATH.")
            return
        if not shutil.which("ffprobe"):
            logger.warning("ffprobe not found. Video validation will be skipped.")

        if not self.tui.show_legal_warning():
            logger.info("User declined legal terms. Exiting.")
            return

        valid, error_msg = self.config.validate()
        if not valid:
            self.tui.show_error(f"Configuration invalid: {error_msg}")
            self.tui.edit_settings(self.config)
            valid, error_msg = self.config.validate()
            if not valid:
                self.tui.show_error(f"Configuration still invalid: {error_msg}")
                return

        self._setup_signal_handlers()

        while True:
            if self.reporter.interrupted:
                self.reporter.on_log("Download interrupted. Returning to menu.")
                self.reporter.interrupted = False
                self.state.save_state()

            if not self.tui.main_menu(self.config):
                break

            self._run_download_session()

        self.state.clear_state()

    def _run_download_session(self) -> None:
        """Create API+downloader, pick courses, run the pipeline."""
        try:
            api = UdemyAPI(self.config)
            downloader = VideoDownloader(self.config, api.session)
        except (OSError, ValueError) as e:
            self.tui.show_error(f"Failed to initialize session: {e}")
            return

        courses: List[Course] = api.fetch_owned_courses()
        if not courses:
            self.tui.show_error("Could not fetch courses. Check your token.")
            return

        chosen_courses = self.tui.select_courses(courses)
        if not chosen_courses:
            return

        pipeline = DownloadPipeline(
            config=self.config,
            api=api,
            downloader=downloader,
            state=self.state,
            reporter=self.reporter,
        )

        completed = pipeline.download_courses(chosen_courses)

        if completed:
            self.stdscr.clear()
            height, width = self.stdscr.getmaxyx()
            self.tui.safe_addstr(
                height // 2,
                max(0, (width - 40) // 2),
                "All downloads completed successfully!",
                COLOR_SUCCESS,
                curses.A_BOLD,
            )
            self.tui.safe_addstr(
                height // 2 + 1,
                max(0, (width - 40) // 2),
                "[ Press any key to return to menu ]",
                COLOR_DIM,
            )
            self.stdscr.refresh()
            self.stdscr.getch()
