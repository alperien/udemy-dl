from __future__ import annotations

import json
import time
import urllib.parse

import requests
from requests.exceptions import RequestException

from .config import Config
from .exceptions import APIError, CurriculumFetchError
from .models import Course
from .utils import get_logger

logger = get_logger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

MAX_RETRIES = 3
RETRY_BACKOFF = 2
PAGINATION_DELAY = 0.5


class UdemyAPI:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "Authorization": f"Bearer {self.config.token}",
                "User-Agent": USER_AGENT,
                "Origin": self.config.domain,
                "Referer": f"{self.config.domain}/",
            }
        )
        session.cookies.update(
            {"access_token": self.config.token, "client_id": self.config.client_id}
        )
        return session

    def _request_with_retry(self, url: str, timeout: int = 30) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.session.get(url, timeout=timeout)
                response.raise_for_status()
                return response
            except RequestException as e:
                last_exc = e
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF * (2 ** (attempt - 1))
                    logger.warning(
                        f"Request failed (attempt {attempt}/{MAX_RETRIES}), "
                        f"retrying in {wait}s: {e}"
                    )
                    time.sleep(wait)
                else:
                    logger.error(f"Request failed after {MAX_RETRIES} attempts: {e}")
        raise APIError(
            f"Request failed after {MAX_RETRIES} attempts: {last_exc}",
        ) from last_exc

    def fetch_owned_courses(self) -> list[Course]:
        url: str | None = f"{self.config.domain}/api-2.0/users/me/subscribed-courses/?page_size=100"
        courses: list[Course] = []
        while url:
            try:
                response = self._request_with_retry(url)
                data = response.json()
                for item in data.get("results", []):
                    course = Course.from_api(item)
                    if course is not None:
                        courses.append(course)
                url = data.get("next")
                if url:
                    url = urllib.parse.urljoin(self.config.domain, url)
                    time.sleep(PAGINATION_DELAY)
            except (APIError, RequestException, json.JSONDecodeError) as e:
                logger.error(f"Error fetching courses (page): {e}")
                break
        return courses

    def get_course_curriculum(self, course_id: int) -> list[dict]:
        url: str | None = (
            f"{self.config.domain}/api-2.0/courses/{course_id}/"
            f"subscriber-curriculum-items/?page=1&page_size=100"
            f"&fields[lecture]=title,asset,id&fields[chapter]=title"
            f"&fields[asset]=stream_urls,hls_url,asset_type,title,filename,download_urls,body,external_url"
        )
        items: list[dict] = []
        while url:
            try:
                response = self._request_with_retry(url)
                data = response.json()
                items.extend(data.get("results", []))
                url = data.get("next")
                if url:
                    url = urllib.parse.urljoin(self.config.domain, url)
                    time.sleep(PAGINATION_DELAY)
            except (APIError, RequestException, json.JSONDecodeError) as e:
                logger.error(f"Error fetching curriculum: {e}")
                raise CurriculumFetchError(f"Failed to fetch complete curriculum: {e}") from e
        return items
