import json
import os
from unittest.mock import patch

from udemy_dl.config import Config, load_config, save_config


class TestConfigValidate:
    def test_valid_config(self):
        cfg = Config(token="a" * 20, client_id="b" * 10, domain="https://www.udemy.com")
        ok, msg = cfg.validate()
        assert ok is True
        assert msg == ""

    def test_missing_token(self):
        cfg = Config(token="", client_id="b" * 10)
        ok, msg = cfg.validate()
        assert ok is False
        assert "token" in msg.lower()

    def test_short_token(self):
        cfg = Config(token="abc", client_id="b" * 10)
        ok, msg = cfg.validate()
        assert ok is False

    def test_missing_client_id(self):
        cfg = Config(token="a" * 20, client_id="")
        ok, msg = cfg.validate()
        assert ok is False
        assert "client_id" in msg.lower()

    def test_short_client_id(self):
        cfg = Config(token="a" * 20, client_id="ab")
        ok, msg = cfg.validate()
        assert ok is False

    def test_invalid_domain(self):
        cfg = Config(token="a" * 20, client_id="b" * 10, domain="not-a-url")
        ok, msg = cfg.validate()
        assert ok is False
        assert "domain" in msg.lower()

    def test_http_domain_rejected(self):
        cfg = Config(token="a" * 20, client_id="b" * 10, domain="http://www.udemy.com")
        ok, msg = cfg.validate()
        assert ok is False
        assert "https" in msg.lower()

    def test_invalid_quality(self):
        cfg = Config(token="a" * 20, client_id="b" * 10, quality="999")
        ok, msg = cfg.validate()
        assert ok is False
        assert "quality" in msg.lower()

    def test_valid_quality_options(self):
        for q in ["2160", "1440", "1080", "720", "480", "360"]:
            cfg = Config(token="a" * 20, client_id="b" * 10, quality=q)
            ok, _ = cfg.validate()
            assert ok is True, f"Quality {q } should be valid"


class TestConfigSaveLoad:
    def test_save_and_load_roundtrip(self, tmp_path):
        cfg = Config(
            token="mytoken12345",
            client_id="myclientid",
            dl_path=str(tmp_path / "downloads"),
            quality="720",
            download_subtitles=False,
            download_materials=True,
        )
        config_file = tmp_path / "config.json"

        with patch("udemy_dl.config.CONFIG_FILE", str(config_file)):
            result = save_config(cfg)
            assert result is True
            assert config_file.exists()
            data = json.loads(config_file.read_text())
            assert data["token"] == "mytoken12345"
            assert data["quality"] == "720"
            assert data["download_subtitles"] is False

            loaded = load_config()
            assert loaded.token == "mytoken12345"
            assert loaded.client_id == "myclientid"
            assert loaded.quality == "720"
            assert loaded.download_subtitles is False
            assert loaded.download_materials is True

    def test_save_config_returns_true_on_success(self, tmp_path):
        cfg = Config(token="x" * 20, client_id="y" * 10)
        config_file = tmp_path / "config.json"
        with patch("udemy_dl.config.CONFIG_FILE", str(config_file)):
            assert save_config(cfg) is True

    def test_save_config_returns_false_on_failure(self, tmp_path):
        cfg = Config(token="x" * 20, client_id="y" * 10)
        bad_path = "/nonexistent/dir/config.json"
        with patch("udemy_dl.config.CONFIG_FILE", bad_path):
            assert save_config(cfg) is False

    def test_load_config_from_env(self, tmp_path):
        env_vars = {
            "UDEMY_TOKEN": "envtoken12345",
            "UDEMY_CLIENT_ID": "envclientid",
            "UDEMY_QUALITY": "480",
            "UDEMY_DOMAIN": "https://www.udemy.com",
            "UDEMY_DL_PATH": str(tmp_path),
            "UDEMY_DOWNLOAD_SUBTITLES": "false",
            "UDEMY_DOWNLOAD_MATERIALS": "true",
        }
        with patch.dict(os.environ, env_vars), patch(
            "udemy_dl.config.CONFIG_FILE", str(tmp_path / "nonexistent.json")
        ):
            cfg = load_config()
        assert cfg.token == "envtoken12345"
        assert cfg.client_id == "envclientid"
        assert cfg.quality == "480"
        assert cfg.download_subtitles is False
        assert cfg.download_materials is True
