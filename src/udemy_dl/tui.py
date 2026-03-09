from __future__ import annotations

import curses
import textwrap

from .config import Config, save_config
from .models import Course, DownloadProgress
from .utils import get_logger

logger = get_logger(__name__)


COLOR_DEFAULT = 1
COLOR_ACCENT = 2
COLOR_SUCCESS = 3
COLOR_WARN = 4
COLOR_ERROR = 5
COLOR_DIM = 6


class TUI:
    def __init__(self, stdscr: curses.window) -> None:
        self.stdscr = stdscr
        self._init_colors()
        curses.curs_set(0)

    def _init_colors(self) -> None:
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(COLOR_DEFAULT, -1, -1)
        curses.init_pair(COLOR_ACCENT, curses.COLOR_GREEN, -1)
        curses.init_pair(COLOR_SUCCESS, curses.COLOR_CYAN, -1)
        curses.init_pair(COLOR_WARN, curses.COLOR_YELLOW, -1)
        curses.init_pair(COLOR_ERROR, curses.COLOR_RED, -1)
        curses.init_pair(COLOR_DIM, curses.COLOR_BLUE, -1)

    def safe_addstr(
        self,
        y: int,
        x: int,
        text: str,
        color: int = COLOR_DEFAULT,
        attr: int = 0,
        max_width: int | None = None,
    ) -> None:
        try:
            if max_width is not None:
                if max_width <= 0:
                    return
                if len(text) > max_width:
                    text = text[: max_width - 1] + "~"
                else:
                    text = text.ljust(max_width)
            self.stdscr.addstr(y, x, text, curses.color_pair(color) | attr)
        except curses.error:
            pass

    def draw_header(self, title: str) -> None:
        _, width = self.stdscr.getmaxyx()
        self.safe_addstr(0, 0, f" {title } ".ljust(width), COLOR_DEFAULT, curses.A_REVERSE, width)

    def draw_footer(self, text: str) -> None:
        height, width = self.stdscr.getmaxyx()
        self.safe_addstr(
            height - 1,
            0,
            f" {text } ".ljust(width - 1),
            COLOR_DEFAULT,
            curses.A_REVERSE,
            width - 1,
        )

    def draw_progress_bar(
        self,
        y: int,
        x: int,
        width: int,
        percent: float,
        prefix: str = "",
        suffix: str = "",
        color: int = COLOR_ACCENT,
    ) -> None:
        bar_width = width - len(prefix) - len(suffix) - 4
        if bar_width < 5:
            return
        clamped = max(0.0, min(percent, 100.0))
        filled = int((clamped / 100) * bar_width)
        bar = "#" * filled + "-" * (bar_width - filled)

        self.safe_addstr(y, x, prefix, COLOR_DEFAULT, curses.A_BOLD)
        self.safe_addstr(y, x + len(prefix) + 1, f"[{bar }]", color)
        self.safe_addstr(y, x + len(prefix) + bar_width + 3, f" {suffix }", COLOR_DEFAULT)

    def render_dashboard(
        self,
        state: DownloadProgress,
        course_index: int,
        total_courses: int,
        log: list[str],
    ) -> None:
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()
        if height < 10 or width < 40:
            self.safe_addstr(0, 0, "Terminal too small!", COLOR_ERROR)
            self.stdscr.refresh()
            return

        self.draw_header(f"DOWNLOADING COURSE [{course_index}/{total_courses}]")

        self.safe_addstr(
            2,
            2,
            f"Course : {state.course_title}",
            COLOR_DEFAULT,
            curses.A_BOLD,
            width - 4,
        )

        overall_pct = state.overall_percent
        self.draw_progress_bar(
            3,
            2,
            width - 4,
            overall_pct,
            "Total  :",
            f"{overall_pct :3.0f}% [{state.done_vids :03d}/{state.total_vids :03d}]",
            COLOR_SUCCESS,
        )

        self.safe_addstr(
            5,
            2,
            f"File   : {state .current_file }",
            COLOR_DEFAULT,
            curses.A_BOLD,
            width - 4,
        )

        vid_pct = state.video_percent
        self.draw_progress_bar(
            6, 2, width - 4, vid_pct, "Video  :", f"{vid_pct :3.0f}%", COLOR_WARN
        )

        self.safe_addstr(8, 0, "-" * width, COLOR_DEFAULT)

        log_start_y = 9
        visible_logs = height - log_start_y - 1
        for idx, line in enumerate(log[-visible_logs:]):
            color = (
                COLOR_ERROR
                if "error" in line.lower()
                else (COLOR_SUCCESS if "done" in line.lower() else COLOR_DEFAULT)
            )
            self.safe_addstr(log_start_y + idx, 2, line, color, 0, width - 4)

        self.draw_footer("Downloading... Press Ctrl+C to abort")
        self.stdscr.refresh()

    def show_error(self, message: str) -> None:
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()

        self.draw_header("ERROR")

        wrapped = textwrap.wrap(message, max(1, width - 4))
        for i, line in enumerate(wrapped):
            if i + 2 < height - 1:
                self.safe_addstr(i + 2, 2, line, COLOR_ERROR, curses.A_BOLD)

        self.draw_footer("Press any key to continue")
        self.stdscr.refresh()
        self.stdscr.timeout(-1)
        self.stdscr.getch()

    def show_legal_warning(self) -> bool:
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()

        self.draw_header("LEGAL DISCLAIMER")

        lines = [
            "This tool is for PERSONAL BACKUP ONLY.",
            "Downloading courses may violate Udemy's Terms of Service.",
            "",
            "By using this tool, you acknowledge that:",
            "  * You own the courses you download",
            "  * You will NOT distribute downloaded content",
            "  * You are responsible for compliance with applicable laws",
        ]

        for i, line in enumerate(lines):
            if i + 2 < height - 1:
                self.safe_addstr(i + 2, 2, line, COLOR_WARN if i < 2 else COLOR_DEFAULT)

        self.draw_footer("[y] Yes, I agree  [n] No, exit")
        self.stdscr.refresh()

        self.stdscr.timeout(-1)
        while True:
            ch = self.stdscr.getch()
            if ch in (ord("y"), ord("Y")):
                return True
            if ch in (ord("n"), ord("N"), 27, ord("q"), ord("Q")):
                return False

    def edit_settings(self, config: Config) -> None:
        keys = list(config.to_dict().keys())
        selected_idx = 0
        scroll_offset = 0
        self.stdscr.timeout(-1)

        while True:
            self.stdscr.erase()
            height, width = self.stdscr.getmaxyx()

            self.draw_header("SETTINGS")

            visible_items = height - 3
            for i in range(visible_items):
                list_idx = scroll_offset + i
                if list_idx >= len(keys):
                    break

                key = keys[list_idx]
                val = str(getattr(config, key))
                if key == "token" and val:
                    val = "*" * min(len(val), 20) + ("..." if len(val) > 20 else "")

                text = f"{key :<20} : {val }"

                if list_idx == selected_idx:
                    self.safe_addstr(
                        i + 2, 2, f"> {text }", COLOR_DEFAULT, curses.A_REVERSE, width - 4
                    )
                else:
                    self.safe_addstr(i + 2, 2, f"  {text }", COLOR_DEFAULT, 0, width - 4)

            self.draw_footer("[j/k] Navigate  [enter] Edit  [q] Back")
            self.stdscr.refresh()

            ch = self.stdscr.getch()
            if ch in (curses.KEY_UP, ord("k")) and selected_idx > 0:
                selected_idx -= 1
                if selected_idx < scroll_offset:
                    scroll_offset -= 1
            elif ch in (curses.KEY_DOWN, ord("j")) and selected_idx < len(keys) - 1:
                selected_idx += 1
                if selected_idx >= scroll_offset + visible_items:
                    scroll_offset += 1
            elif ch in (ord("q"), ord("Q"), 27):
                break
            elif ch in (10, 13):
                self._edit_setting_field(config, keys[selected_idx], height, width)

    def _edit_setting_field(self, config: Config, key: str, height: int, width: int) -> None:
        prompt = f" New {key } (Blank=cancel, 'CLEAR'=empty): "

        self.safe_addstr(height - 1, 0, " " * width, COLOR_DEFAULT, curses.A_REVERSE)
        self.safe_addstr(height - 1, 0, prompt, COLOR_DEFAULT, curses.A_REVERSE)
        self.stdscr.refresh()

        curses.echo()
        curses.curs_set(1)
        max_input_width = width - len(prompt) - 1
        max_input_width = max(1, max_input_width)  # Ensure positive width
        try:
            new_val: object = (
                self.stdscr.getstr(height - 1, len(prompt), max_input_width).decode().strip()
            )
        except (curses.error, UnicodeDecodeError):
            new_val = ""
        finally:
            curses.noecho()
            curses.curs_set(0)

        if not new_val:
            return

        assert isinstance(new_val, str)
        if new_val.upper() == "CLEAR":
            new_val = ""
        elif key in ("download_subtitles", "download_materials"):
            new_val = new_val.lower() in ("true", "1", "yes", "y")

        old_val = getattr(config, key)
        setattr(config, key, new_val)
        valid, err = config.validate()
        if not valid:
            setattr(config, key, old_val)
            logger.warning(f"Config validation failed for {key }: {err }")
        else:
            save_config(config)
            logger.info(f"Updated config: {key }")

    def select_courses(self, courses: list[Course]) -> list[Course]:
        selected: set[int] = set()
        selected_idx = 0
        scroll_offset = 0
        self.stdscr.timeout(-1)

        while True:
            self.stdscr.erase()
            height, width = self.stdscr.getmaxyx()

            self.draw_header("SELECT COURSES")

            visible_items = height - 3
            for i in range(visible_items):
                list_idx = scroll_offset + i
                if list_idx >= len(courses):
                    break

                course = courses[list_idx]
                box = "[x]" if list_idx in selected else "[ ]"
                text = f"{box } {course .id :<10} {course .title }"

                if list_idx == selected_idx:
                    self.safe_addstr(
                        i + 2, 2, f"> {text }", COLOR_DEFAULT, curses.A_REVERSE, width - 4
                    )
                else:
                    self.safe_addstr(i + 2, 2, f"  {text }", COLOR_DEFAULT, 0, width - 4)

            self.draw_footer("[j/k] Navigate  [space] Toggle  [enter] Confirm  [q] Cancel")
            self.stdscr.refresh()

            ch = self.stdscr.getch()
            if ch in (curses.KEY_UP, ord("k")) and selected_idx > 0:
                selected_idx -= 1
                if selected_idx < scroll_offset:
                    scroll_offset -= 1
            elif ch in (curses.KEY_DOWN, ord("j")) and selected_idx < len(courses) - 1:
                selected_idx += 1
                if selected_idx >= scroll_offset + visible_items:
                    scroll_offset += 1
            elif ch == ord(" "):
                if courses:
                    if selected_idx in selected:
                        selected.remove(selected_idx)
                    else:
                        selected.add(selected_idx)
            elif ch in (ord("q"), ord("Q"), 27):
                return []
            elif ch in (10, 13):
                if not selected and len(courses) > 0:
                    selected.add(selected_idx)
                break

        return [courses[i] for i in sorted(selected)]

    def main_menu(self, config: Config) -> bool:
        options = [
            ("Download Courses", True),
            ("Settings", "settings"),
            ("Help", "help"),
            ("Exit", False),
        ]
        selected_idx = 0
        self.stdscr.timeout(-1)

        while True:
            self.stdscr.erase()
            height, width = self.stdscr.getmaxyx()

            self.draw_header("UDEMY-DL")

            for i, (opt_name, _) in enumerate(options):
                if i + 2 >= height - 1:
                    break

                if i == selected_idx:
                    self.safe_addstr(
                        i + 2, 2, f"> {opt_name }", COLOR_DEFAULT, curses.A_REVERSE, width - 4
                    )
                else:
                    self.safe_addstr(i + 2, 2, f"  {opt_name }", COLOR_DEFAULT, 0, width - 4)

            self.draw_footer("[j/k] Navigate  [enter] Select  [q] Quit")
            self.stdscr.refresh()

            ch = self.stdscr.getch()
            if ch in (curses.KEY_UP, ord("k")) and selected_idx > 0:
                selected_idx -= 1
            elif ch in (curses.KEY_DOWN, ord("j")) and selected_idx < len(options) - 1:
                selected_idx += 1
            elif ch in (10, 13):
                action = options[selected_idx][1]
                if action is True:
                    return True
                if action is False:
                    return False
                if action == "settings":
                    self.edit_settings(config)
                elif action == "help":
                    self.show_help()
            elif ch in (ord("q"), ord("Q"), 27):
                return False

    def show_help(self) -> None:
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()

        self.draw_header("HELP")

        lines = [
            "CONFIGURATION",
            "-------------",
            "domain",
            "  Base URL for Udemy (default: https://www.udemy.com)",
            "",
            "token",
            "  Your account's access_token cookie.",
            "  1. Log in to Udemy in your web browser.",
            "  2. Open Developer Tools (F12) -> Application -> Cookies.",
            "  3. Copy the value of the 'access_token' cookie.",
            "",
            "client_id",
            "  Also found in your browser cookies.",
            "",
            "DISCLAIMER",
            "----------",
            "For PERSONAL BACKUP ONLY. Do not distribute downloaded content.",
        ]

        for i, line in enumerate(lines):
            if i + 2 < height - 1:
                if line.isupper() and len(line) > 2:
                    self.safe_addstr(i + 2, 2, line, COLOR_DEFAULT, curses.A_BOLD)
                else:
                    self.safe_addstr(i + 2, 2, line, COLOR_DEFAULT)

        self.draw_footer("Press any key to close")
        self.stdscr.refresh()
        self.stdscr.timeout(-1)
        self.stdscr.getch()
