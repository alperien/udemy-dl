import curses
from typing import Any, Dict, List, Optional

from .config import Config
from .utils import get_logger

logger = get_logger(__name__)

COLOR_DEFAULT = 1
COLOR_ACCENT = 2
COLOR_SUCCESS = 3
COLOR_WARN = 4
COLOR_ERROR = 5
COLOR_DIM = 6


class TUI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self._init_colors()

    def _init_colors(self):
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(COLOR_DEFAULT, curses.COLOR_WHITE, -1)
        curses.init_pair(COLOR_ACCENT, curses.COLOR_GREEN, -1)
        curses.init_pair(COLOR_SUCCESS, curses.COLOR_CYAN, -1)
        curses.init_pair(COLOR_WARN, curses.COLOR_YELLOW, -1)
        curses.init_pair(COLOR_ERROR, curses.COLOR_RED, -1)
        curses.init_pair(COLOR_DIM, curses.COLOR_WHITE, -1)

    def safe_addstr(
        self,
        y: int,
        x: int,
        text: str,
        color: int = 0,
        attr: int = 0,
        max_width: Optional[int] = None,
    ):
        try:
            if max_width and len(text) > max_width:
                text = text[: max_width - 3] + "..."
            self.stdscr.addstr(y, x, text, curses.color_pair(color) | attr)
        except curses.error:
            pass

    def draw_progress_bar(
        self,
        y: int,
        x: int,
        width: int,
        percent: float,
        prefix: str = "",
        suffix: str = "",
        color: int = COLOR_ACCENT,
    ):
        bar_width = width - len(prefix) - len(suffix) - 4
        if bar_width < 5:
            return
        clamped = max(0.0, min(percent, 100.0))
        filled = int((clamped / 100) * bar_width)
        bar = "=" * filled
        if filled < bar_width:
            bar += ">" + " " * (bar_width - filled - 1)
        self.safe_addstr(y, x, prefix, COLOR_DEFAULT, curses.A_BOLD)
        self.safe_addstr(y, x + len(prefix) + 1, f"[{bar}]", color)
        self.safe_addstr(
            y, x + len(prefix) + bar_width + 3, f" {suffix}", COLOR_DEFAULT
        )

    def render_dashboard(
        self,
        state: Dict[str, Any],
        course_index: int,
        total_courses: int,
        log: List[str],
    ):
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()
        if height < 15 or width < 60:
            self.safe_addstr(0, 0, "Terminal too small!", COLOR_ERROR)
            self.stdscr.refresh()
            return

        self.safe_addstr(
            0,
            0,
            f"+-- Downloading Course [{course_index}/{total_courses}] ".ljust(
                width - 1, "-"
            )
            + "+",
            COLOR_ACCENT,
        )
        self.safe_addstr(
            1,
            2,
            f"Course : {state.get('course_title', '')[:width-20]}",
            COLOR_DEFAULT,
            curses.A_BOLD,
        )
        overall_pct = (
            (state["done_vids"] / state["total_vids"] * 100)
            if state["total_vids"] > 0
            else 0
        )
        self.draw_progress_bar(
            2,
            2,
            width - 4,
            overall_pct,
            "Total  :",
            f"{overall_pct:3.0f}% [{state['done_vids']:03d}/{state['total_vids']:03d}]",
            COLOR_SUCCESS,
        )

        self.safe_addstr(
            5,
            2,
            f"File   : {state['current_file'][:width-20]}",
            COLOR_DEFAULT,
            curses.A_BOLD,
        )
        vid_pct = (
            (state["vid_current_secs"] / state["vid_duration_secs"] * 100)
            if state["vid_duration_secs"] > 0
            else 0
        )
        self.draw_progress_bar(
            6, 2, width - 4, vid_pct, "Video  :", f"{vid_pct:3.0f}%", COLOR_WARN
        )

        log_start_y = 9
        for idx, line in enumerate(log[-(height - log_start_y - 1) :]):
            color = (
                COLOR_ERROR
                if "error" in line.lower()
                else (COLOR_SUCCESS if "done" in line.lower() else COLOR_DIM)
            )
            self.safe_addstr(log_start_y + idx, 2, f"> {line}", color, 0, width - 4)
        self.stdscr.refresh()

    def show_error(self, message: str):
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()
        self.safe_addstr(
            height // 2,
            max(0, (width - 40) // 2),
            f"ERROR: {message}",
            COLOR_ERROR,
            curses.A_BOLD,
        )
        self.safe_addstr(
            height // 2 + 1, max(0, (width - 40) // 2), "Press any key...", COLOR_DIM
        )
        self.stdscr.refresh()
        self.stdscr.getch()

    def show_legal_warning(self) -> bool:
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()
        lines = [
            "⚠️  LEGAL DISCLAIMER  ⚠️",
            "",
            "This tool is for PERSONAL BACKUP ONLY.",
            "Downloading courses may violate Udemy's Terms of Service.",
            "",
            "By using this tool, you acknowledge that:",
            "  • You own the courses you download",
            "  • You will NOT distribute downloaded content",
            "  • You are responsible for compliance with applicable laws",
            "",
            "Do you agree to these terms?",
            "[Y] Yes, I agree  |  [N] No, exit",
        ]
        box_width = min(70, width - 4)
        start_y = max(0, height // 2 - 8)
        start_x = max(0, (width - box_width) // 2)
        for i, line in enumerate(lines):
            y = start_y + i
            if y < height - 1:
                color = (
                    COLOR_WARN
                    if "⚠️" in line or "WARNING" in line.upper()
                    else COLOR_DEFAULT
                )
                self.safe_addstr(y, start_x, line.ljust(box_width)[:box_width], color)
        self.stdscr.refresh()
        while True:
            ch = self.stdscr.getch()
            if ch in (ord("y"), ord("Y")):
                return True
            elif ch in (ord("n"), ord("N")):
                return False

    def edit_settings(self, config: Config) -> None:
        curses.curs_set(0)
        keys = list(config.to_dict().keys())
        selected_idx = 0
        while True:
            self.stdscr.clear()
            height, width = self.stdscr.getmaxyx()
            self.safe_addstr(
                0, 0, "+-- Settings ".ljust(width - 1, "-") + "+", COLOR_ACCENT
            )
            for i, key in enumerate(keys):
                prefix = ">" if i == selected_idx else " "
                color = COLOR_SUCCESS if i == selected_idx else COLOR_DIM
                val = str(getattr(config, key))
                if key == "token" and val:
                    val = "*" * min(len(val), 20) + ("..." if len(val) > 20 else "")
                if len(val) > width - 25:
                    val = val[: width - 28] + "..."
                self.safe_addstr(
                    i + 2, 0, f"| {prefix} {key:<20} : {val}", color, 0, width - 2
                )
            self.safe_addstr(
                height - 2,
                0,
                "| [Enter] Edit | [Q] Back ".ljust(width - 1, " ") + "|",
                COLOR_DEFAULT,
            )
            self.stdscr.refresh()
            ch = self.stdscr.getch()
            if ch == curses.KEY_UP and selected_idx > 0:
                selected_idx -= 1
            elif ch == curses.KEY_DOWN and selected_idx < len(keys) - 1:
                selected_idx += 1
            elif ch in (ord("q"), ord("Q")):
                break
            elif ch == 10:
                curses.curs_set(1)
                curses.echo()
                key = keys[selected_idx]
                prompt = f"| New {key} (Blank=cancel, 'CLEAR'=empty): "
                self.safe_addstr(
                    height - 3,
                    0,
                    prompt.ljust(width - 1, " ")[: width - 2] + "|",
                    COLOR_WARN,
                )
                try:
                    new_val = (
                        self.stdscr.getstr(height - 3, len(prompt), 100)
                        .decode()
                        .strip()
                    )
                except Exception:
                    new_val = ""
                if new_val:
                    if new_val.upper() == "CLEAR":
                        new_val = ""
                    elif key in ["download_subtitles", "download_materials"]:
                        new_val = new_val.lower() in ("true", "1", "yes")
                    setattr(config, key, new_val)
                    from .config import save_config

                    save_config(config)
                    logger.info(f"Updated config: {key}")
                curses.noecho()
                curses.curs_set(0)

    def select_courses(self, courses: List[Dict]) -> List[Dict]:
        curses.curs_set(0)
        selected = set()
        selected_idx = 0
        scroll_offset = 0
        while True:
            self.stdscr.clear()
            height, width = self.stdscr.getmaxyx()
            self.safe_addstr(
                0, 0, "+-- Select Courses ".ljust(width - 1, "-") + "+", COLOR_ACCENT
            )
            self.safe_addstr(
                1,
                0,
                "| [Space] Toggle | [Enter] Confirm | [Q] Cancel ".ljust(width - 1, " ")
                + "|",
                COLOR_DEFAULT,
            )
            visible_items = height - 5
            for i in range(visible_items):
                list_idx = scroll_offset + i
                if list_idx >= len(courses):
                    break
                course = courses[list_idx]
                prefix = ">" if list_idx == selected_idx else " "
                box = "[x]" if list_idx in selected else "[ ]"
                color = (
                    COLOR_SUCCESS
                    if list_idx == selected_idx
                    else (COLOR_ACCENT if list_idx in selected else COLOR_DIM)
                )
                title = (
                    course["title"][: width - 25]
                    if len(course["title"]) > width - 25
                    else course["title"]
                )
                self.safe_addstr(
                    i + 3,
                    0,
                    f"| {prefix} {box} {course['id']:<10} {title}",
                    color,
                    0,
                    width - 2,
                )
            self.stdscr.refresh()
            k = self.stdscr.getch()
            if k == curses.KEY_UP and selected_idx > 0:
                selected_idx -= 1
                if selected_idx < scroll_offset:
                    scroll_offset -= 1
            elif k == curses.KEY_DOWN and selected_idx < len(courses) - 1:
                selected_idx += 1
                if selected_idx >= scroll_offset + visible_items:
                    scroll_offset += 1
            elif k == ord(" "):
                if selected_idx in selected:
                    selected.remove(selected_idx)
                else:
                    selected.add(selected_idx)
            elif k in (ord("q"), ord("Q")):
                return []
            elif k == 10:
                if not selected and len(courses) > 0:
                    selected.add(selected_idx)
                break
        return [courses[i] for i in sorted(list(selected))]

    def main_menu(self, config: Config) -> bool:
        options = ["Download Courses", "Settings", "Help", "Exit"]
        selected_idx = 0
        while True:
            self.stdscr.clear()
            height, width = self.stdscr.getmaxyx()
            self.safe_addstr(
                0, 0, "+-- Main Menu ".ljust(width - 1, "-") + "+", COLOR_ACCENT
            )
            for i, opt in enumerate(options):
                prefix = ">" if i == selected_idx else " "
                color = COLOR_SUCCESS if i == selected_idx else COLOR_DIM
                self.safe_addstr(
                    i + 2, 0, f"| {prefix} [{i+1}] {opt}", color, 0, width - 2
                )
            self.stdscr.refresh()
            ch = self.stdscr.getch()
            if ch == curses.KEY_UP and selected_idx > 0:
                selected_idx -= 1
            elif ch == curses.KEY_DOWN and selected_idx < len(options) - 1:
                selected_idx += 1
            elif ch == 10:
                if selected_idx == 0:
                    return True
                elif selected_idx == 1:
                    self.edit_settings(config)
                elif selected_idx == 2:
                    self.show_help()
                elif selected_idx == 3:
                    return False
        return False

    def show_help(self):
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()
        lines = [
            "",
            "  [ domain ]",
            "    Base URL for Udemy (default: https://www.udemy.com)",
            "",
            "  [ token ]",
            "    Your account's access_token cookie.",
            "    1. Log in to Udemy in your web browser.",
            "    2. Open Developer Tools (F12) -> Application -> Cookies.",
            "    3. Copy the value of the 'access_token' cookie.",
            "",
            "  [ client_id ]",
            "    Also found in your browser cookies.",
            "",
            "  ⚠️  WARNING: For PERSONAL BACKUP ONLY!",
            "",
        ]
        self.safe_addstr(
            0, 0, "+-- Help Menu ".ljust(width - 1, "-") + "+", COLOR_ACCENT
        )
        for y in range(1, min(height - 3, len(lines) + 1)):
            text = lines[y - 1] if y - 1 < len(lines) else ""
            self.safe_addstr(
                y, 0, f"| {text}".ljust(width - 1, " ") + "|", COLOR_DEFAULT
            )
        self.safe_addstr(
            height - 2,
            0,
            "| > Press any key to close".ljust(width - 1, " ") + "|",
            COLOR_DIM,
        )
        self.stdscr.refresh()
        self.stdscr.getch()
