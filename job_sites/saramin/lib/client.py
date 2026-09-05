"""사람인 HTTP. 차단 회피와 재시도.

Wanted 는 UA 하나가 게이트였고 레이트리밋이 없었다. **사람인은 다르다** —
상세를 0.3~0.7초 간격으로 받으면 연결이 끊긴다. 1.0초는 견딘다. 그래서 간격이 필수다.

그리고 `HeadlessChrome` UA 는 응답이 안 온다(Wanted 는 403 이라도 줬다). 실제 크롬과
같은 헤더 묶음을 보낸다.
"""
from __future__ import annotations

import random
import time
import urllib.error
import urllib.request

BASE_URL = "https://www.saramin.co.kr"

# **`HeadlessChrome` 이 들어가면 안 된다.** 그게 유일한 게이트다.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}

# 실측: 0.5초 간격은 끊기고 1.0초는 견딘다. 여유를 두고 지터를 얹는다.
MIN_INTERVAL = 1.0
JITTER = 0.6
TIMEOUT = 40
MAX_RETRIES = 3


class BlockedError(RuntimeError):
    """차단으로 보이는 응답. **재시도하지 않는다** — 재시도하면 차단만 깊어진다."""


class SaraminClient:
    """세션 하나를 재사용하고, 요청 사이에 간격을 둔다."""

    def __init__(self, *, min_interval: float = MIN_INTERVAL, sleep=time.sleep):
        self.opener = urllib.request.build_opener()
        self.min_interval = min_interval
        self._sleep = sleep
        self._last_request_at = 0.0

    def get_html(self, path: str, params: dict | None = None, *,
                 referer: str | None = None) -> str:
        url = BASE_URL + path + _query(params)
        headers = dict(HEADERS)
        if referer:
            headers["Referer"] = referer
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            self._wait_turn()
            try:
                request = urllib.request.Request(url, headers=headers)
                with self.opener.open(request, timeout=TIMEOUT) as response:
                    return response.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as error:
                if error.code in (403, 429):
                    raise BlockedError(
                        "사람인이 %d 로 막았습니다 (%s).\n"
                        "  · User-Agent 에 HeadlessChrome 이 섞였는지\n"
                        "  · 요청 간격이 %.1f초보다 짧아졌는지 확인하세요."
                        % (error.code, url, self.min_interval)) from error
                last_error = error
            except (urllib.error.URLError, OSError) as error:
                last_error = error
            # 서버가 흔들릴 때는 물러섰다 다시 — 다만 차단은 위에서 이미 걸러 냈다
            self._sleep(self.min_interval * (2 ** attempt))
        raise ConnectionError("%s 를 %d번 시도해도 못 받았습니다: %s"
                              % (url, MAX_RETRIES, last_error))

    def _wait_turn(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.min_interval + random.uniform(0, JITTER) - elapsed
        if remaining > 0:
            self._sleep(remaining)
        self._last_request_at = time.monotonic()


def _query(params: dict | None) -> str:
    """조건을 질의 문자열로. **값이 여럿이면 콤마로 잇는다.**

    같은 이름을 여러 번 보내면 사람인은 **마지막 값만 쓴다.** 실측:

        cat_kewd=84            1,854건
        cat_kewd=87            1,507건
        cat_kewd=84&cat_kewd=87  1,507건   ← 84 가 통째로 버려졌다
        cat_kewd=84,87         2,552건   ← 이게 합집합이다

    `loc_mcd` `job_type` 도 같다. 조건을 넓혔는데 **결과가 줄고 예외도 안 난다** —
    직무 둘을 넣었는데 하나만 긁히는 것을 총계가 이상해서야 알아챘다.
    """
    if not params:
        return ""
    import urllib.parse
    pairs = []
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            joined = ",".join(str(item) for item in value if str(item).strip())
        else:
            joined = "" if value is None else str(value)
        if joined:
            pairs.append((key, joined))
    return "?" + urllib.parse.urlencode(pairs) if pairs else ""
