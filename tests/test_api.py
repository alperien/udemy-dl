from unittest.mock import MagicMock, patch

import pytest
import requests

from udemy_dl.api import UdemyAPI
from udemy_dl.config import Config


def _make_api() -> UdemyAPI:
    cfg = Config(
        token="t" * 20,
        client_id="c" * 10,
        domain="https://www.udemy.com",
    )
    return UdemyAPI(cfg)


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=resp)
    return resp


class TestFetchOwnedCourses:
    def test_returns_courses(self):
        api = _make_api()
        page1 = {
            "results": [
                {"id": 1, "title": "Course A"},
                {"id": 2, "title": "Course B"},
            ],
            "next": None,
        }
        with patch.object(api.session, "get", return_value=_mock_response(page1)):
            courses = api.fetch_owned_courses()
        assert len(courses) == 2
        assert courses[0] == {"id": 1, "title": "Course A"}

    def test_paginates_through_all_pages(self):
        api = _make_api()
        page1 = {
            "results": [{"id": 1, "title": "Course A"}],
            "next": "https://www.udemy.com/api-2.0/users/me/subscribed-courses/?page=2",
        }
        page2 = {
            "results": [{"id": 2, "title": "Course B"}],
            "next": None,
        }
        responses = [_mock_response(page1), _mock_response(page2)]
        with patch.object(api.session, "get", side_effect=responses):
            with patch("udemy_dl.api.time.sleep"):
                courses = api.fetch_owned_courses()
        assert len(courses) == 2

    def test_skips_items_without_id_or_title(self):
        api = _make_api()
        page = {
            "results": [
                {"id": None, "title": "No ID"},
                {"id": 1, "title": ""},
                {"id": 2, "title": "Valid"},
            ],
            "next": None,
        }
        with patch.object(api.session, "get", return_value=_mock_response(page)):
            courses = api.fetch_owned_courses()
        assert len(courses) == 1
        assert courses[0]["id"] == 2

    def test_returns_partial_on_error(self):
        api = _make_api()
        page1 = {
            "results": [{"id": 1, "title": "Course A"}],
            "next": "https://www.udemy.com/api-2.0/users/me/subscribed-courses/?page=2",
        }
        responses = [
            _mock_response(page1),
            requests.exceptions.Timeout("timed out"),
            requests.exceptions.Timeout("timed out"),
            requests.exceptions.Timeout("timed out"),
        ]
        with patch.object(api.session, "get", side_effect=responses):
            with patch("udemy_dl.api.time.sleep"):
                courses = api.fetch_owned_courses()
        assert len(courses) == 1


class TestRetryLogic:
    def test_retries_on_timeout(self):
        api = _make_api()
        success_resp = _mock_response({"results": [], "next": None})
        side_effects = [
            requests.exceptions.Timeout("timeout"),
            requests.exceptions.Timeout("timeout"),
            success_resp,
        ]
        with patch.object(api.session, "get", side_effect=side_effects) as mock_get:
            with patch("udemy_dl.api.time.sleep") as mock_sleep:
                api.fetch_owned_courses()
        assert mock_get.call_count == 3
        assert mock_sleep.call_count == 2

    def test_raises_after_max_retries(self):
        api = _make_api()
        with patch.object(
            api.session,
            "get",
            side_effect=requests.exceptions.Timeout("always timeout"),
        ):
            with patch("udemy_dl.api.time.sleep"):
                with pytest.raises(requests.exceptions.Timeout):
                    api._request_with_retry("https://example.com")


class TestGetCourseCurriculum:
    def test_returns_items(self):
        api = _make_api()
        page = {
            "results": [
                {"_class": "chapter", "title": "Intro"},
                {"_class": "lecture", "title": "Lecture 1", "id": 101},
            ],
            "next": None,
        }
        with patch.object(api.session, "get", return_value=_mock_response(page)):
            items = api.get_course_curriculum(12345)
        assert len(items) == 2

    def test_raises_runtime_error_on_failure(self):
        api = _make_api()
        with patch.object(
            api.session,
            "get",
            side_effect=requests.exceptions.Timeout("timeout"),
        ):
            with patch("udemy_dl.api.time.sleep"):
                with pytest.raises(RuntimeError, match="Failed to fetch complete curriculum"):
                    api.get_course_curriculum(12345)
