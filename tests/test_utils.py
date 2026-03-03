"""Tests for utility functions — filename sanitisation, time parsing, validation."""

from unittest.mock import patch

from udemy_dl.utils import (
    ValidationResult,
    sanitize_filename,
    time_string_to_seconds,
    validate_video,
)


class TestSanitizeFilename:
    def test_removes_forbidden_chars(self):
        assert sanitize_filename('file<>:"/\\|?*name') == "file---------name"

    def test_strips_whitespace(self):
        assert sanitize_filename("  hello  ") == "hello"

    def test_empty_string_returns_unknown(self):
        assert sanitize_filename("") == "unknown"

    def test_whitespace_only_returns_unknown(self):
        assert sanitize_filename("   ") == "unknown"

    def test_normal_name_unchanged(self):
        assert sanitize_filename("My Course 101") == "My Course 101"

    def test_unicode_preserved(self):
        result = sanitize_filename("Курс по Python")
        assert result == "Курс по Python"

    def test_colon_replaced(self):
        assert sanitize_filename("Chapter 1: Introduction") == "Chapter 1- Introduction"



    def test_strips_leading_dots(self):
        assert sanitize_filename("..hidden") == "hidden"
        assert sanitize_filename(".env") == "env"

    def test_dots_only_returns_unknown(self):
        assert sanitize_filename("...") == "unknown"

    def test_truncates_long_names(self):
        long_name = "a" * 300
        result = sanitize_filename(long_name)
        assert len(result) <= 200

    def test_prefixes_windows_reserved_names(self):
        assert sanitize_filename("CON") == "_CON"
        assert sanitize_filename("NUL") == "_NUL"
        assert sanitize_filename("COM1") == "_COM1"
        assert sanitize_filename("LPT3") == "_LPT3"

    def test_windows_reserved_case_insensitive(self):
        assert sanitize_filename("con") == "_con"
        assert sanitize_filename("Con.txt") == "_Con.txt"

    def test_control_characters_replaced(self):
        result = sanitize_filename("file\x00name\x1f")
        assert "\x00" not in result
        assert "\x1f" not in result
        assert "file" in result


class TestTimeStringToSeconds:
    def test_basic_conversion(self):
        assert time_string_to_seconds("01:02:03") == 3723

    def test_zero_time(self):
        assert time_string_to_seconds("00:00:00") == 0

    def test_hours_only(self):
        assert time_string_to_seconds("02:00:00") == 7200

    def test_minutes_only(self):
        assert time_string_to_seconds("00:30:00") == 1800

    def test_seconds_only(self):
        assert time_string_to_seconds("00:00:45") == 45

    def test_with_fractional_seconds(self):
        assert time_string_to_seconds("00:01:30.500") == 90

    def test_invalid_format_returns_zero(self):
        assert time_string_to_seconds("invalid") == 0

    def test_empty_string_returns_zero(self):
        assert time_string_to_seconds("") == 0

    def test_leading_whitespace_handled(self):
        assert time_string_to_seconds("  00:01:00") == 60


class TestValidateVideo:
    def test_returns_unknown_when_no_ffprobe(self, tmp_path):
        dummy = tmp_path / "test.mp4"
        dummy.write_bytes(b"\x00" * 2048)
        with patch("udemy_dl.utils.is_ffprobe_available", return_value=False):
            result = validate_video(dummy)
        assert result == ValidationResult.UNKNOWN

    def test_returns_invalid_for_nonexistent_file(self, tmp_path):
        path = tmp_path / "missing.mp4"
        with patch("udemy_dl.utils.is_ffprobe_available", return_value=True):
            result = validate_video(path)
        assert result == ValidationResult.INVALID
