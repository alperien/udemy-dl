import curses
import re
import shutil
import signal
from pathlib import Path
from typing import Dict, List

from .api import UdemyAPI
from .config import load_config
from .dl import VideoDownloader
from .state import AppState, DownloadState
from .tui import TUI
from .utils import get_logger, setup_logging, sanitize_filename, time_string_to_seconds, validate_video

logger = get_logger(__name__)

class Application:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.tui = TUI(stdscr)
        self.config = load_config()
        self.state = AppState()
        self.api = None
        self.downloader = None
        self.log_buffer: List[str] = []
        self.download_interrupted = False

    def add_log(self, msg: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self.log_buffer.append(entry)
        if len(self.log_buffer) > 100:
            self.log_buffer.pop(0)
        logger.info(msg)

    def _setup_signal_handlers(self):
        def handler(sig, frame):
            self.download_interrupted = True
            self.state.interrupted = True
            logger.warning("Download interrupted by user")
            self.state.save_state()
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def run(self):
        setup_logging()
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
            if self.download_interrupted:
                self.add_log("Download interrupted. Returning to menu.")
                self.download_interrupted = False
                self.state.save_state()
            
            if not self.tui.main_menu(self.config):
                break
            
            self._run_download_session()
        
        self.state.clear_state()

    def _run_download_session(self):
        try:
            self.api = UdemyAPI(self.config)
            self.downloader = VideoDownloader(self.config, self.api.session)
        except Exception as e:
            self.tui.show_error(f"Failed to initialize session: {e}")
            return
        
        courses = self.api.fetch_owned_courses()
        if not courses:
            self.tui.show_error("Could not fetch courses. Check your token.")
            return
        
        chosen_courses = self.tui.select_courses(courses)
        if not chosen_courses:
            return
        
        for i, course in enumerate(chosen_courses):
            self._download_course(course, i + 1, len(chosen_courses))
            if self.download_interrupted:
                break
        
        if not self.download_interrupted:
            self.state.clear_state()
            self.stdscr.clear()
            height, width = self.stdscr.getmaxyx()
            self.tui.safe_addstr(height // 2, max(0, (width - 40) // 2), 
                                "All downloads completed successfully!", 3, curses.A_BOLD)
            self.tui.safe_addstr(height // 2 + 1, max(0, (width - 40) // 2),
                                "[ Press any key to return to menu ]", 6)
            self.stdscr.refresh()
            self.stdscr.getch()

    def _download_course(self, course: Dict, index: int, total: int):
        self.state.current_course_state = DownloadState(
            course_id=course['id'],
            course_title=course['title'],
            total_lectures=0
        )
        
        ui_state = {
            "course_title": course['title'],
            "total_vids": 0, "done_vids": 0, "current_file": "Initializing...",
            "vid_duration_secs": 0, "vid_current_secs": 0
        }
        
        curriculum = self.api.get_course_curriculum(course['id'])
        
        download_queue = []
        chapter_index = 0
        lecture_index = 0
        current_chapter_dir = None
        base_dir = Path(self.config.dl_path) / sanitize_filename(course['title'])
        
        for item in curriculum:
            item_type = item.get("_class")
            clean_title = sanitize_filename(str(item.get("title") or "Unknown"))
            
            if item_type == "chapter":
                chapter_index += 1
                lecture_index = 0
                current_chapter_dir = base_dir / f"{chapter_index:02d} - {clean_title}"
            elif item_type == "lecture" and "asset" in item:
                lecture_index += 1
                lecture_id = item.get("id")
                asset = item.get("asset")
                url = self.downloader.get_quality_video_url(asset)
                if url and current_chapter_dir:
                    file_path = current_chapter_dir / f"{lecture_index:03d} - {clean_title}.mp4"
                    download_queue.append({
                        "title": clean_title,
                        "url": url,
                        "id": lecture_id,
                        "path": file_path
                    })
                    ui_state["total_vids"] += 1
                    self.state.current_course_state.total_lectures += 1
        
        saved_state = self.state.load_state()
        completed_lectures = set()
        if saved_state and saved_state.course_id == course['id']:
            completed_lectures = set(saved_state.completed_lectures)
            self.add_log(f"[RESUME] Found {len(completed_lectures)} previously completed lectures")
        
        DURATION_REGEX = re.compile(r"duration:\s*(?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?)")
        STATS_REGEX = re.compile(r"size=\s*(?P<size>\d+[a-z]*)\s+time=(?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?).*?speed=\s*(?P<speed>[\d\.]+x)")
        
        for item in download_queue:
            if self.download_interrupted:
                self.add_log("[WARN] Download interrupted. Saving progress...")
                self.state.save_state()
                break
            
            ui_state["current_file"] = item["title"]
            self.tui.render_dashboard(ui_state, index, total, self.log_buffer)
            
            out_path = item["path"]
            out_path.parent.mkdir(parents=True, exist_ok=True)
            lecture_id = item.get("id")
            
            if lecture_id and lecture_id in completed_lectures:
                self.add_log(f"[CACHE] Skipping completed lecture: {item['title'][:30]}...")
                ui_state["done_vids"] += 1
                self.state.current_course_state.completed_lectures.append(lecture_id)
                continue
            
            if out_path.exists() and out_path.stat().st_size > 1024:
                if validate_video(out_path):
                    size_mb = out_path.stat().st_size / (1024 * 1024)
                    self.add_log(f"[CACHE] Skipping existing file: {item['title'][:20]}... ({size_mb:.1f}MB)")
                    ui_state["done_vids"] += 1
                    if lecture_id:
                        self.state.current_course_state.completed_lectures.append(lecture_id)
                        self.state.save_state()
                    continue
                else:
                    self.add_log(f"[WARN] Invalid file detected, re-downloading: {item['title'][:20]}")
                    out_path.unlink()
            
            self.add_log(f"[DOWNLOAD] Starting: {item['title'][:30]}...")
            proc = self.downloader.download_video(item["url"], out_path)
            
            ui_state["vid_duration_secs"] = 0
            ui_state["vid_current_secs"] = 0
            
            try:
                for line in self.downloader.read_ffmpeg_output(proc):
                    if self.download_interrupted:
                        proc.terminate()
                        self.add_log("[WARN] FFmpeg terminated by user")
                        break
                    if ui_state["vid_duration_secs"] == 0:
                        if match := DURATION_REGEX.search(line):
                            time_val = match.group("time").split(".")[0]
                            ui_state["vid_duration_secs"] = time_string_to_seconds(time_val)
                    if match := STATS_REGEX.search(line):
                        time_val = match.group("time").split(".")[0]
                        ui_state["vid_current_secs"] = time_string_to_seconds(time_val)
                    self.tui.render_dashboard(ui_state, index, total, self.log_buffer)
            except Exception as e:
                logger.error(f"Error reading ffmpeg output: {e}")
            
            proc.wait()
            
            if out_path.exists() and validate_video(out_path):
                ui_state["done_vids"] += 1
                self.add_log(f"[DONE] Finished: {item['title'][:30]}")
                if lecture_id:
                    self.state.current_course_state.completed_lectures.append(lecture_id)
                    self.state.save_state()
                
                if self.config.download_subtitles and lecture_id:
                    subs = self.downloader.download_subtitles(course['id'], lecture_id, out_path)
                    if subs:
                        self.add_log(f"[SUBS] Downloaded {len(subs)} subtitle track(s)")
                
                if self.config.download_materials and lecture_id:
                    mats = self.downloader.download_materials(course['id'], lecture_id, out_path)
                    if mats:
                        self.add_log(f"[MATS] Downloaded {len(mats)} material file(s)")
            else:
                self.add_log(f"[ERROR] Download failed or invalid file: {item['title'][:30]}")
                if out_path.exists():
                    out_path.unlink()
