import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional

import requests

from .config import Config
from .utils import get_logger, sanitize_filename

logger = get_logger(__name__)


def _webvtt_to_srt(content: str) -> str:
    if not content.strip().startswith("WEBVTT"):
        return content

    lines = content.split("\n")
    cue_lines: List[str] = []
    in_header = True
    for line in lines:
        if in_header:
            if "-->" in line:
                in_header = False
                cue_lines.append(line)
        else:
            cue_lines.append(line)

    srt_blocks: List[str] = []
    cue_index = 0
    i = 0
    raw_lines = cue_lines

    while i < len(raw_lines):
        line = raw_lines[i].strip()
        if "-->" in line:
            cue_index += 1
            timestamp_match = re.match(r"([\d:.]+)\s*-->\s*([\d:.]+)", line)
            if timestamp_match:
                start = timestamp_match.group(1).replace(".", ",")
                end = timestamp_match.group(2).replace(".", ",")
                if start.count(":") == 1:
                    start = "00:" + start
                if end.count(":") == 1:
                    end = "00:" + end
                srt_blocks.append(str(cue_index))
                srt_blocks.append(f"{start} --> {end}")
                i += 1
                while i < len(raw_lines):
                    text_line = raw_lines[i]
                    if text_line.strip() == "" or "-->" in text_line:
                        break
                    text_line = re.sub(r"<[^>]+>", "", text_line)
                    srt_blocks.append(text_line.rstrip())
                    i += 1
                srt_blocks.append("")
            else:
                i += 1
        else:
            i += 1

    return "\n".join(srt_blocks).strip() + "\n"


class VideoDownloader:
    def __init__(self, config: Config, session: requests.Session):
        self.config = config
        self.session = session

    def get_quality_video_url(self, asset_data: Optional[Dict[str, Any]]) -> str:
        if not asset_data:
            return ""
        quality_options = ["2160", "1440", "1080", "720", "480", "360"]
        try:
            pref_index = quality_options.index(self.config.quality)
        except ValueError:
            pref_index = 2
        stream_urls = asset_data.get("stream_urls") or {}
        videos = stream_urls.get("Video", [])
        for i in range(pref_index, len(quality_options)):
            for v in videos:
                if v.get("label") == quality_options[i]:
                    return str(v.get("file", ""))
        try:
            if videos:
                best_video = max(videos, key=lambda v: int(v.get("label", "0") or 0))
                return str(best_video.get("file", ""))
        except (ValueError, TypeError):
            pass

        if hls_url := asset_data.get("hls_url"):
            return str(hls_url) if hls_url else ""

        return ""

    def read_ffmpeg_output(self, proc: subprocess.Popen) -> Generator[str, None, None]:
        if sys.platform == "win32":
            import queue
            import threading

            q = queue.Queue()

            def reader():
                try:
                    while True:
                        if proc.stderr is None:
                            break
                        chunk = proc.stderr.read1(1024)
                        if not chunk:
                            break
                        q.put(chunk)
                except Exception:
                    pass
                finally:
                    q.put(None)

            t = threading.Thread(target=reader, daemon=True)
            t.start()

            buffer = ""
            while True:
                try:
                    chunk = q.get(timeout=0.1)
                    if chunk is None:
                        break
                    buffer += chunk.decode("utf-8", "ignore")
                    parts = re.split(r"[\r\n]+", buffer)
                    buffer = parts.pop()
                    for line in parts:
                        if line.strip():
                            yield line.strip().lower()
                except queue.Empty:
                    if proc.poll() is not None:
                        break

            if buffer.strip():
                yield buffer.strip().lower()
            return

        buffer = ""
        while True:
            import select

            if proc.stderr is None:
                break
            ready, _, _ = select.select([proc.stderr], [], [], 0.1)
            if not ready:
                if proc.poll() is not None:
                    break
                continue

            import os

            try:
                chunk = os.read(proc.stderr.fileno(), 1024)
            except Exception:
                break

            if not chunk:
                if proc.poll() is not None:
                    break
                continue

            buffer += chunk.decode("utf-8", "ignore")
            parts = re.split(r"[\r\n]+", buffer)
            buffer = parts.pop()
            for line in parts:
                if line.strip():
                    yield line.strip().lower()

        if buffer.strip():
            yield buffer.strip().lower()

    def download_video(self, url: str, output_path: Path) -> subprocess.Popen:
        headers_content = (
            f"Authorization: Bearer {self.config.token}\r\n"
            f"Origin: {self.config.domain}\r\n"
            f"Referer: {self.config.domain}/\r\n"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-headers",
            headers_content,
            "-i",
            url,
            "-c",
            "copy",
            "-bsf:a",
            "aac_adtstoasc",
            str(output_path),
        ]

        return subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
        )

    def download_subtitles(self, course_id: int, lecture_id: int, output_path: Path) -> List[Path]:
        downloaded = []
        try:
            url = (
                f"{self.config.domain}/api-2.0/courses/{course_id}/lectures/{lecture_id}/subtitles"
            )
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            subtitles_dir = output_path.parent
            for caption in data.get("captions", []):
                lang = caption.get("language", "en")
                srt_url = caption.get("url")
                if srt_url:
                    srt_path = subtitles_dir / f"{output_path.stem}.{lang}.srt"
                    try:
                        sub_response = self.session.get(srt_url, timeout=30)
                        sub_response.raise_for_status()
                        content = sub_response.text
                        if content.strip().startswith("WEBVTT"):
                            content = _webvtt_to_srt(content)
                        srt_path.write_text(content, encoding="utf-8")
                        downloaded.append(srt_path)
                        logger.info(f"Downloaded subtitle: {srt_path.name}")
                    except Exception as e:
                        logger.warning(f"Failed to download subtitle {lang}: {e}")
        except Exception as e:
            logger.warning(f"Failed to fetch subtitles for lecture {lecture_id}: {e}")
        return downloaded

    def download_materials(
        self,
        course_id: int,
        lecture_id: int,
        output_path: Path,
        is_interrupted: Optional[Callable] = None,
    ) -> List[Path]:
        downloaded = []
        try:
            url = f"{self.config.domain}/api-2.0/courses/{course_id}/lectures/{lecture_id}/supplementary-assets"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            materials_dir = output_path.parent / "00-materials"
            materials_dir.mkdir(parents=True, exist_ok=True)
            for asset in data.get("results", []):
                if is_interrupted and is_interrupted():
                    break
                file_url = asset.get("file_url")
                filename = sanitize_filename(asset.get("filename", "unknown"))
                if not file_url:
                    continue
                try:
                    mat_response = self.session.get(file_url, timeout=30, stream=True)
                    if mat_response.status_code in [401, 403]:
                        mat_response = requests.get(file_url, timeout=30, stream=True)
                    mat_response.raise_for_status()
                    mat_path = materials_dir / filename
                    with open(mat_path, "wb") as f:
                        for chunk in mat_response.iter_content(chunk_size=8192):
                            if is_interrupted and is_interrupted():
                                break
                            if chunk:
                                f.write(chunk)
                    if is_interrupted and is_interrupted():
                        logger.warning(f"Material download interrupted: {filename}")
                        if mat_path.exists():
                            mat_path.unlink()
                    elif mat_path.exists() and mat_path.stat().st_size > 0:
                        downloaded.append(mat_path)
                        logger.info(f"Downloaded material: {filename}")
                    else:
                        logger.warning(f"Material file empty: {filename}")
                        if mat_path.exists():
                            mat_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to download material {filename}: {e}")
        except Exception as e:
            logger.warning(f"Failed to fetch materials for lecture {lecture_id}: {e}")
        return downloaded
