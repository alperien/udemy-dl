#!/usr/bin/env python3
"""
Udemy Course Downloader - TUI Application
==========================================
WARNING: This tool is for PERSONAL BACKUP ONLY.
Downloading courses may violate Udemy's Terms of Service.
Do not distribute downloaded content.

Version: 2.0.0 (Fixed & Enhanced)
"""

import os
import re
import json
import curses
import shutil
import subprocess
import signal
import sys
import logging
import select
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict

# Try to import requests, provide helpful error if missing
try:
    import requests
    from requests.exceptions import RequestException, Timeout, HTTPError
except ImportError:
    print("ERROR: 'requests' library not installed.")
    print("Run: pip install requests")
    sys.exit(1)

# =============================================================================
# CONFIGURATION & CONSTANTS
# =============================================================================

CONFIG_FILE = "config.json"
STATE_FILE = "download_state.json"
LOG_FILE = "downloader.log"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Color theme mappings
COLOR_DEFAULT = 1
COLOR_ACCENT = 2
COLOR_SUCCESS = 3
COLOR_WARN = 4
COLOR_ERROR = 5
COLOR_DIM = 6

# Quality options (highest to lowest)
QUALITY_OPTIONS = ["2160", "1440", "1080", "720", "480", "360"]

# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logging():
    """
    Configure logging to FILE ONLY.
    
    NOTE: We do NOT use StreamHandler during curses operation because
    it outputs directly to stdout/stderr, which corrupts the TUI display.
    All user-facing messages should go through the curses UI log instead.
    """
    logger = logging.getLogger("udemy_downloader")
    logger.setLevel(logging.INFO)
    
    # ⚠️ CRITICAL: Prevent propagation to root logger
    # Root logger has default StreamHandler that breaks TUI
    logger.propagate = False
    
    # Clear any existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # File handler only - logs saved to downloader.log
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logging()

# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class DownloadState:
    """Tracks download progress for resume capability."""
    course_id: Optional[int] = None
    course_title: str = ""
    completed_lectures: List[int] = field(default_factory=list)
    total_lectures: int = 0
    last_updated: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'DownloadState':
        return cls(**data)

@dataclass
class Config:
    """Application configuration with validation."""
    domain: str = "https://www.udemy.com"
    token: str = ""
    client_id: str = ""
    dl_path: str = "downloads"
    quality: str = "1080"
    max_workers: int = 1
    download_subtitles: bool = True
    download_materials: bool = True
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def validate(self) -> Tuple[bool, str]:
        """Validate configuration values."""
        if not self.token or len(self.token) < 10:
            return False, "Invalid or missing access token"
        if not self.client_id or len(self.client_id) < 5:
            return False, "Invalid or missing client_id"
        if not self.domain.startswith("http"):
            return False, "Invalid domain URL"
        if self.quality not in QUALITY_OPTIONS:
            return False, f"Invalid quality option. Choose from: {QUALITY_OPTIONS}"
        if self.max_workers < 1 or self.max_workers > 5:
            return False, "max_workers must be between 1 and 5"
        return True, ""

# =============================================================================
# GLOBAL STATE
# =============================================================================

download_interrupted = False
current_download_state: Optional[DownloadState] = None

# =============================================================================
# SIGNAL HANDLING
# =============================================================================

def signal_handler(sig, frame):
    """Handle graceful shutdown on SIGINT/SIGTERM."""
    global download_interrupted
    download_interrupted = True
    logger.warning("Download interrupted by user. Cleaning up...")
    save_download_state()

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def init_colors():
    """Setup curses color pairs for the terminal UI."""
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(COLOR_DEFAULT, curses.COLOR_WHITE, -1)
    curses.init_pair(COLOR_ACCENT, curses.COLOR_GREEN, -1)
    curses.init_pair(COLOR_SUCCESS, curses.COLOR_CYAN, -1)
    curses.init_pair(COLOR_WARN, curses.COLOR_YELLOW, -1)
    curses.init_pair(COLOR_ERROR, curses.COLOR_RED, -1)
    curses.init_pair(COLOR_DIM, curses.COLOR_WHITE, -1)

def set_secure_permissions(file_path: Path):
    """Set restrictive file permissions (owner read/write only)."""
    try:
        os.chmod(file_path, 0o600)
        logger.debug(f"Set secure permissions on {file_path}")
    except OSError as e:
        logger.warning(f"Could not set permissions on {file_path}: {e}")

def sanitize_filename(name: str) -> str:
    """Remove invalid characters from filenames."""
    return re.sub(r'[<>:"/\\|?*]', '-', str(name)).strip()

def time_string_to_seconds(time_str: str) -> int:
    """Converts a timestamp string (HH:MM:SS.ms) into total seconds."""
    try:
        clean_time = time_str.strip().split(".")[0]
        h, m, s = clean_time.split(":")
        return int(h) * 3600 + int(m) * 60 + int(s)
    except (ValueError, AttributeError):
        logger.debug(f"Failed to parse time string: {time_str}")
        return 0

