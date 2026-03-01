"""Tests for udemy_dl.utils module."""


from udemy_dl.utils import sanitize_filename, time_string_to_seconds


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
        # fractional part should be stripped
        assert time_string_to_seconds("00:01:30.500") == 90

    def test_invalid_format_returns_zero(self):
        assert time_string_to_seconds("invalid") == 0

    def test_empty_string_returns_zero(self):
        assert time_string_to_seconds("") == 0

    def test_leading_whitespace_handled(self):
        assert time_string_to_seconds("  00:01:00") == 60
