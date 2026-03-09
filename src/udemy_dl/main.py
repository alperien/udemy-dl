from __future__ import annotations

import argparse
import curses
import shutil
import sys

from .config import QUALITY_OPTIONS, load_config
from .models import Course, DownloadProgress
from .pipeline import DownloadPipeline
from .utils import LOG_FILE, get_logger, setup_logging

logger = get_logger(__name__)


class _HeadlessReporter:
    def __init__(self) -> None:
        self._interrupted = False

    def on_log(self, message: str) -> None:
        print(f"  {message}")

    def on_progress(
        self,
        progress: DownloadProgress,
        course_index: int,
        total_courses: int,
    ) -> None:
        pass

    def is_interrupted(self) -> bool:
        return self._interrupted


def _main(stdscr: curses.window) -> None:
    root_logger = setup_logging()
    try:
        from .app import Application

        app = Application(stdscr)
        app.run()
    except KeyboardInterrupt:
        root_logger.info("User pressed Ctrl+C, exiting cleanly")
    except Exception as e:
        root_logger.exception(f"Unhandled exception: {e}")
        print(f"\nFatal error: {e}")
        print(f"Check {LOG_FILE} for details")
        sys.exit(1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="udemy-dl",
        description="Lightweight CLI tool for locally backing up your owned Udemy courses.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_get_version()}",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help=(
            "Run without the interactive TUI. "
            "Requires UDEMY_TOKEN and UDEMY_CLIENT_ID to be set via environment variables. "
            "Downloads all owned courses to the configured download path."
        ),
    )
    parser.add_argument(
        "--course-id",
        type=int,
        metavar="ID",
        help="Download a specific course by its Udemy course ID (implies --headless).",
    )
    parser.add_argument(
        "--quality",
        choices=QUALITY_OPTIONS,
        help="Override the preferred video quality for this run.",
    )
    parser.add_argument(
        "--no-subtitles",
        action="store_true",
        help="Skip subtitle downloads for this run.",
    )
    parser.add_argument(
        "--no-materials",
        action="store_true",
        help="Skip supplementary material downloads for this run.",
    )
    return parser.parse_args()


def _get_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("udemy-dl")
    except (ImportError, PackageNotFoundError):
        try:
            from . import __version__

            return __version__
        except ImportError:
            return "unknown"


def _run_headless(args: argparse.Namespace) -> None:
    from .api import UdemyAPI
    from .dl import VideoDownloader
    from .state import AppState

    setup_logging()
    config = load_config()

    if args.quality:
        config.quality = args.quality
    if args.no_subtitles:
        config.download_subtitles = False
    if args.no_materials:
        config.download_materials = False

    valid, error_msg = config.validate()
    if not valid:
        print(f"Configuration error: {error_msg}", file=sys.stderr)
        print(
            "Set UDEMY_TOKEN and UDEMY_CLIENT_ID environment variables.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not shutil.which("ffmpeg"):
        print("Error: ffmpeg is not installed or not in PATH.", file=sys.stderr)
        sys.exit(1)

    api = UdemyAPI(config)
    downloader = VideoDownloader(config, api.session)
    app_state = AppState()
    reporter = _HeadlessReporter()

    if args.course_id:
        courses = [Course(id=args.course_id, title=f"Course {args.course_id}")]
    else:
        print("Fetching owned courses...")
        courses = api.fetch_owned_courses()
        if not courses:
            print("No courses found. Check your token.", file=sys.stderr)
            sys.exit(1)
        print(f"Found {len(courses)} course(s).")

    pipeline = DownloadPipeline(
        config=config,
        api=api,
        downloader=downloader,
        state=app_state,
        reporter=reporter,
    )

    try:
        pipeline.download_courses(courses)
        print("\n[DONE] All requested courses processed.")
    except KeyboardInterrupt:
        reporter._interrupted = True
        print("\nInterrupted — saving progress...")
        app_state.save_state()
        sys.exit(130)


def run() -> None:
    args = _parse_args()

    if args.headless or args.course_id:
        _run_headless(args)
    else:
        curses.wrapper(_main)


if __name__ == "__main__":
    run()