def seconds_to_time_string(seconds: int) -> str:
    """Convert seconds to HH:MM:SS format."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def calculate_eta(current_speed: float, remaining_bytes: int) -> str:
    """Calculate estimated time remaining."""
    if current_speed <= 0:
        return "Unknown"
    seconds = remaining_bytes / current_speed
    if seconds > 3600:
        return f"{seconds/3600:.1f}h"
    elif seconds > 60:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds:.0f}s"

# =============================================================================
# CONFIGURATION MANAGEMENT
# =============================================================================

def load_config() -> Config:
    """Load configuration from file and environment variables."""
    # Default config
    config = Config(
        domain=os.getenv("UDEMY_DOMAIN", "https://www.udemy.com"),
        token=os.getenv("UDEMY_TOKEN", ""),
        client_id=os.getenv("UDEMY_CLIENT_ID", ""),
        dl_path=os.getenv("UDEMY_DL_PATH", "downloads"),
        quality=os.getenv("UDEMY_QUALITY", "1080"),
        max_workers=int(os.getenv("UDEMY_MAX_WORKERS", "1")),
        download_subtitles=os.getenv("UDEMY_DOWNLOAD_SUBTITLES", "true").lower() == "true",
        download_materials=os.getenv("UDEMY_DOWNLOAD_MATERIALS", "true").lower() == "true"
    )
    
    # Load from file (env vars take precedence)
    config_path = Path(CONFIG_FILE)
    if config_path.exists():
        try:
            saved = json.loads(config_path.read_text(encoding='utf-8'))
            # Only update if not set via environment
            if not os.getenv("UDEMY_DOMAIN"):
                config.domain = saved.get("domain", config.domain).strip()
            if not os.getenv("UDEMY_TOKEN"):
                config.token = saved.get("token", config.token).strip()
            if not os.getenv("UDEMY_CLIENT_ID"):
                config.client_id = saved.get("client_id", config.client_id).strip()
            if not os.getenv("UDEMY_DL_PATH"):
                config.dl_path = saved.get("dl_path", config.dl_path).strip()
            if not os.getenv("UDEMY_QUALITY"):
                config.quality = saved.get("quality", config.quality).strip()
            if not os.getenv("UDEMY_MAX_WORKERS"):
                config.max_workers = saved.get("max_workers", config.max_workers)
            if not os.getenv("UDEMY_DOWNLOAD_SUBTITLES"):
                config.download_subtitles = saved.get("download_subtitles", config.download_subtitles)
            if not os.getenv("UDEMY_DOWNLOAD_MATERIALS"):
                config.download_materials = saved.get("download_materials", config.download_materials)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load config file: {e}")
    
    return config

def save_config(config: Config):
    """Save configuration to file with secure permissions."""
    config_path = Path(CONFIG_FILE)
    try:
        config_path.write_text(json.dumps(config.to_dict(), indent=4), encoding='utf-8')
        set_secure_permissions(config_path)
        logger.info("Configuration saved successfully")
    except IOError as e:
        logger.error(f"Failed to save config: {e}")

def load_download_state() -> Optional[DownloadState]:
    """Load previous download state for resume capability."""
    state_path = Path(STATE_FILE)
    if state_path.exists():
        try:
            data = json.loads(state_path.read_text(encoding='utf-8'))
            state = DownloadState.from_dict(data)
            logger.info(f"Loaded download state for course: {state.course_title}")
            return state
        except (json.JSONDecodeError, IOError, KeyError) as e:
            logger.error(f"Failed to load download state: {e}")
    return None

def save_download_state():
    """Save current download state for resume capability."""
    global current_download_state
    if current_download_state is None:
        return
    
    state_path = Path(STATE_FILE)
    current_download_state.last_updated = datetime.now().isoformat()
    try:
        state_path.write_text(json.dumps(current_download_state.to_dict(), indent=4), encoding='utf-8')
        set_secure_permissions(state_path)
        logger.debug("Download state saved")
    except IOError as e:
        logger.error(f"Failed to save download state: {e}")

def clear_download_state():
    """Clear download state file after successful completion."""
    state_path = Path(STATE_FILE)
    if state_path.exists():
        try:
            state_path.unlink()
            logger.debug("Download state cleared")
        except IOError as e:
            logger.error(f"Failed to clear download state: {e}")

# =============================================================================
# CURSES UI HELPERS
# =============================================================================

def safe_addstr(stdscr, y: int, x: int, text: str, color: int = 0, attr: int = 0, max_width: Optional[int] = None):
    """Safely prints text to the curses window, truncating if it exceeds bounds."""
    try:
        if max_width and len(text) > max_width:
            text = text[:max_width-3] + "..."
        stdscr.addstr(y, x, text, curses.color_pair(color) | attr)
    except curses.error:
        pass  # Ignore out-of-bounds rendering errors if terminal resizes

def draw_progress_bar(stdscr, y: int, x: int, width: int, percent: float, prefix: str = "", suffix: str = "", color: int = COLOR_ACCENT):
    """Draws a standard ASCII progress bar."""
    bar_width = width - len(prefix) - len(suffix) - 4
    if bar_width < 5:
        return
        
    filled = int((percent / 100) * bar_width)
    bar = "=" * filled
    if filled < bar_width:
        bar += ">" + " " * (bar_width - filled - 1)
        
    safe_addstr(stdscr, y, x, prefix, COLOR_DEFAULT, curses.A_BOLD)
    safe_addstr(stdscr, y, x + len(prefix) + 1, f"[{bar}]", color)
    safe_addstr(stdscr, y, x + len(prefix) + bar_width + 3, f" {suffix}", COLOR_DEFAULT)

def show_error(stdscr, message: str):
    """Displays a modal error box."""
    stdscr.clear()
    height, width = stdscr.getmaxyx()
    box_width = min(60, width - 4)
    start_y = max(0, height // 2 - 3)
    start_x = max(0, (width - box_width) // 2)
    
    safe_addstr(stdscr, start_y, start_x, "+-- [ Error ] ".ljust(box_width-1, "-") + "+", COLOR_ERROR)
    safe_addstr(stdscr, start_y+1, start_x, "|".ljust(box_width-1, " ") + "|", COLOR_ERROR)
    
    # Word wrap the message
    words = message.split()
    lines = []
    current_line = ""
    for word in words:
        if len(current_line) + len(word) + 1 < box_width - 4:
            current_line += (" " if current_line else "") + word
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    
    for i, line in enumerate(lines[:3]):
        safe_addstr(stdscr, start_y+2+i, start_x, f"|  {line}".ljust(box_width-1, " ") + "|", COLOR_ERROR, curses.A_BOLD)
    
    safe_addstr(stdscr, start_y+5, start_x, "|  > Press any key to return...".ljust(box_width-1, " ") + "|", COLOR_DIM)
    safe_addstr(stdscr, start_y+6, start_x, "|".ljust(box_width-1, " ") + "|", COLOR_ERROR)
    safe_addstr(stdscr, start_y+7, start_x, "+".ljust(box_width-1, "-") + "+", COLOR_ERROR)
    
    stdscr.refresh()
    stdscr.getch()
    logger.error(message)

def show_help(stdscr):
    """Displays instructions on how to configure the tool."""
    stdscr.clear()
    height, width = stdscr.getmaxyx()
    
    lines = [
        "",
        "  [ domain ]",
        "    Base URL for Udemy (default: https://www.udemy.com)",
        "    Only change this if using Udemy for Business.",
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
        "  [ dl_path ]",
        "    Folder where courses will be saved.",
        "",
        "  [ quality ]",
        f"    Preferred video quality: {', '.join(QUALITY_OPTIONS)}",
        "",
        "  ⚠️  WARNING: For PERSONAL BACKUP ONLY!",
        "     Do not distribute downloaded content.",
        ""
    ]
    
    safe_addstr(stdscr, 0, 0, "+-- Help Menu ".ljust(width-1, "-") + "+", COLOR_ACCENT)
    for y in range(1, min(height-3, len(lines)+1)):
        text = lines[y-1] if y-1 < len(lines) else ""
        safe_addstr(stdscr, y, 0, f"| {text}".ljust(width-1, " ") + "|", COLOR_DEFAULT)
        
    safe_addstr(stdscr, height-3, 0, "+".ljust(width-1, "-") + "+", COLOR_ACCENT)
    safe_addstr(stdscr, height-2, 0, "| > Press any key to close".ljust(width-1, " ") + "|", COLOR_DIM)
    safe_addstr(stdscr, height-1, 0, "+".ljust(width-1, "-") + "+", COLOR_ACCENT)
    
    stdscr.refresh()
    stdscr.getch()

def show_legal_warning(stdscr) -> bool:
    """Display legal disclaimer and get user acknowledgment."""
    stdscr.clear()
    height, width = stdscr.getmaxyx()
    
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
        "[Y] Yes, I agree  |  [N] No, exit"
    ]
    
    box_width = min(70, width - 4)
    start_y = max(0, height // 2 - 8)
    start_x = max(0, (width - box_width) // 2)
    
    for i, line in enumerate(lines):
        y = start_y + i
        if y < height - 1:
            safe_addstr(stdscr, y, start_x, line.ljust(box_width)[:box_width], COLOR_WARN if "⚠️" in line or "WARNING" in line.upper() else COLOR_DEFAULT)
    
    stdscr.refresh()
    
    while True:
        ch = stdscr.getch()
        if ch in (ord('y'), ord('Y')):
            return True
        elif ch in (ord('n'), ord('N')):
            return False

def edit_settings(stdscr, config: Config):
    """Simple UI for modifying configuration values."""
    curses.curs_set(0)
    keys = list(config.to_dict().keys())
    selected_idx = 0
    
    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        safe_addstr(stdscr, 0, 0, "+-- Settings ".ljust(width-1, "-") + "+", COLOR_ACCENT)
        
        for i, key in enumerate(keys):
            prefix = ">" if i == selected_idx else " "
            color = COLOR_SUCCESS if i == selected_idx else COLOR_DIM
            val = str(getattr(config, key))
            if key == "token" and val:
                val = "*" * min(len(val), 20) + ("..." if len(val) > 20 else "")
            if len(val) > width - 25:
                val = val[:width-28] + "..."
                
            safe_addstr(stdscr, i + 2, 0, f"| {prefix} {key:<20} : {val}", color, 0, width-2)
            safe_addstr(stdscr, i + 2, width-1, "|", COLOR_ACCENT)
        
        safe_addstr(stdscr, height-2, 0, "| [Enter] Edit | [Q] Back ".ljust(width-1, " ") + "|", COLOR_DEFAULT)
        safe_addstr(stdscr, height-1, 0, "+".ljust(width-1, "-") + "+", COLOR_ACCENT)
        stdscr.refresh()
        
        ch = stdscr.getch()
        if ch == curses.KEY_UP and selected_idx > 0:
            selected_idx -= 1
        elif ch == curses.KEY_DOWN and selected_idx < len(keys) - 1:
            selected_idx += 1
        elif ch in (ord('q'), ord('Q')):
            break
        elif ch == 10:  # Enter key
            curses.curs_set(1)
            curses.echo()
            key = keys[selected_idx]
            prompt = f"| New {key} (Leave blank to cancel): "
            safe_addstr(stdscr, height-3, 0, prompt.ljust(width-1, " ")[:width-2] + "|", COLOR_WARN)
            
            try:
                new_val = stdscr.getstr(height-3, len(prompt), 100).decode().strip()
            except:
                new_val = ""
            
            if new_val:
                if key == "download_subtitles" or key == "download_materials":
                    new_val = new_val.lower() in ('true', '1', 'yes')
                elif key == "max_workers":
                    try:
                        new_val = int(new_val)
                    except ValueError:
                        new_val = config.max_workers
                setattr(config, key, new_val)
                save_config(config)
                logger.info(f"Updated config: {key}")
                
            curses.noecho()
            curses.curs_set(0)

def main_menu(stdscr, config: Config) -> bool:
    """Displays the main application menu."""
    options = ["Download Courses", "Settings", "Help", "Exit"]
    selected_idx = 0
    
    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        safe_addstr(stdscr, 0, 0, "+-- Main Menu ".ljust(width-1, "-") + "+", COLOR_ACCENT)
        
        for i, opt in enumerate(options):
            prefix = ">" if i == selected_idx else " "
            color = COLOR_SUCCESS if i == selected_idx else COLOR_DIM
            safe_addstr(stdscr, i + 2, 0, f"| {prefix} [{i+1}] {opt}", color, 0, width-2)
            safe_addstr(stdscr, i + 2, width-1, "|", COLOR_ACCENT)
            
        safe_addstr(stdscr, height-1, 0, "+".ljust(width-1, "-") + "+", COLOR_ACCENT)
        stdscr.refresh()
        
        ch = stdscr.getch()
        if ch == curses.KEY_UP and selected_idx > 0:
            selected_idx -= 1
        elif ch == curses.KEY_DOWN and selected_idx < len(options) - 1:
            selected_idx += 1
        elif ch == 10:  # Enter key
            if selected_idx == 0:
                return True
            elif selected_idx == 1:
                edit_settings(stdscr, config)
            elif selected_idx == 2:
                show_help(stdscr)
            elif selected_idx == 3:
                return False

# =============================================================================
# API & DOWNLOAD FUNCTIONS
# =============================================================================

def create_session(config: Config) -> requests.Session:
    """Create authenticated requests session."""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {config.token}",
        "User-Agent": USER_AGENT,
        "Origin": config.domain,
        "Referer": f"{config.domain}/"
    })
    session.cookies.update({
        "access_token": config.token,
        "client_id": config.client_id
    })
    return session

def fetch_owned_courses(stdscr, session: requests.Session, api_base: str) -> List[Dict]:
    """Pulls the user's library of courses from the Udemy API."""
    stdscr.clear()
    height, width = stdscr.getmaxyx()
    safe_addstr(stdscr, height//2, max(0, (width-40)//2), "Fetching your courses...", COLOR_ACCENT, curses.A_BLINK)
    stdscr.refresh()
    
    url = f"{api_base}/api-2.0/users/me/subscribed-courses/?page_size=100"
    courses = []
    
    while url:
        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            for item in data.get("results", []):
                courses.append({"id": item["id"], "title": item["title"]})
            url = data.get("next")
        except Timeout:
            logger.error("Request timed out while fetching courses")
            break
        except HTTPError as e:
            logger.error(f"HTTP error while fetching courses: {e}")
            break
        except (RequestException, json.JSONDecodeError) as e:
            logger.error(f"Error fetching courses: {e}")
            break
            
    logger.info(f"Fetched {len(courses)} courses")
    return courses

def select_courses(stdscr, courses: List[Dict]) -> List[Dict]:
    """Allows the user to select which courses to download."""
    curses.curs_set(0)
    selected = set()
    selected_idx = 0
    scroll_offset = 0
    
    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        safe_addstr(stdscr, 0, 0, "+-- Select Courses ".ljust(width-1, "-") + "+", COLOR_ACCENT)
        safe_addstr(stdscr, 1, 0, "| [Space] Toggle | [Enter] Confirm | [Q] Cancel ".ljust(width-1, " ") + "|", COLOR_DEFAULT)
        safe_addstr(stdscr, 2, 0, "+".ljust(width-1, "-") + "+", COLOR_ACCENT)
        
        visible_items = height - 5
        for i in range(visible_items):
            list_idx = scroll_offset + i
            if list_idx >= len(courses):
                break
                
            course = courses[list_idx]
            prefix = ">" if list_idx == selected_idx else " "
            box = "[x]" if list_idx in selected else "[ ]"
            color = COLOR_SUCCESS if list_idx == selected_idx else (COLOR_ACCENT if list_idx in selected else COLOR_DIM)
            
            title = course['title'][:width-25] if len(course['title']) > width-25 else course['title']
            safe_addstr(stdscr, i + 3, 0, f"| {prefix} {box} {course['id']:<10} {title}", color, 0, width - 2)
            safe_addstr(stdscr, i + 3, width - 1, "|", COLOR_ACCENT)
            
        safe_addstr(stdscr, height - 2, 0, "+".ljust(width-1, "-") + "+", COLOR_ACCENT)
        stdscr.refresh()
        
        k = stdscr.getch()
        
        if k == curses.KEY_UP and selected_idx > 0:
            selected_idx -= 1
            if selected_idx < scroll_offset:
                scroll_offset -= 1
        elif k == curses.KEY_DOWN and selected_idx < len(courses) - 1:
            selected_idx += 1
            if selected_idx >= scroll_offset + visible_items:
                scroll_offset += 1
        elif k == ord(' '):
            if selected_idx in selected:
                selected.remove(selected_idx)
            else:
                selected.add(selected_idx)
        elif k in (ord('q'), ord('Q')):
            return []
        elif k == 10:  # Enter
            if not selected and len(courses) > 0:
                selected.add(selected_idx)
            break
            
    return [courses[i] for i in sorted(list(selected))]

def get_quality_video_url(asset_data: Optional[Dict], quality_pref: str = "1080") -> str:
    """Extracts the best available video URL based on quality preference."""
    if not asset_data:
        return ""
    
    # Prefer HLS streams if available
    if hls_url := asset_data.get("hls_url"):
        return hls_url
    
    # Get quality preference index
    try:
        pref_index = QUALITY_OPTIONS.index(quality_pref)
    except ValueError:
        pref_index = 2  # Default to 1080
    
    # Fallback to standard MP4 streams
    stream_urls = asset_data.get("stream_urls") or {}
    videos = stream_urls.get("Video", [])
    
    if not videos:
        return ""
    
    # Try to find preferred quality or better
    for i in range(pref_index, len(QUALITY_OPTIONS)):
        for v in videos:
            if v.get("label") == QUALITY_OPTIONS[i]:
                return v.get("file", "")
    
    # Fallback to highest available
    try:
        best_video = max(videos, key=lambda v: int(v.get("label", "0") or 0))
        return best_video.get("file", "")
    except (ValueError, TypeError):
        return ""

def validate_video(path: Path) -> bool:
    """Verify downloaded file is complete using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=10
        )
        duration = float(result.stdout.strip())
        return duration > 0
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError) as e:
        logger.debug(f"Video validation failed for {path}: {e}")
        return False

def download_subtitles(session: requests.Session, lecture_id: int, course_id: int, 
                       output_path: Path, domain: str) -> List[Path]:
    """Download available subtitle tracks."""
    downloaded = []
    try:
        url = f"{domain}/api-2.0/courses/{course_id}/lectures/{lecture_id}/subtitles"
        response = session.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        subtitles_dir = output_path.parent
        for caption in data.get("captions", []):
            lang = caption.get("language", "en")
            srt_url = caption.get("url")
            if srt_url:
                srt_path = subtitles_dir / f"{output_path.stem}.{lang}.srt"
                try:
                    # Subtitle URLs are often external (not authenticated)
                    sub_response = requests.get(srt_url, timeout=30, stream=True)
                    sub_response.raise_for_status()
                    
                    # Handle both VTT and SRT formats
                    content = sub_response.text
                    if content.startswith("WEBVTT"):
                        # Convert VTT to SRT format (basic conversion)
                        content = content.replace("WEBVTT\n\n", "").replace("WEBVTT", "")
                    
                    srt_path.write_text(content, encoding='utf-8')
                    downloaded.append(srt_path)
                    logger.info(f"Downloaded subtitle: {srt_path.name}")
                except Exception as e:
                    logger.warning(f"Failed to download subtitle {lang}: {e}")
    except Exception as e:
        logger.warning(f"Failed to fetch subtitles for lecture {lecture_id}: {e}")
    
    return downloaded


def download_presentations(session: requests.Session, lecture_id: int, course_id: int,
                           output_path: Path, domain: str) -> List[Path]:
    """Download presentation files (PPTX, PDF slides)."""
    downloaded = []
    try:
        # Presentations are often in a separate endpoint
        url = f"{domain}/api-2.0/courses/{course_id}/lectures/{lecture_id}/attachments"
        response = session.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        presentations_dir = output_path.parent / "00-presentations"
        presentations_dir.mkdir(parents=True, exist_ok=True)
        
        for asset in data.get("results", []):
            asset_type = asset.get("_class", "").lower()
            file_url = asset.get("file_url")
            filename = asset.get("filename", "unknown")
            
            # Only process presentation-type assets
            if asset_type not in ["presentation", "slide", "powerpoint"]:
                # Also check filename extension
                if not any(filename.lower().endswith(ext) for ext in [".pptx", ".ppt", ".pdf", ".key"]):
                    continue
            
            if not file_url:
                logger.debug(f"No URL for presentation: {filename}")
                continue
            
            # Sanitize filename
            filename = sanitize_filename(filename)
            
            # Ensure extension
            if "." not in filename:
                ext = Path(file_url).suffix if file_url else ".pptx"
                filename = f"{filename}{ext}"
            
            try:
                pres_path = presentations_dir / filename
                
                # Try authenticated request first
                pres_response = session.get(file_url, timeout=30, stream=True)
                
                # Fallback to unauthenticated if needed
                if pres_response.status_code in [401, 403, 404]:
                    pres_response = requests.get(file_url, timeout=30, stream=True)
                
                pres_response.raise_for_status()
                
                # Download in chunks
                with open(pres_path, 'wb') as f:
                    for chunk in pres_response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                # Verify download
                if pres_path.exists() and pres_path.stat().st_size > 0:
                    downloaded.append(pres_path)
                    logger.info(f"Downloaded presentation: {filename} ({pres_path.stat().st_size} bytes)")
                else:
                    logger.warning(f"Presentation file empty: {filename}")
                    if pres_path.exists():
                        pres_path.unlink()
                        
            except Exception as e:
                logger.warning(f"Failed to download presentation {filename}: {e}")
                
    except Exception as e:
        logger.warning(f"Failed to fetch presentations for lecture {lecture_id}: {e}")
    
    return downloaded

def download_materials(session: requests.Session, lecture_id: int, course_id: int,
                       output_path: Path, domain: str) -> List[Path]:
    """Download supplementary materials (PDFs, source code, etc.)."""
    downloaded = []
    try:
        url = f"{domain}/api-2.0/courses/{course_id}/lectures/{lecture_id}/supplementary-assets"
        response = session.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        materials_dir = output_path.parent / "00-materials"
        materials_dir.mkdir(parents=True, exist_ok=True)
        
        for asset in data.get("results", []):
            file_url = asset.get("file_url")
            filename = asset.get("filename", "unknown")
            
            # Better filename sanitization
            filename = sanitize_filename(filename)
            
            if asset_type in ["presentation", "slide", "powerpoint"]:
                continue


            # Ensure filename has extension
            if "." not in filename:
                # Try to get extension from URL
                ext = Path(file_url).suffix if file_url else ""
                if ext:
                    filename = f"{filename}{ext}"
                else:
                    filename = f"{filename}.file"
            
            # Skip if no URL
            if not file_url:
                logger.warning(f"No URL for material: {filename}")
                continue
            
            # Sanitize again after adding extension
            filename = sanitize_filename(filename)
            
            if file_url and filename:
                try:
                    # Some material URLs require authentication, some don't
                    # Try with session first (authenticated)
                    mat_response = session.get(file_url, timeout=30, stream=True)
                    
                    # If 403/401, try without auth (some URLs are public)
                    if mat_response.status_code in [401, 403]:
                        mat_response = requests.get(file_url, timeout=30, stream=True)
                    
                    mat_response.raise_for_status()
                    
                    # Write in binary mode for all file types
                    mat_path = materials_dir / filename
                    
                    # Use stream for large files
                    with open(mat_path, 'wb') as f:
                        for chunk in mat_response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    # Verify file was written
                    if mat_path.exists() and mat_path.stat().st_size > 0:
                        downloaded.append(mat_path)
                        logger.info(f"Downloaded material: {filename} ({mat_path.stat().st_size} bytes)")
                    else:
                        logger.warning(f"Material file empty or missing: {filename}")
                        if mat_path.exists():
                            mat_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to download material {filename}: {e}")
                    # Clean up partial file
                    if 'mat_path' in locals() and mat_path.exists():
                        mat_path.unlink()
    except Exception as e:
        logger.warning(f"Failed to fetch materials for lecture {lecture_id}: {e}")
    
    return downloaded

def read_ffmpeg_output(proc: subprocess.Popen):
    """Read ffmpeg stderr line-by-line with timeout."""
    while True:
        ready, _, _ = select.select([proc.stderr], [], [], 0.1)
        if ready:
            line = proc.stderr.readline()
            if line:
                yield line.decode('utf-8', 'ignore').strip().lower()
        if proc.poll() is not None:
            # Read any remaining output
            remaining = proc.stderr.read()
            if remaining:
                yield remaining.decode('utf-8', 'ignore').strip().lower()
            break

# =============================================================================
# MAIN APPLICATION
# =============================================================================

def main(stdscr):
    global download_interrupted, current_download_state
    
    init_colors()
    curses.curs_set(0)
    
    # Check dependencies
    if not shutil.which("ffmpeg"):
        show_error(stdscr, "ffmpeg is not installed or not in PATH. Please install it to download videos.")
        return
    
    if not shutil.which("ffprobe"):
        logger.warning("ffprobe not found. Video validation will be skipped.")
    
    # Show legal warning
    if not show_legal_warning(stdscr):
        logger.info("User declined legal terms. Exiting.")
        return
    
    # Load Config
    config = load_config()
    
    # Validate config
    valid, error_msg = config.validate()
    if not valid:
        logger.error(f"Config validation failed: {error_msg}")
        edit_settings(stdscr, config)
        valid, error_msg = config.validate()
        if not valid:
            show_error(stdscr, f"Configuration invalid: {error_msg}")
            return
    
    # Main loop
    while True:
        if download_interrupted:
            logger.info("Download interrupted. Returning to menu.")
            download_interrupted = False
        
        if not main_menu(stdscr, config):
            break

        # Setup HTTP Client
        try:
            session = create_session(config)
        except Exception as e:
            show_error(stdscr, f"Failed to create session: {e}")
            continue

        all_courses = fetch_owned_courses(stdscr, session, config.domain)
        if not all_courses:
            show_error(stdscr, "Could not fetch courses. Check your token and client_id.")
            continue

        chosen_courses = select_courses(stdscr, all_courses)
        if not chosen_courses:
            continue
        
        # Regexes for parsing ffmpeg terminal output
        DURATION_REGEX = re.compile(r"duration:\s*(?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?)")
        STATS_REGEX = re.compile(r"size=\s*(?P<size>\d+[a-z]*)\s+time=(?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?).*?speed=\s*(?P<speed>[\d\.]+x)")

        for course_index, course in enumerate(chosen_courses, 1):
            if download_interrupted:
                logger.info("Download interrupted by user.")
                save_download_state()
                break
            
            # Sanitize folder name
            folder_name = sanitize_filename(course['title'])
            base_dir = Path(config.dl_path) / folder_name
            
            # Activity Log (limited size)
            MAX_LOG_ENTRIES = 100
            log = []
            
            # UI State Tracker
            state = {
                "total_vids": 0, "done_vids": 0, "current_file": "Initializing...",
                "ff_time": "00:00:00", "ff_size": "0kb", "ff_speed": "0.0x",
                "vid_duration_secs": 0, "vid_current_secs": 0, "vid_duration_str": "00:00:00"
            }

            def render_ui():
                """Nested function to redraw the screen easily using local state variables."""
                stdscr.clear()
                height, width = stdscr.getmaxyx()
                if height < 15 or width < 60:
                    safe_addstr(stdscr, 0, 0, "Terminal too small!", COLOR_ERROR)
                    stdscr.refresh()
                    return

                # Header
                safe_addstr(stdscr, 0, 0, f"+-- Downloading Course [{course_index}/{len(chosen_courses)}] ".ljust(width-1, "-") + "+", COLOR_ACCENT)
                for i in range(1, 4):
                    safe_addstr(stdscr, i, 0, "|", COLOR_ACCENT)
                    safe_addstr(stdscr, i, width-1, "|", COLOR_ACCENT)
                
                # Course progress
                safe_addstr(stdscr, 1, 2, f"Course : {course['title'][:width-20]}", COLOR_DEFAULT, curses.A_BOLD)
                overall_pct = (state['done_vids'] / state['total_vids'] * 100) if state['total_vids'] > 0 else 0
                draw_progress_bar(stdscr, 2, 2, width - 4, overall_pct, "Total  :", f"{overall_pct:3.0f}% [{state['done_vids']:03d}/{state['total_vids']:03d}]", COLOR_SUCCESS)

                safe_addstr(stdscr, 4, 0, "+".ljust(width-1, "-") + "+", COLOR_ACCENT)

                # Active video progress
                for i in range(5, 8):
                    safe_addstr(stdscr, i, 0, "|", COLOR_ACCENT)
                    safe_addstr(stdscr, i, width-1, "|", COLOR_ACCENT)
                
                safe_addstr(stdscr, 5, 2, f"File   : {state['current_file'][:width-20]}", COLOR_DEFAULT, curses.A_BOLD)
                vid_pct = (state['vid_current_secs'] / state['vid_duration_secs'] * 100) if state['vid_duration_secs'] > 0 else 0
                draw_progress_bar(stdscr, 6, 2, width - 4, vid_pct, "Video  :", f"{vid_pct:3.0f}%", COLOR_WARN)
                
                stats_line = f"Time: {state['ff_time']} / {state['vid_duration_str']}  |  Size: {state['ff_size']:<8}  |  Speed: {state['ff_speed']:<5}"
                safe_addstr(stdscr, 7, 2, stats_line, COLOR_DIM)

                # Activity Log
                safe_addstr(stdscr, 8, 0, "+-- Activity Log ".ljust(width-1, "-") + "+", COLOR_ACCENT)

                log_start_y = 9
                for y in range(log_start_y, height - 1):
                    safe_addstr(stdscr, y, 0, "|", COLOR_ACCENT)
                    safe_addstr(stdscr, y, width-1, "|", COLOR_ACCENT)
                    
                log_capacity = height - log_start_y - 1
                for idx, line in enumerate(log[-log_capacity:]):
                    color = COLOR_ERROR if "error" in line.lower() else (COLOR_SUCCESS if "done" in line.lower() or "ok" in line.lower() else COLOR_DIM)
                    safe_addstr(stdscr, log_start_y + idx, 2, f"> {line}", color, 0, width - 4)

                safe_addstr(stdscr, height-1, 0, "+".ljust(width-1, "-") + "+", COLOR_ACCENT)
                stdscr.refresh()

            def add_log(msg: str):
                """Helper to append log messages and trigger a UI redraw."""
                ts = datetime.now().strftime("%H:%M:%S")
                log.append(f"[{ts}] {msg}")
                # Limit log size
                if len(log) > MAX_LOG_ENTRIES:
                    log.pop(0)
                render_ui()
                logger.info(msg)

            # -----------------------------------------------------------------
            # Step 1: Map out the course structure (Chapters & Lectures)
            # -----------------------------------------------------------------
            state["current_file"] = "Fetching metadata..."
            add_log(f"[INFO] Analyzing course ID: {course['id']}...")
            
            # Initialize download state for resume capability
            current_download_state = DownloadState(
                course_id=course['id'],
                course_title=course['title'],
                total_lectures=0
            )
            
            # API endpoint to get all course items
            url = f"{config.domain}/api-2.0/courses/{course['id']}/subscriber-curriculum-items/?page=1&page_size=100&fields[lecture]=title,asset,id&fields[chapter]=title&fields[asset]=stream_urls,hls_url"
            
            download_queue = []
            chapter_index = 0
            lecture_index = 0
            current_chapter_dir = base_dir
            lecture_ids = []  # Track lecture IDs for subtitle/material download
            
            while url:
                try:
                    response = session.get(url, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                except Timeout:
                    add_log(f"[ERROR] Connection timeout")
                    break
                except HTTPError as e:
                    add_log(f"[ERROR] HTTP error: {e}")
                    break
                except (RequestException, json.JSONDecodeError) as e:
                    add_log(f"[ERROR] Connection issue: {e}")
                    break

                for item in data.get("results", []):
                    item_type = item.get("_class")
                    clean_title = sanitize_filename(str(item.get("title") or "Unknown"))
                    
                    if item_type == "chapter":
                        # Create a new folder for the chapter
                        chapter_index += 1
                        lecture_index = 0
                        current_chapter_dir = base_dir / f"{chapter_index:02d} - {clean_title}"
                        download_queue.append({"type": "folder", "path": current_chapter_dir, "title": clean_title})
                        
                    elif item_type == "lecture" and "asset" in item:
                        # Queue the video inside the current chapter folder
                        lecture_index += 1
                        lecture_id = item.get("id")
                        if lecture_id:
                            lecture_ids.append(lecture_id)
                        
                        video_url = get_quality_video_url(item.get("asset"), config.quality)
                        if video_url:
                            file_path = current_chapter_dir / f"{lecture_index:03d} - {clean_title}.mp4"
                            download_queue.append({
                                "type": "video", 
                                "title": clean_title, 
                                "url": video_url, 
                                "path": file_path,
                                "lecture_id": lecture_id
                            })
                            state["total_vids"] += 1
                            current_download_state.total_lectures += 1
                            
                url = data.get("next")
                render_ui()

            add_log(f"[INFO] Found {state['total_vids']} videos to download.")

            # Check for resume capability
            saved_state = load_download_state()
            completed_lectures = set()
            if saved_state and saved_state.course_id == course['id']:
                completed_lectures = set(saved_state.completed_lectures)
                add_log(f"[RESUME] Found {len(completed_lectures)} previously completed lectures")

            # -----------------------------------------------------------------
            # Step 2: Download the queued items via FFmpeg
            # -----------------------------------------------------------------
            for item in download_queue:
                if download_interrupted:
                    add_log("[WARN] Download interrupted. Saving progress...")
                    save_download_state()
                    break
                    
                if item["type"] == "folder":
                    item["path"].mkdir(parents=True, exist_ok=True)
                    add_log(f"[SYS] Created folder: {item['path'].name}")
                    
                elif item["type"] == "video":
                    state["current_file"] = item["title"]
                    out_path = item["path"]
                    lecture_id = item.get("lecture_id")
                    
                    # Check if already completed in previous session
                    if lecture_id and lecture_id in completed_lectures:
                        add_log(f"[CACHE] Skipping completed lecture: {item['title'][:30]}...")
                        state["done_vids"] += 1
                        if current_download_state:
                            current_download_state.completed_lectures.append(lecture_id)
                        continue

                    # Check if file already exists and is valid
                    if out_path.exists() and out_path.stat().st_size > 1024:
                        if validate_video(out_path):
                            size_mb = out_path.stat().st_size / (1024 * 1024)
                            add_log(f"[CACHE] Skipping existing file: {item['title'][:20]}... ({size_mb:.1f}MB)")
                            state["done_vids"] += 1
                            if lecture_id and current_download_state:
                                current_download_state.completed_lectures.append(lecture_id)
                                save_download_state()
                            continue
                        else:
                            add_log(f"[WARN] Invalid file detected, re-downloading: {item['title'][:20]}")
                            out_path.unlink()

                    add_log(f"[DOWNLOAD] Starting: {item['title'][:30]}...")
                    
                    # FFmpeg needs the authentication headers to pull the HLS stream
                    headers = f"Authorization: Bearer {config.token}\\r\\nOrigin: {config.domain}\\r\\nReferer: {config.domain}/\\r\\n"
                    cmd = ["ffmpeg", "-y", "-headers", headers, "-i", item["url"], "-c", "copy", "-bsf:a", "aac_adtstoasc", str(out_path)]
                    
                    # Run FFmpeg and hide standard output, but capture stderr to parse progress
                    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL)
                    
                    # Reset stats for the new video
                    state.update({
                        "ff_time": "00:00:00", "ff_size": "0kb", "ff_speed": "0.0x",
                        "vid_duration_secs": 0, "vid_current_secs": 0, "vid_duration_str": "??:??:??"
                    })
                    
                    # Read FFmpeg's terminal output in real-time
                    try:
                        for line in read_ffmpeg_output(proc):
                            if download_interrupted:
                                proc.terminate()
                                add_log("[WARN] FFmpeg terminated by user")
                                break
                                
                            # Catch the total duration of the video when FFmpeg first prints it
                            if state["vid_duration_secs"] == 0:
                                if match := DURATION_REGEX.search(line):
                                    time_val = match.group("time").split(".")[0]
                                    state["vid_duration_str"] = time_val
                                    state["vid_duration_secs"] = time_string_to_seconds(time_val)
                            
                            # Catch the live progress updates
                            if match := STATS_REGEX.search(line):
                                time_val = match.group("time").split(".")[0]
                                state["ff_size"] = match.group("size")
                                state["ff_time"] = time_val
                                state["vid_current_secs"] = time_string_to_seconds(time_val)
                                state["ff_speed"] = match.group("speed").strip()
                                render_ui()
                    except Exception as e:
                        logger.error(f"Error reading ffmpeg output: {e}")
                    
                    proc.wait()
                    
                    # Validate downloaded file
                    if out_path.exists() and validate_video(out_path):
                        state["done_vids"] += 1
                        add_log(f"[DONE] Finished {state['ff_size']} file.")
                        
                        # Update completed lectures
                        if lecture_id and current_download_state:
                            current_download_state.completed_lectures.append(lecture_id)
                            save_download_state()
                        
                        # Download subtitles if enabled
                        if config.download_subtitles and lecture_id:
                            subs = download_subtitles(session, lecture_id, course['id'], out_path, config.domain)
                            if subs:
                                add_log(f"[SUBS] Downloaded {len(subs)} subtitle track(s)")
                        
                        # Download materials if enabled
                        if config.download_materials and lecture_id:
                            mats = download_materials(session, lecture_id, course['id'], out_path, config.domain)
                            if mats:
                                add_log(f"[MATS] Downloaded {len(mats)} material file(s)")
                    else:
                        add_log(f"[ERROR] Download failed or invalid file: {item['title'][:30]}")
                        if out_path.exists():
                            out_path.unlink()
                    
                    render_ui()

            # Clear download state after successful course completion
            if not download_interrupted and current_download_state:
                clear_download_state()
            current_download_state = None

        # All selected courses are done
        if not download_interrupted:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            safe_addstr(stdscr, height // 2, max(0, (width - 40) // 2), "All downloads completed successfully!", COLOR_SUCCESS, curses.A_BOLD)
            safe_addstr(stdscr, height // 2 + 1, max(0, (width - 40) // 2), "[ Press any key to return to menu ]", COLOR_DIM)
            stdscr.refresh()
            stdscr.getch()

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        logger.info("User pressed Ctrl+C, exiting cleanly")
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
        print(f"\nFatal error: {e}")
        print("Check downloader.log for details")
        sys.exit(1)
