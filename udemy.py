import os
import re
import json
import curses
import shutil
import subprocess
import requests
from pathlib import Path
from datetime import datetime

# --- Configuration & Constants ---
CONFIG_FILE = "config.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Color theme mappings
COLOR_DEFAULT = 1
COLOR_ACCENT = 2
COLOR_SUCCESS = 3
COLOR_WARN = 4
COLOR_ERROR = 5
COLOR_DIM = 6

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

def get_highest_quality_video_url(asset_data):
    """Extracts the best available video URL from Udemy's asset payload."""
    if not asset_data: 
        return ""
    
    # Prefer HLS streams if available
    if hls_url := asset_data.get("hls_url"): 
        return hls_url
    
    # Fallback to standard MP4 streams, grabbing the highest resolution
    stream_urls = asset_data.get("stream_urls") or {}
    videos = stream_urls.get("Video", [])
    
    if not videos:
        return ""
        
    # Sort by the 'label' (which is usually the resolution, e.g., "720", "1080")
    best_video = max(videos, key=lambda v: int(v.get("label", "0") or 0))
    return best_video.get("file", "")

def time_string_to_seconds(time_str):
    """Converts a timestamp string (HH:MM:SS.ms) into total seconds."""
    try:
        clean_time = time_str.strip().split(".")[0]
        h, m, s = clean_time.split(":")
        return int(h) * 3600 + int(m) * 60 + int(s)
    except Exception:
        return 0

def safe_addstr(stdscr, y, x, text, color=0, attr=0, max_width=None):
    """Safely prints text to the curses window, truncating if it exceeds bounds."""
    try:
        if max_width and len(text) > max_width:
            text = text[:max_width-3] + "..."
        # Using lowercase purely for stylistic CLI preference
        stdscr.addstr(y, x, text.lower(), curses.color_pair(color) | attr)
    except curses.error:
        pass # Ignore out-of-bounds rendering errors if terminal resizes

def draw_progress_bar(stdscr, y, x, width, percent, prefix="", suffix="", color=COLOR_ACCENT):
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

def read_ffmpeg_output(proc):
    """Reads ffmpeg stderr (where it prints progress) character by character to yield lines."""
    buf = bytearray()
    while True:
        char = proc.stderr.read(1)
        if not char and proc.poll() is not None:
            break
        if char in (b'\r', b'\n'):
            if buf:
                yield buf.decode('utf-8', 'ignore').lower()
                buf.clear()
        else:
            buf.extend(char)

def show_error(stdscr, message):
    """Displays a modal error box."""
    stdscr.clear()
    height, width = stdscr.getmaxyx()
    box_width = 60
    start_y = height // 2 - 3
    start_x = (width - box_width) // 2
    
    safe_addstr(stdscr, start_y, start_x, "+-- [ Error ] ".ljust(box_width-1, "-") + "+", COLOR_ERROR)
    safe_addstr(stdscr, start_y+1, start_x, "|".ljust(box_width-1, " ") + "|", COLOR_ERROR)
    safe_addstr(stdscr, start_y+2, start_x, f"|  {message}".ljust(box_width-1, " ") + "|", COLOR_ERROR, curses.A_BOLD)
    safe_addstr(stdscr, start_y+3, start_x, "|  > Press any key to return...".ljust(box_width-1, " ") + "|", COLOR_DIM)
    safe_addstr(stdscr, start_y+4, start_x, "|".ljust(box_width-1, " ") + "|", COLOR_ERROR)
    safe_addstr(stdscr, start_y+5, start_x, "+".ljust(box_width-1, "-") + "+", COLOR_ERROR)
    
    stdscr.refresh()
    stdscr.getch()

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
        "    Folder where courses will be saved."
    ]
    
    safe_addstr(stdscr, 0, 0, "+-- Help Menu ".ljust(width-1, "-") + "+", COLOR_ACCENT)
    for y in range(1, height-3):
        text = lines[y-1] if y-1 < len(lines) else ""
        safe_addstr(stdscr, y, 0, f"| {text}".ljust(width-1, " ") + "|", COLOR_DEFAULT)
        
    safe_addstr(stdscr, height-3, 0, "+".ljust(width-1, "-") + "+", COLOR_ACCENT)
    safe_addstr(stdscr, height-2, 0, "| > Press any key to close".ljust(width-1, " ") + "|", COLOR_DIM)
    safe_addstr(stdscr, height-1, 0, "+".ljust(width-1, "-") + "+", COLOR_ACCENT)
    
    stdscr.refresh()
    stdscr.getch()

