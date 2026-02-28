import subprocess
import select
import requests
from pathlib import Path
from typing import List, Optional, Generator, Dict, Any

from .config import Config
from .utils import get_logger, sanitize_filename

logger = get_logger(__name__)


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
        while True:
            ready, _, _ = select.select([proc.stderr], [], [], 0.1)
            if ready:
                line = proc.stderr.readline()
                if line:
                    yield line.decode("utf-8", "ignore").strip().lower()
            if proc.poll() is not None:
                remaining = proc.stderr.read()
                if remaining:
                    yield remaining.decode("utf-8", "ignore").strip().lower()
                break

    def download_video(self, url: str, output_path: Path) -> subprocess.Popen:
        headers = (
            f"Authorization: Bearer {self.config.token}\\r\n"
            f"Origin: {self.config.domain}\\r\n"
            f"Referer: {self.config.domain}/\\r\n"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-headers",
            headers,
            "-i",
            url,
            "-c",
            "copy",
            "-bsf:a",
            "aac_adtstoasc",
            str(output_path),
        ]
        return subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL)

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
                        sub_response = requests.get(srt_url, timeout=30, stream=True)
                        sub_response.raise_for_status()
                        content = sub_response.text
                        if content.startswith("WEBVTT"):
                            content = content.replace("WEBVTT", "").strip()
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
                    if mat_response.status_code in [401, 403]:
                        mat_response = requests.get(file_url, timeout=30, stream=True)
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
