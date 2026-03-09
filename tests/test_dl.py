from unittest.mock import MagicMock, patch

import requests

from udemy_dl.config import Config
from udemy_dl.dl import VideoDownloader, _webvtt_to_srt


class TestWebvttToSrt:
    def test_basic_conversion(self):
        webvtt = (
            "WEBVTT\n\n"
            "00:00:01.000 --> 00:00:04.000\n"
            "Hello world\n\n"
            "00:00:05.000 --> 00:00:08.000\n"
            "Second line\n"
        )
        result = _webvtt_to_srt(webvtt)
        assert "1\n" in result
        assert "00:00:01,000 --> 00:00:04,000" in result
        assert "Hello world" in result
        assert "2\n" in result
        assert "00:00:05,000 --> 00:00:08,000" in result
        assert "Second line" in result

    def test_non_webvtt_passthrough(self):
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHello\n\n"
        result = _webvtt_to_srt(srt)
        assert result == srt

    def test_strips_html_tags(self):
        webvtt = "WEBVTT\n\n" "00:00:01.000 --> 00:00:04.000\n" "<b>Bold text</b>\n"
        result = _webvtt_to_srt(webvtt)
        assert "<b>" not in result
        assert "Bold text" in result

    def test_short_timestamp_padded(self):
        webvtt = "WEBVTT\n\n" "01:00.000 --> 02:00.000\n" "Short timestamp\n"
        result = _webvtt_to_srt(webvtt)
        assert "00:01:00,000 --> 00:02:00,000" in result

    def test_empty_webvtt(self):
        webvtt = "WEBVTT\n\n"
        result = _webvtt_to_srt(webvtt)
        assert isinstance(result, str)

    def test_dot_to_comma_conversion(self):
        webvtt = "WEBVTT\n\n" "00:00:01.500 --> 00:00:04.750\n" "Test\n"
        result = _webvtt_to_srt(webvtt)
        assert "00:00:01,500 --> 00:00:04,750" in result


class TestGetQualityVideoUrl:
    def _make_downloader(self, quality: str = "1080") -> VideoDownloader:
        cfg = Config(
            token="t" * 20,
            client_id="c" * 10,
            quality=quality,
        )
        import requests

        session = requests.Session()
        return VideoDownloader(cfg, session)

    def _make_asset(self, labels: list) -> dict:
        return {
            "stream_urls": {
                "Video": [
                    {"label": lbl, "file": f"http://example.com/{lbl }.mp4"} for lbl in labels
                ]
            }
        }

    def test_exact_quality_match(self):
        dl = self._make_downloader("720")
        asset = self._make_asset(["1080", "720", "480"])
        url = dl.get_quality_video_url(asset)
        assert "720" in url

    def test_fallback_to_lower_quality(self):
        dl = self._make_downloader("1080")
        asset = self._make_asset(["720", "480"])
        url = dl.get_quality_video_url(asset)
        assert url != ""

    def test_empty_asset_returns_empty(self):
        dl = self._make_downloader()
        assert dl.get_quality_video_url(None) == ""
        assert dl.get_quality_video_url({}) == ""

    def test_hls_fallback(self):
        dl = self._make_downloader("1080")
        asset = {"hls_url": "http://example.com/stream.m3u8", "stream_urls": {}}
        url = dl.get_quality_video_url(asset)
        assert url == "http://example.com/stream.m3u8"

    def test_no_urls_returns_empty(self):
        dl = self._make_downloader()
        asset = {"stream_urls": {"Video": []}}
        url = dl.get_quality_video_url(asset)
        assert url == ""

    def test_prefers_exact_over_higher(self):
        dl = self._make_downloader("720")
        asset = self._make_asset(["2160", "1440", "1080", "720", "480"])
        url = dl.get_quality_video_url(asset)
        assert "720" in url

    def test_invalid_quality_falls_back_to_1080_index(self):
        cfg = Config(token="t" * 20, client_id="c" * 10, quality="999")
        import requests

        dl = VideoDownloader(cfg, requests.Session())
        asset = self._make_asset(["1080", "720"])
        url = dl.get_quality_video_url(asset)
        assert "1080" in url


class TestGetAssetDownloadUrl:
    def test_extracts_from_download_urls(self):
        asset = {"download_urls": {"File": [{"file": "http://example.com/doc.pdf"}]}}
        assert VideoDownloader.get_asset_download_url(asset) == "http://example.com/doc.pdf"

    def test_returns_empty_for_none(self):
        assert VideoDownloader.get_asset_download_url(None) == ""

    def test_returns_empty_for_empty_dict(self):
        assert VideoDownloader.get_asset_download_url({}) == ""

    def test_returns_empty_when_no_download_urls(self):
        assert VideoDownloader.get_asset_download_url({"asset_type": "Article"}) == ""

    def test_fallback_to_file_field(self):
        asset = {"file": "http://example.com/fallback.pdf"}
        assert VideoDownloader.get_asset_download_url(asset) == "http://example.com/fallback.pdf"

    def test_none_file_value_returns_empty(self):
        asset = {"download_urls": {"File": [{"file": None}]}}
        assert VideoDownloader.get_asset_download_url(asset) == ""

    def test_none_top_level_file_returns_empty(self):
        asset = {"file": None}
        assert VideoDownloader.get_asset_download_url(asset) == ""

    def test_empty_file_list(self):
        asset = {"download_urls": {"File": []}}
        assert VideoDownloader.get_asset_download_url(asset) == ""

    def test_multiple_files_returns_first(self):
        asset = {
            "download_urls": {
                "File": [
                    {"file": "http://example.com/first.pdf"},
                    {"file": "http://example.com/second.pdf"},
                ]
            }
        }
        assert VideoDownloader.get_asset_download_url(asset) == "http://example.com/first.pdf"