def edit_settings(stdscr, config):
    """Simple UI for modifying configuration values."""
    curses.curs_set(0)
    keys = list(config.keys())
    selected_idx = 0
    
    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        safe_addstr(stdscr, 0, 0, "+-- Settings ".ljust(width-1, "-") + "+", COLOR_ACCENT)
        
        for i, key in enumerate(keys):
            prefix = ">" if i == selected_idx else " "
            color = COLOR_SUCCESS if i == selected_idx else COLOR_DIM
            val = str(config[key])
            if len(val) > width - 25: 
                val = val[:width-28] + "..."
                
            safe_addstr(stdscr, i + 2, 0, f"| {prefix} {key:<10} : {val}", color, 0, width-2)
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
        elif ch == 10: # Enter key
            curses.curs_set(1)
            curses.echo()
            prompt = f"| New {keys[selected_idx]} (Leave blank to cancel): "
            safe_addstr(stdscr, height-3, 0, prompt.ljust(width-1, " ")[:width-2] + "|", COLOR_WARN)
            
            # Get user input
            new_val = stdscr.getstr(height-3, len(prompt), 100).decode().strip()
            if new_val:
                config[keys[selected_idx]] = new_val
                Path(CONFIG_FILE).write_text(json.dumps(config, indent=4))
                
            curses.noecho()
            curses.curs_set(0)

def main_menu(stdscr, config):
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
        elif ch == 10: # Enter key
            if selected_idx == 0: return True
            elif selected_idx == 1: edit_settings(stdscr, config)
            elif selected_idx == 2: show_help(stdscr)
            elif selected_idx == 3: return False

