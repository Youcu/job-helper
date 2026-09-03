"""Wanted HTTP 클라이언트 — API 만 쓴다.

HTML 페이지는 건드리지 않는다. 필요한 데이터가 전부 API 에 있고(공고 페이지와
본문 7필드가 바이트 단위로 같은 것을 20건 전수 확인), API 만 쓰는 쪽이 화면 구조
변경에 흔들리지 않는다.

CloudFront 가 `HeadlessChrome` UA 를 403 으로 막는다. 그래서 실제 Chrome 과 같은
헤더 묶음을 보내고, 세션 하나를 재사용해 커넥션을 유지한다.
"""
from __future__ import annotations

import random
import time

import requests

BASE_URL = "https://www.wanted.co.kr"

CHROME_VERSION = "152"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) Chrome/{CHROME_VERSION}.0.0.0 Safari/537.36"
)


class BlockedError(Exception):
    """403 — UA 나 헤더가 실제 브라우저와 달라 CloudFront 에 막혔다는 뜻."""


class WantedClient:
    def __init__(self, min_delay: float = 0.2, max_delay: float = 0.5, retries: int = 3):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Origin": BASE_URL,
                "sec-ch-ua": f'"Chromium";v="{CHROME_VERSION}", "Not(A:Brand";v="24", '
                f'"Google Chrome";v="{CHROME_VERSION}"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "Connection": "keep-alive",
            }
        )

    def get_json(self, path: str, *, params=None, referer: str) -> dict:
        time.sleep(random.uniform(self.min_delay, self.max_delay))
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                resp = self.session.get(
                    f"{BASE_URL}{path}", params=params, headers={"Referer": referer}, timeout=30
                )
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(2**attempt)
                continue
            if resp.status_code == 403:
                raise BlockedError(
                    f"403 으로 막혔습니다: {resp.url}\n"
                    "  User-Agent 가 실제 브라우저와 같은지 확인하세요. "
                    "'HeadlessChrome' 이 들어가면 CloudFront 가 차단합니다."
                )
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = requests.HTTPError(f"{resp.status_code} {resp.url}")
                time.sleep(2**attempt + random.random())
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"{self.retries}회 재시도 실패: {path}") from last_error
