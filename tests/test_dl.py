"""Tests for udemy_dl.dl module."""


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
        # Should return something without crashing
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
                "Video": [{"label": lbl, "file": f"http://example.com/{lbl}.mp4"} for lbl in labels]
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
        # Should fall back to best available (720)
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
        # pref_index defaults to 2 (1080) when quality not in list
        cfg = Config(token="t" * 20, client_id="c" * 10, quality="999")
        import requests

        dl = VideoDownloader(cfg, requests.Session())
        asset = self._make_asset(["1080", "720"])
        url = dl.get_quality_video_url(asset)
        assert "1080" in url