def fetch_owned_courses(stdscr, session, api_base):
    """Pulls the user's library of courses from the Udemy API."""
    stdscr.clear()
    height, width = stdscr.getmaxyx()
    safe_addstr(stdscr, height//2, (width-40)//2, "Fetching your courses...", COLOR_ACCENT, curses.A_BLINK)
    stdscr.refresh()
    
    url = f"{api_base}/api-2.0/users/me/subscribed-courses/?page_size=100"
    courses = []
    
    while url:
        try:
            response = session.get(url).json()
            for item in response.get("results", []):
                courses.append({"id": item["id"], "title": item["title"]})
            # Udemy uses cursor-based pagination
            url = response.get("next")
        except Exception:
            break
            
    return courses

def select_courses(stdscr, courses):
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
            
            safe_addstr(stdscr, i + 3, 0, f"| {prefix} {box} {course['id']:<10} {course['title']}", color, 0, width - 2)
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
        elif k == 10: # Enter
            # If nothing checked, just download the one they are highlighting
            if not selected and len(courses) > 0:
                selected.add(selected_idx)
            break
            
    return [courses[i] for i in sorted(list(selected))]

def main(stdscr):
    init_colors()
    curses.curs_set(0)
    
    # Check dependencies before doing anything
    if not shutil.which("ffmpeg"):
        show_error(stdscr, "ffmpeg is not installed or not in PATH. Please install it to download videos.")
        return

    # Load Config
    config = {
        "domain": "https://www.udemy.com", 
        "token": "", 
        "client_id": "", 
        "dl_path": "downloads"
    }
    
    if Path(CONFIG_FILE).exists():
        try:
            saved = json.loads(Path(CONFIG_FILE).read_text())
            config.update({k: saved[k] for k in config if k in saved})
        except Exception:
            pass
            
    # Force setup if token is missing
    if not config["token"]:
        edit_settings(stdscr, config)
    
    while True:
        if not main_menu(stdscr, config):
            break

        # Setup HTTP Client
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {config['token']}", 
            "User-Agent": USER_AGENT, 
            "Origin": config["domain"], 
            "Referer": f"{config['domain']}/"
        })
        session.cookies.update({
            "access_token": config["token"], 
            "client_id": config["client_id"]
        })

        all_courses = fetch_owned_courses(stdscr, session, config["domain"])
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
            # Sanitize folder name
            folder_name = re.sub(r'[<>:"/\\|?*]', '-', course['title']).strip()
            base_dir = Path(config["dl_path"]) / folder_name
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
                    color = COLOR_ERROR if "Error" in line else (COLOR_SUCCESS if "Done" in line or "OK" in line else COLOR_DIM)
                    safe_addstr(stdscr, log_start_y + idx, 2, f"> {line}", color, 0, width - 4)

                safe_addstr(stdscr, height-1, 0, "+".ljust(width-1, "-") + "+", COLOR_ACCENT)
                stdscr.refresh()

            def add_log(msg):
                """Helper to append log messages and trigger a UI redraw."""
                ts = datetime.now().strftime("%H:%M:%S")
                log.append(f"[{ts}] {msg}")
                render_ui()

            # -----------------------------------------------------------------
            # Step 1: Map out the course structure (Chapters & Lectures)
            # -----------------------------------------------------------------
            state["current_file"] = "Fetching metadata..."
            add_log(f"[INFO] Analyzing course ID: {course['id']}...")
            
            # API endpoint to get all course items
            url = f"{config['domain']}/api-2.0/courses/{course['id']}/subscriber-curriculum-items/?page=1&page_size=100&fields[lecture]=title,asset&fields[chapter]=title&fields[asset]=stream_urls,hls_url"
            
            download_queue = []
            chapter_index = 0
            lecture_index = 0
            current_chapter_dir = base_dir
            
            while url:
                try: 
                    data = session.get(url).json()
                except Exception as e: 
                    add_log(f"[ERROR] Connection issue: {e}")
                    break

                for item in data.get("results", []):
                    item_type = item.get("_class")
                    clean_title = re.sub(r'[<>:"/\\|?*]', '-', str(item.get("title") or "Unknown")).strip()
                    
                    if item_type == "chapter":
                        # Create a new folder for the chapter
                        chapter_index += 1
                        lecture_index = 0
                        current_chapter_dir = base_dir / f"{chapter_index:02d} - {clean_title}"
                        download_queue.append({"type": "folder", "path": current_chapter_dir, "title": clean_title})
                        
                    elif item_type == "lecture" and "asset" in item:
                        # Queue the video inside the current chapter folder
                        lecture_index += 1
                        video_url = get_highest_quality_video_url(item.get("asset"))
                        if video_url:
                            file_path = current_chapter_dir / f"{lecture_index:03d} - {clean_title}.mp4"
                            download_queue.append({"type": "video", "title": clean_title, "url": video_url, "path": file_path})
                            state["total_vids"] += 1
                            
                url = data.get("next")
                render_ui()

            add_log(f"[INFO] Found {state['total_vids']} videos to download.")

            # -----------------------------------------------------------------
            # Step 2: Download the queued items via FFmpeg
            # -----------------------------------------------------------------
            for item in download_queue:
                if item["type"] == "folder":
                    item["path"].mkdir(parents=True, exist_ok=True)
                    add_log(f"[SYS] Created folder: {item['path'].name}")
                    
                elif item["type"] == "video":
                    state["current_file"] = item["title"]
                    out_path = item["path"]
                    
                    # Check if file already exists and has a reasonable file size (>1KB)
                    if out_path.exists() and out_path.stat().st_size > 1024:
                        size_mb = out_path.stat().st_size / (1024 * 1024)
                        add_log(f"[CACHE] Skipping existing file: {item['title'][:20]}... ({size_mb:.1f}MB)")
                        state["done_vids"] += 1
                        continue

                    add_log(f"[DOWNLOAD] Starting: {item['title'][:30]}...")
                    
                    # FFmpeg needs the authentication headers to pull the HLS stream
                    headers = f"Authorization: Bearer {config['token']}\r\nOrigin: {config['domain']}\r\nReferer: {config['domain']}/\r\n"
                    cmd = ["ffmpeg", "-y", "-headers", headers, "-i", item["url"], "-c", "copy", "-bsf:a", "aac_adtstoasc", str(out_path)]
                    
                    # Run FFmpeg and hide standard output, but capture stderr to parse progress
                    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL)
                    
                    # Reset stats for the new video
                    state.update({
                        "ff_time": "00:00:00", "ff_size": "0kb", "ff_speed": "0.0x", 
                        "vid_duration_secs": 0, "vid_current_secs": 0, "vid_duration_str": "??:??:??"
                    })
                    
                    # Read FFmpeg's terminal output in real-time
                    for line in read_ffmpeg_output(proc):
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
                    
                    proc.wait()
                    state["done_vids"] += 1
                    add_log(f"[DONE] Finished {state['ff_size']} file.")
                    render_ui()

        # All selected courses are done
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        safe_addstr(stdscr, height // 2, (width - 40) // 2, "All downloads completed successfully!", COLOR_SUCCESS, curses.A_BOLD)
        safe_addstr(stdscr, height // 2 + 1, (width - 40) // 2, "[ Press any key to return to menu ]", COLOR_DIM)
        stdscr.refresh()
        stdscr.getch()

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        # User pressed Ctrl+C, just exit cleanly
        pass
