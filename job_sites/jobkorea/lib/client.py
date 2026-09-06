"""잡코리아 HTTP.

**목록이 POST 다.** 사람인·Wanted 는 GET 으로 조건을 실었는데, 잡코리아는 조건을
`condition[...]` 폼 본문에 담아 보낸다. 주소창에 조건이 안 남는 이유가 이것이고,
그래서 "URL 로는 못 거른다" 고 오해하기 쉽다 — 실은 GET 으로도 되지만, 페이지를
넘기려면 POST 엔드포인트를 써야 한다.

차단은 관측되지 않았다. `HeadlessChrome` UA 도 200 이 온다 (Wanted 는 403 이었다).
그래도 실제 브라우저와 같은 헤더를 보내고 요청 사이에 간격을 둔다 — 레이트리밋을
아직 못 쟀고, 못 쟀다는 것이 없다는 뜻은 아니다.
"""
from __future__ import annotations

import random
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://www.jobkorea.co.kr"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
}

MIN_INTERVAL = 0.8
JITTER = 0.5
TIMEOUT = 40
MAX_RETRIES = 3


class BlockedError(RuntimeError):
    """차단으로 보이는 응답. **재시도하지 않는다** — 재시도하면 차단만 깊어진다."""


class JobKoreaClient:
    """세션 하나를 재사용하고, 요청 사이에 간격을 둔다."""

    def __init__(self, *, min_interval: float = MIN_INTERVAL, sleep=time.sleep):
        self.opener = urllib.request.build_opener()
        self.min_interval = min_interval
        self._sleep = sleep
        self._last_request_at = 0.0

    def get_html(self, path: str, params: dict | None = None, *,
                 referer: str | None = None) -> str:
        return self._send(path + _query(params), None, referer)

    def post_html(self, path: str, conditions: dict, extra: dict | None = None, *,
                  referer: str | None = None) -> str:
        """조건을 `condition[이름]=값` 폼으로 보낸다.

        `extra` 는 `Page` 처럼 조건 바깥의 값이다 — `condition[]` 으로 감싸지 않는다.
        """
        fields = [("condition[%s]" % key, value) for key, value in conditions.items()]
        fields += list((extra or {}).items())
        return self._send(path, urllib.parse.urlencode(fields).encode("utf-8"), referer)

    def _send(self, url_path: str, body: bytes | None, referer: str | None) -> str:
        url = BASE_URL + url_path
        headers = dict(HEADERS)
        if referer:
            headers["Referer"] = referer
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
            headers["X-Requested-With"] = "XMLHttpRequest"
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            self._wait_turn()
            try:
                request = urllib.request.Request(url, data=body, headers=headers)
                with self.opener.open(request, timeout=TIMEOUT) as response:
                    return response.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as error:
                if error.code in (403, 429):
                    raise BlockedError(
                        "잡코리아가 %d 로 막았습니다 (%s).\n"
                        "  · 요청 간격이 %.1f초보다 짧아졌는지\n"
                        "  · User-Agent 가 실제 브라우저와 다른지 확인하세요."
                        % (error.code, url, self.min_interval)) from error
                last_error = error
            except (urllib.error.URLError, OSError) as error:
                last_error = error
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

    같은 이름을 여러 번 보내면 잡코리아는 **첫 값만** 쓴다. 실측:

        jobtype=1              155,809건
        jobtype=3                2,107건
        jobtype=1&jobtype=3    155,809건   ← 3 이 통째로 버려졌다
        jobtype=1,3            156,940건   ← 이게 합집합이다

    사람인은 **마지막** 값만 썼다. 방향은 반대지만 결과는 같다 — 조용히 값을 잃는다.
    """
    if not params:
        return ""
    pairs = []
    for key, value in params.items():
        joined = (",".join(str(item) for item in value if str(item).strip())
                  if isinstance(value, (list, tuple))
                  else ("" if value is None else str(value)))
        if joined:
            pairs.append((key, joined))
    return "?" + urllib.parse.urlencode(pairs) if pairs else ""
