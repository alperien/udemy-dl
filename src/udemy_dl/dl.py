import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import requests

from .config import Config
from .utils import get_logger, sanitize_filename

logger = get_logger(__name__)


def _webvtt_to_srt(content: str) -> str:
    """Convert WebVTT subtitle content to SRT format."""
    if not content.startswith("WEBVTT"):
        return content

    # Strip the WEBVTT header and any metadata lines before first cue
    lines = content.split("\n")
    cue_lines: List[str] = []
    in_header = True
    for line in lines:
        if in_header:
            # Skip until we find the first timestamp line
            if "-->" in line:
                in_header = False
                cue_lines.append(line)
        else:
            cue_lines.append(line)

    # Parse cues and rebuild as SRT
    srt_blocks: List[str] = []
    cue_index = 0
    i = 0
    raw_lines = cue_lines

    while i < len(raw_lines):
        line = raw_lines[i].strip()
        if "-->" in line:
            cue_index += 1
            # Convert WebVTT timestamp separators: '.' → ','
            # Also strip any positioning metadata after the timestamp
            timestamp_match = re.match(
                r"([\d:.]+)\s*-->\s*([\d:.]+)", line
            )
            if timestamp_match:
                start = timestamp_match.group(1).replace(".", ",")
                end = timestamp_match.group(2).replace(".", ",")
                # Ensure HH:MM:SS,mmm format
                if start.count(":") == 1:
                    start = "00:" + start
                if end.count(":") == 1:
                    end = "00:" + end
                srt_blocks.append(str(cue_index))
                srt_blocks.append(f"{start} --> {end}")
                i += 1
                # Collect text lines until empty line or next cue
                while i < len(raw_lines):
                    text_line = raw_lines[i]
                    if text_line.strip() == "" or "-->" in text_line:
                        break
                    srt_blocks.append(text_line.rstrip())
                    i += 1
                srt_blocks.append("")  # blank line between cues
            else:
                i += 1  # skip malformed cue line
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
        if hls_url := asset_data.get("hls_url"):
            return hls_url
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
                    return v.get("file", "")
        try:
            best_video = max(videos, key=lambda v: int(v.get("label", "0") or 0))
            return best_video.get("file", "")
        except (ValueError, TypeError):
            return ""

    def read_ffmpeg_output(self, proc: subprocess.Popen) -> Generator[str, None, None]:
        buffer = bytearray()
        while True:
            if sys.platform != "win32":
                import select

                ready, _, _ = select.select([proc.stderr], [], [], 0.1)
                if not ready:
                    if proc.poll() is not None:
                        break
                    continue

            char = proc.stderr.read(1)
            if not char:
                break

            if char in (b"\r", b"\n"):
                if buffer:
                    yield buffer.decode("utf-8", "ignore").strip().lower()
                    buffer.clear()
            else:
                buffer.extend(char)

        if buffer:
            yield buffer.decode("utf-8", "ignore").strip().lower()

    def download_video(self, url: str, output_path: Path) -> subprocess.Popen:
        headers_content = (
            f"Authorization: Bearer {self.config.token}\r\n"
            f"Origin: {self.config.domain}\r\n"
            f"Referer: {self.config.domain}/\r\n"
        )

        # Avoid leaking the auth token in the process argument list (visible
        # via ``ps aux`` or /proc/PID/cmdline).  On POSIX we pass the headers
        # through an environment variable and expand it inside a shell wrapper
        # so only ``$_UDEMY_HEADERS`` appears in argv.  The environment is
        # protected by the OS — only the same uid (or root) can read
        # /proc/PID/environ.  On Windows, fall back to direct CLI args since
        # the security model differs.
        env = {**os.environ, "_UDEMY_HEADERS": headers_content}

        if sys.platform == "win32":
            cmd = [
                "ffmpeg", "-y",
                "-headers", headers_content,
                "-i", url,
                "-c", "copy",
                "-bsf:a", "aac_adtstoasc",
                str(output_path),
            ]
            return subprocess.Popen(
                cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, env=env,
            )

        # POSIX: use shell expansion so the token stays out of argv
        cmd = [
            "sh", "-c",
            'exec ffmpeg -y -headers "$_UDEMY_HEADERS" '
            '-i "$1" -c copy -bsf:a aac_adtstoasc "$2"',
            "_",  # $0 placeholder
            url,
            str(output_path),
        ]
        return subprocess.Popen(
            cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, env=env,
        )

    def download_subtitles(
        self, course_id: int, lecture_id: int, output_path: Path
    ) -> List[Path]:
        downloaded = []
        try:
            url = f"{self.config.domain}/api-2.0/courses/{course_id}/lectures/{lecture_id}/subtitles"
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
                        if content.startswith("WEBVTT"):
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
        self, course_id: int, lecture_id: int, output_path: Path
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
                file_url = asset.get("file_url")
                filename = sanitize_filename(asset.get("filename", "unknown"))
                if not file_url:
                    continue
                try:
                    mat_response = self.session.get(file_url, timeout=30, stream=True)
                    # Retry logic for auth failures - try different approaches
                    retry_count = 0
                    max_retries = 2
                    while mat_response.status_code in [401, 403] and retry_count < max_retries:
                        retry_count += 1
                        if retry_count == 1:
                            # First retry: try unauthenticated request
                            mat_response = requests.get(file_url, timeout=30, stream=True)
                        # else: max retries reached, will raise on raise_for_status()
                    mat_response.raise_for_status()
                    mat_path = materials_dir / filename
                    with open(mat_path, "wb") as f:
                        for chunk in mat_response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    if mat_path.exists() and mat_path.stat().st_size > 0:
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
