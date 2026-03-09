from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any, Callable

import requests

from .config import QUALITY_OPTIONS, Config
from .utils import get_logger, sanitize_filename

logger = get_logger(__name__)

FFMPEG_TIMEOUT = 600
CHUNK_SIZE = 8192
DIRECT_DOWNLOAD_MIN_SIZE = 500
VIDEO_MIN_SIZE = 1024


def _webvtt_to_srt(content: str) -> str:
    if not content.strip().startswith("WEBVTT"):
        return content

    lines = content.split("\n")
    cue_lines: list[str] = []
    in_header = True
    for line in lines:
        if in_header:
            if "-->" in line:
                in_header = False
                cue_lines.append(line)
        else:
            cue_lines.append(line)

    srt_blocks: list[str] = []
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
    def __init__(self, config: Config, session: requests.Session) -> None:
        self.config = config
        self.session = session

    def _build_headers_content(self) -> str:
        return (
            f"Authorization: Bearer {self.config.token}\r\n"
            f"Origin: {self.config.domain}\r\n"
            f"Referer: {self.config.domain}/\r\n"
        )

    @staticmethod
    def get_asset_download_url(asset_data: dict[str, Any] | None) -> str:
        if not asset_data:
            return ""
        download_urls = asset_data.get("download_urls") or {}
        file_list = download_urls.get("File") or []
        if file_list:
            file_val = file_list[0].get("file")
            return str(file_val) if file_val is not None else ""
        file_val = asset_data.get("file")
        return str(file_val) if file_val is not None else ""

    def get_quality_video_url(self, asset_data: dict[str, Any] | None) -> str:
        if not asset_data:
            return ""

        try:
            pref_index = QUALITY_OPTIONS.index(self.config.quality)
        except ValueError:
            pref_index = 2

        stream_urls = asset_data.get("stream_urls") or {}
        videos = stream_urls.get("Video", [])

        for i in range(pref_index, len(QUALITY_OPTIONS)):
            for v in videos:
                if v.get("label") == QUALITY_OPTIONS[i]:
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
            yield from self._read_ffmpeg_output_win32(proc)
            return

        import select

        buffer = ""
        while True:
            if proc.stderr is None:
                break
            ready, _, _ = select.select([proc.stderr], [], [], 0.1)
            if not ready:
                if proc.poll() is not None:
                    break
                continue

            try:
                chunk = os.read(proc.stderr.fileno(), 1024)
            except (OSError, ValueError):
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

    @staticmethod
    def _read_ffmpeg_output_win32(proc: subprocess.Popen) -> Generator[str, None, None]:
        import queue
        import threading

        q: queue.Queue = queue.Queue()

        def reader() -> None:
            try:
                while True:
                    if proc.stderr is None:
                        break
                    chunk = proc.stderr.read(1024)
                    if not chunk:
                        break
                    q.put(chunk)
            except (OSError, ValueError):
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

    def download_video(self, url: str, output_path: Path) -> subprocess.Popen:
        headers_content = self._build_headers_content()

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

    def wait_for_download(self, proc: subprocess.Popen, timeout: int = FFMPEG_TIMEOUT) -> int:
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg process timed out after {timeout}s, killing")
            proc.kill()
            proc.wait(timeout=10)
        return proc.returncode if proc.returncode is not None else -1

    def download_file(
        self,
        url: str,
        output_path: Path,
        is_interrupted: Callable | None = None,
    ) -> bool:
        try:
            response = self.session.get(url, timeout=60, stream=True)
            if response.status_code in (401, 403):
                response.close()
                clean_headers = {
                    k: v for k, v in self.session.headers.items() if k.lower() != "authorization"
                }
                response = requests.get(url, timeout=60, stream=True, headers=clean_headers)
            response.raise_for_status()

            with output_path.open("wb") as f:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if is_interrupted and is_interrupted():
                        f.close()
                        if output_path.exists():
                            output_path.unlink()
                        return False
                    if chunk:
                        f.write(chunk)

            return output_path.exists() and output_path.stat().st_size > 0
        except (requests.RequestException, OSError) as e:
            logger.error(f"Failed to download file asset: {e}")
            if output_path.exists():
                with contextlib.suppress(OSError):
                    output_path.unlink()
            return False

    def download_subtitles(self, course_id: int, lecture_id: int, output_path: Path) -> list[Path]:
        downloaded: list[Path] = []
        try:
            url = (
                f"{self.config.domain}/api-2.0/courses/{course_id}"
                f"/lectures/{lecture_id}/subtitles"
            )
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            subtitles_dir = output_path.parent
            for caption in data.get("captions", []):
                lang = sanitize_filename(caption.get("language", "en"))
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
                    except (requests.RequestException, OSError) as e:
                        logger.warning(f"Failed to download subtitle {lang}: {e}")
        except (requests.RequestException, OSError, ValueError) as e:
            logger.warning(f"Failed to fetch subtitles for lecture {lecture_id}: {e}")
        return downloaded

    def download_materials(
        self,
        course_id: int,
        lecture_id: int,
        output_path: Path,
        is_interrupted: Callable | None = None,
    ) -> list[Path]:
        downloaded: list[Path] = []
        try:
            url = (
                f"{self.config.domain}/api-2.0/courses/{course_id}"
                f"/lectures/{lecture_id}/supplementary-assets"
            )
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
                    if mat_response.status_code in (401, 403):
                        mat_response.close()
                        clean_headers = {
                            k: v
                            for k, v in self.session.headers.items()
                            if k.lower() != "authorization"
                        }
                        mat_response = requests.get(
                            file_url, timeout=30, stream=True, headers=clean_headers
                        )
                    mat_response.raise_for_status()
                    mat_path = materials_dir / filename
                    with mat_path.open("wb") as f:
                        for chunk in mat_response.iter_content(chunk_size=CHUNK_SIZE):
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
                except (requests.RequestException, OSError) as e:
                    logger.warning(f"Failed to download material {filename}: {e}")
        except (requests.RequestException, OSError, ValueError) as e:
            logger.warning(f"Failed to fetch materials for lecture {lecture_id}: {e}")
        return downloaded
