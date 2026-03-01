#!/usr/bin/env python3
import argparse
import curses
import sys

from .app import Application
from .utils import setup_logging

logger = None


def _main(stdscr: "curses.window") -> None:
    global logger
    logger = setup_logging()
    try:
        app = Application(stdscr)
        app.run()
    except KeyboardInterrupt:
        if logger:
            logger.info("User pressed Ctrl+C, exiting cleanly")
    except Exception as e:
        if logger:
            logger.exception(f"Unhandled exception: {e}")
        print(f"\nFatal error: {e}")
        from .utils import LOG_FILE

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
        choices=["2160", "1440", "1080", "720", "480", "360"],
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
        from . import __version__

        return __version__
    except ImportError:
        return "unknown"


def _run_headless(args: argparse.Namespace) -> None:
    """Non-interactive download mode — no curses required."""
    from pathlib import Path

    from .api import UdemyAPI
    from .config import load_config
    from .dl import VideoDownloader
    from .state import AppState, DownloadState
    from .utils import sanitize_filename, validate_video

    setup_logging()
    config = load_config()

    # Apply CLI overrides
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

    import shutil

    if not shutil.which("ffmpeg"):
        print("Error: ffmpeg is not installed or not in PATH.", file=sys.stderr)
        sys.exit(1)

    api = UdemyAPI(config)
    downloader = VideoDownloader(config, api.session)
    app_state = AppState()

    if args.course_id:
        courses = [{"id": args.course_id, "title": f"Course {args.course_id}"}]
        # Try to get the real title
        all_courses = api.fetch_owned_courses()
        for c in all_courses:
            if c["id"] == args.course_id:
                courses = [c]
                break
    else:
        print("Fetching owned courses...")
        courses = api.fetch_owned_courses()
        if not courses:
            print("No courses found. Check your token.", file=sys.stderr)
            sys.exit(1)
        print(f"Found {len(courses)} course(s).")

    try:
        for course in courses:
            print(f"\n[COURSE] {course['title']} (id={course['id']})")
            app_state.current_course_state = DownloadState(
                course_id=course["id"],
                course_title=course["title"],
                total_lectures=0,
            )

            try:
                curriculum = api.get_course_curriculum(course["id"])
            except RuntimeError as e:
                print(f"[ERROR] {e}", file=sys.stderr)
                continue

            base_dir = Path(config.dl_path) / sanitize_filename(course["title"])
            chapter_index = 0
            lecture_index = 0
            current_chapter_dir = None

            saved_state = app_state.load_state()
            completed_lectures: set = set()
            if saved_state and saved_state.course_id == course["id"]:
                completed_lectures = set(saved_state.completed_lectures)
                print(f"[RESUME] {len(completed_lectures)} previously completed lectures")

            for item in curriculum:
                item_type = item.get("_class")
                clean_title = sanitize_filename(str(item.get("title") or "Unknown"))

                if item_type == "chapter":
                    chapter_index += 1
                    lecture_index = 0
                    current_chapter_dir = base_dir / f"{chapter_index:02d} - {clean_title}"
                elif item_type == "lecture":
                    lecture_index += 1
                    lecture_id = item.get("id")
                    asset = item.get("asset")
                    url = downloader.get_quality_video_url(asset) if asset else ""

                    if not current_chapter_dir:
                        current_chapter_dir = base_dir / "00 - Uncategorized"

                    out_path = current_chapter_dir / f"{lecture_index:03d} - {clean_title}.mp4"
                    out_path.parent.mkdir(parents=True, exist_ok=True)

                    if lecture_id and lecture_id in completed_lectures:
                        print(f"  [CACHE] {clean_title[:50]}")
                        continue

                    if not url:
                        print(f"  [SKIP]  {clean_title[:50]} (no video)")
                        if lecture_id:
                            app_state.current_course_state.completed_lectures.append(lecture_id)
                            app_state.save_state()
                        continue

                    if (
                        out_path.exists()
                        and out_path.stat().st_size > 1024
                        and validate_video(out_path)
                    ):
                        print(f"  [CACHE] {clean_title[:50]} (file exists)")
                        if lecture_id:
                            app_state.current_course_state.completed_lectures.append(lecture_id)
                            app_state.save_state()
                        continue

                    print(f"  [DL]    {clean_title[:50]}")
                    proc = downloader.download_video(url, out_path)
                    proc.wait()

                    if proc.returncode == 0 and out_path.exists() and validate_video(out_path):
                        print(f"  [DONE]  {clean_title[:50]}")
                        if lecture_id:
                            app_state.current_course_state.completed_lectures.append(lecture_id)
                            app_state.save_state()
                    else:
                        print(f"  [FAIL]  {clean_title[:50]}", file=sys.stderr)
                        if out_path.exists():
                            out_path.unlink()

            app_state.clear_state()
            print(f"[DONE] Finished: {course['title']}")
    except KeyboardInterrupt:
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
