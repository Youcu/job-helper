"""점핏 HTTP.

**차단이 없다.** 네 사이트 중 가장 순하다 — 실측:

    정상 Chrome UA / UA 없음 / HeadlessChrome UA / Referer 없음     전부 200

인증도 쿠키도 필요 없다. 그래도 실제 브라우저와 같은 헤더를 보내고 요청 사이에 간격을
둔다 — **레이트리밋을 못 봤다는 것이 없다는 뜻은 아니다.** 잡플래닛에서 "안 막힌다" 고
넘겼다가 실제 부하에서 막힌 적이 있다.

## 같은 이름을 두 번 보내도 된다

앞선 세 사이트는 전부 값을 하나 잃었는데(사람인·잡플래닛 마지막 값, 잡코리아 첫 값)
여기는 둘 다 먹는다. 실측:

    jobCategory=1        139건
    jobCategory=2         73건
    jobCategory=1&…=2    189건   ← 둘 다 먹었다 (139+73 에서 겹침을 뺀 수)
    jobCategory=1,2      189건   ← 콤마도 같은 결과

**그래도 반복 파라미터로 보낸다.** 화면이 그렇게 보내고, 콤마는 이 사이트가 우연히
받아 주는 것일 수 있다.
"""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://jumpit-api.saramin.co.kr"
LIST_REFERER = "https://jumpit.saramin.co.kr/positions"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": LIST_REFERER,
    "Origin": "https://jumpit.saramin.co.kr",
}

# 차단을 못 봤지만 간격은 둔다. 못 봤다는 것이 없다는 뜻은 아니다.
MIN_INTERVAL = 0.4
JITTER = 0.3
TIMEOUT = 30
MAX_RETRIES = 3

# 다시 물어봐야 답이 같은 코드. 없는 공고를 세 번 물어봐야 세 번 없다.
NO_RETRY_CODES = frozenset({400, 404, 410})


class BlockedError(RuntimeError):
    """차단으로 보이는 응답. **재시도하지 않는다** — 재시도하면 차단만 깊어진다."""


class JumpitClient:
    """세션 하나를 재사용하고, 요청 사이에 간격을 둔다."""

    def __init__(self, *, min_interval: float = MIN_INTERVAL, sleep=time.sleep):
        self.opener = urllib.request.build_opener()
        self.min_interval = min_interval
        self._sleep = sleep
        self._last_request_at = 0.0

    def get_json(self, path: str, params: dict | None = None) -> dict:
        """JSON 응답. 껍데기(`{"message","status","code","result"}`)를 벗겨 `result` 만."""
        body = self._send(path + _query(params))
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError("%s 가 JSON 이 아닌 것을 돌려줬습니다 (앞부분: %r)"
                             % (path, body[:120])) from error
        if not isinstance(payload, dict):
            return payload
        return payload.get("result", payload)

    def _send(self, url_path: str) -> str:
        url = BASE_URL + url_path
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            self._wait_turn()
            try:
                request = urllib.request.Request(url, headers=dict(HEADERS))
                with self.opener.open(request, timeout=TIMEOUT) as response:
                    return response.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as error:
                if error.code in (403, 429):
                    raise BlockedError(
                        "점핏이 %d 로 막았습니다 (%s).\n"
                        "  이 사이트는 차단이 관측되지 않던 곳입니다 — 무언가 바뀌었을 수 있습니다.\n"
                        "  · 요청 간격(%.1f초)을 줄이지는 않았는지\n"
                        "  · User-Agent 가 실제 브라우저와 다른지 확인하세요."
                        % (error.code, url, self.min_interval)) from error
                if error.code in NO_RETRY_CODES:
                    raise
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
    """조건을 질의 문자열로. **값이 여럿이면 같은 이름을 여러 번 쓴다.**

    이 사이트는 그렇게 보내야 둘 다 먹는다 — 화면도 그렇게 보낸다. 콤마로 이어도
    같은 결과가 나오지만(실측), 그건 우연히 받아 주는 것일 수 있다.
    """
    if not params:
        return ""
    pairs = []
    for key, value in params.items():
        values = value if isinstance(value, (list, tuple)) else [value]
        for item in values:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                pairs.append((key, text))
    return "?" + urllib.parse.urlencode(pairs) if pairs else ""
