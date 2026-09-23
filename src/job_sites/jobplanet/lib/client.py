"""잡플래닛 HTTP.

## Cloudflare 가 막는데, 게이트는 **HTTP 버전**이다

세 사이트 중 처음으로 봇 방어가 걸려 있다. 그런데 막는 것이 UA 가 아니다 — 실측:

    UA 없이 / 정상 Chrome UA / HeadlessChrome UA        403
    브라우저 헤더 11개를 전부 맞춤                          403
    Playwright (headless 실제 Chrome)                   403
    `curl --http1.1` 하나만 추가                          200

Cloudflare 가 **HTTP/2 지문**으로 거른다. `urllib` 은 기본이 HTTP/1.1 이라
추가 라이브러리 없이 그대로 통과한다 — 그래서 여기서 `requests` 도 안 쓴다.

## 레이트리밋이 **있다**

사람인·잡코리아에는 없었는데 여기는 있다. 0.3초 간격으로 던지다 403 을 맞았다.
임계를 정확히 재지는 않았다 — 재려면 일부러 막혀 봐야 하고, 막히면 한동안 못 긁는다.
그래서 넉넉히 잡고, 403 이 오면 **재시도하지 않고 멈춘다.**
"""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://www.jobplanet.co.kr"
LIST_REFERER = BASE_URL + "/job"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": LIST_REFERER,
}

# 0.3초로 던지다 403 을 맞았고, **1.2초로도 맞았다** — 7요청 만에 막혔다.
# 간격만이 아니라 **한동안 던진 총량**을 보는 듯하다. 그래서 넉넉히 잡는다.
# 임계를 정확히 재지는 않았다 — 재려면 일부러 막혀 봐야 하고, 막히면 한동안 못 긁는다.
MIN_INTERVAL = 2.5
JITTER = 0.6
TIMEOUT = 40
MAX_RETRIES = 3

# 다시 물어봐야 답이 같은 코드. 잡플래닛은 접근할 수 없는 공고에 **400** 을 준다 —
# 404 만 막아 두면 그런 공고 하나에 요청 3개를 쓰고, 그만큼 레이트리밋에 더 가까워진다.
NO_RETRY_CODES = frozenset({400, 404, 410})


class BlockedError(RuntimeError):
    """차단으로 보이는 응답. **재시도하지 않는다** — 재시도하면 차단만 깊어진다."""


class JobPlanetClient:
    """요청 사이에 간격을 두고, 차단이면 즉시 멈춘다."""

    def __init__(self, *, min_interval: float = MIN_INTERVAL, sleep=time.sleep):
        self.opener = urllib.request.build_opener()
        self.min_interval = min_interval
        self._sleep = sleep
        self._last_request_at = 0.0

    def get_json(self, path: str, params: dict | None = None) -> dict:
        """JSON 응답. 껍데기(`{"status","code","data"}`)를 벗겨 `data` 만 돌려준다."""
        body = self._send(path + _query(params))
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError("%s 가 JSON 이 아닌 것을 돌려줬습니다 (앞부분: %r)"
                             % (path, body[:120])) from error
        return payload.get("data", payload) if isinstance(payload, dict) else payload

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
                        "잡플래닛이 %d 로 막았습니다 (%s).\n"
                        "  · **방금 돌린 뒤 곧바로 다시 돌리지는 않았는지** — 간격만이 아니라\n"
                        "    한동안 던진 총량을 봅니다. 몇 분 쉬었다 다시 돌리면 풀립니다.\n"
                        "  · 요청 간격(%.1f초)을 줄이지는 않았는지\n"
                        "  · HTTP/2 로 보내고 있지는 않은지 —\n"
                        "    Cloudflare 가 HTTP/2 지문으로 거릅니다. urllib 은 HTTP/1.1 이라 통과합니다."
                        % (error.code, url, self.min_interval)) from error
                if error.code in NO_RETRY_CODES:
                    # 없는 공고를 세 번 물어봐야 세 번 없다. 재시도는 레이트리밋만 쓴다.
                    # **400 도 여기 든다** — 접근할 수 없는 공고가 404 가 아니라 400 으로 온다.
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
    """조건을 질의 문자열로. **값이 여럿이면 콤마로 잇는다.**

    같은 이름을 여러 번 보내면 잡플래닛은 **마지막 값만** 쓴다. 실측:

        occupation_level2=11904              579건
        occupation_level2=11905              288건
        occupation_level2=11904&…=11905      288건   ← 11904 가 통째로 버려졌다
        occupation_level2=11904,11905        673건   ← 이게 합집합이다

    잡코리아는 **첫** 값만 썼다. 방향은 반대지만 결과는 같다 — 조용히 값을 잃는다.
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