class TestDownloadFile:
    def _make_downloader(self):
        cfg = Config(token="t" * 20, client_id="c" * 10)
        session = requests.Session()
        return VideoDownloader(cfg, session)

    def test_successful_download(self, tmp_path):
        dl = self._make_downloader()
        out = tmp_path / "test.pdf"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content = MagicMock(return_value=[b"PDF content here"])
        mock_resp.raise_for_status = MagicMock()

        with patch.object(dl.session, "get", return_value=mock_resp):
            result = dl.download_file("http://example.com/f.pdf", out)

        assert result is True
        assert out.exists()
        assert out.read_bytes() == b"PDF content here"

    def test_interrupted_download_cleans_up(self, tmp_path):
        dl = self._make_downloader()
        out = tmp_path / "test.pdf"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content = MagicMock(return_value=[b"partial"])
        mock_resp.raise_for_status = MagicMock()

        with patch.object(dl.session, "get", return_value=mock_resp):
            result = dl.download_file("http://example.com/f.pdf", out, is_interrupted=lambda: True)

        assert result is False

    def test_auth_retry_on_403(self, tmp_path):
        dl = self._make_downloader()
        out = tmp_path / "test.pdf"

        forbidden_resp = MagicMock()
        forbidden_resp.status_code = 403
        forbidden_resp.close = MagicMock()

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.iter_content = MagicMock(return_value=[b"ok"])
        success_resp.raise_for_status = MagicMock()

        with patch.object(dl.session, "get", return_value=forbidden_resp), patch(
            "udemy_dl.dl.requests.get", return_value=success_resp
        ):
            result = dl.download_file("http://example.com/f.pdf", out)

        assert result is True

    def test_network_error_returns_false(self, tmp_path):
        dl = self._make_downloader()
        out = tmp_path / "test.pdf"

        with patch.object(dl.session, "get", side_effect=requests.ConnectionError("fail")):
            result = dl.download_file("http://example.com/f.pdf", out)

        assert result is False
        assert not out.exists()


class TestDownloadVideo:
    def _make_downloader(self):
        cfg = Config(token="t" * 20, client_id="c" * 10)
        session = requests.Session()
        return VideoDownloader(cfg, session)

    def test_spawns_ffmpeg_process(self):
        dl = self._make_downloader()

        proc = dl.download_video("http://example.com/video.m3u8", MagicMock())

        assert proc is not None
        proc.kill()
        proc.wait()

    def test_builds_correct_command(self):
        dl = self._make_downloader()

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.stderr = MagicMock()
            mock_popen.return_value = mock_proc

            output_path = MagicMock()
            output_path.__str__ = lambda self: "/tmp/output.mp4"

            dl.download_video("http://example.com/video.m3u8", output_path)

            cmd = mock_popen.call_args[0][0]

            assert "ffmpeg" in cmd
            assert "-i" in cmd
            assert "http://example.com/video.m3u8" in cmd


class TestWaitForDownload:
    def _make_downloader(self):
        cfg = Config(token="t" * 20, client_id="c" * 10)
        session = requests.Session()
        return VideoDownloader(cfg, session)

    def test_returns_exit_code_on_normal_exit(self):
        dl = self._make_downloader()

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        result = dl.wait_for_download(mock_proc, timeout=1)

        assert result == 0

    def test_returns_minus_one_when_no_exit_code(self):
        dl = self._make_downloader()

        mock_proc = MagicMock()
        mock_proc.returncode = None

        result = dl.wait_for_download(mock_proc, timeout=1)

        assert result == -1

    def test_kills_process_on_timeout(self):
        dl = self._make_downloader()

        mock_proc = MagicMock()
        import subprocess

        mock_proc.wait.side_effect = subprocess.TimeoutExpired("cmd", 1)
        mock_proc.kill = MagicMock()

        dl.wait_for_download(mock_proc, timeout=1)

        mock_proc.kill.assert_called_once()
        mock_proc.wait.assert_called()


class TestReadFfmpegOutput:
    def test_reads_stderr_output(self):
        cfg = Config(token="t" * 20, client_id="c" * 10)
        session = requests.Session()
        dl = VideoDownloader(cfg, session)

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0

        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_proc.stderr = mock_stderr

        lines = list(dl.read_ffmpeg_output(mock_proc))

        assert isinstance(lines, list)
