"""Udemy REST API client with automatic retry and pagination.

All network calls go through :meth:`UdemyAPI._request_with_retry` which
applies exponential back-off so that transient failures are tolerated
transparently.
"""

from __future__ import annotations

import json
import time
import urllib.parse
from typing import Dict, List

import requests
from requests.exceptions import RequestException

from .config import Config
from .exceptions import APIError, CurriculumFetchError
from .models import Course
from .utils import get_logger

logger = get_logger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
"""Truncated Chrome user-agent sent with every request."""

MAX_RETRIES = 3
RETRY_BACKOFF = 2
PAGINATION_DELAY = 0.5


class UdemyAPI:
    """Authenticated client for Udemy's REST API.

    Handles session management, automatic retries with exponential back-off,
    and transparent pagination for list endpoints.

    Args:
        config: Application configuration containing domain, token, and
            client_id.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Build a :class:`requests.Session` pre-loaded with auth headers."""
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
        """Issue a GET request with up to :data:`MAX_RETRIES` attempts.

        Raises:
            APIError: When all retry attempts have been exhausted.
        """
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

    def fetch_owned_courses(self) -> List[Course]:
        """Fetch all courses the authenticated user is enrolled in.

        Paginates through the ``subscribed-courses`` endpoint, collecting
        course IDs and titles.  Stops on error and returns partial results
        so the user can still work with whatever was retrieved.
        """
        url: str | None = (
            f"{self.config.domain}/api-2.0/users/me/subscribed-courses/?page_size=100"
        )
        courses: List[Course] = []
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

    def get_course_curriculum(self, course_id: int) -> List[Dict]:
        """Retrieve the full curriculum (chapters + lectures) for a course.

        Raises:
            CurriculumFetchError: If any page of the curriculum cannot be
                retrieved (partial results are *not* returned here because
                incomplete curricula lead to mis-ordered downloads).
        """
        url: str | None = (
            f"{self.config.domain}/api-2.0/courses/{course_id}/"
            f"subscriber-curriculum-items/?page=1&page_size=100"
            f"&fields[lecture]=title,asset,id&fields[chapter]=title"
            f"&fields[asset]=stream_urls,hls_url"
        )
        items: List[Dict] = []
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
                raise CurriculumFetchError(
                    f"Failed to fetch complete curriculum: {e}"
                ) from e
        return items
