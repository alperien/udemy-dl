import json
from typing import Dict, List

import requests
from requests.exceptions import HTTPError, RequestException, Timeout

from .config import Config
from .utils import get_logger

logger = get_logger(__name__)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


class UdemyAPI:
    def __init__(self, config: Config):
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

    def fetch_owned_courses(self) -> List[Dict]:
        url = f"{self.config.domain}/api-2.0/users/me/subscribed-courses/?page_size=100"
        courses = []
        while url:
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                data = response.json()
                for item in data.get("results", []):
                    courses.append({"id": item["id"], "title": item["title"]})
                url = data.get("next")
            except (Timeout, HTTPError, RequestException) as e:
                logger.error(f"Error fetching courses: {e}")
                break
        return courses

    def get_course_curriculum(self, course_id: int) -> List[Dict]:
        url = f"{self.config.domain}/api-2.0/courses/{course_id}/subscriber-curriculum-items/?page=1&page_size=100&fields[lecture]=title,asset,id&fields[chapter]=title&fields[asset]=stream_urls,hls_url"
        items = []
        while url:
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                data = response.json()
                items.extend(data.get("results", []))
                url = data.get("next")
            except (Timeout, HTTPError, RequestException, json.JSONDecodeError) as e:
                logger.error(f"Error fetching curriculum: {e}")
                break
        return items

    def get_subtitles_data(self, course_id: int, lecture_id: int) -> List[Dict]:
        try:
            url = f"{self.config.domain}/api-2.0/courses/{course_id}/lectures/{lecture_id}/subtitles"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json().get("captions", [])
        except Exception as e:
            logger.warning(f"Failed to fetch subtitles: {e}")
            return []

    def get_materials_data(self, course_id: int, lecture_id: int) -> List[Dict]:
        try:
            url = f"{self.config.domain}/api-2.0/courses/{course_id}/lectures/{lecture_id}/supplementary-assets"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json().get("results", [])
        except Exception as e:
            logger.warning(f"Failed to fetch materials: {e}")
            return []
