"""`lib/client.py` — 차단 회피와 재시도.

**네트워크를 타지 않는다.** `urllib` 을 바꿔 끼워 응답을 정한다.

노리는 결함 셋.

1. **차단에 재시도하는 것.** 403/429 를 서버 흔들림처럼 다뤄 다시 던지면 차단만 깊어진다.
2. **간격을 안 지키는 것.** 실측에서 0.5초는 끊기고 1.0초는 견뎠다. 간격이 없으면
   상세 수집 중반에 연결이 죽는다.
3. **실패를 성공처럼 돌려주는 것.** 세 번 다 실패했는데 빈 문자열을 주면 그 공고가
   조용히 빈칸이 된다.
"""
from __future__ import annotations

import urllib.error

from lib import client as client_module
from tests.helpers import check, check_equal


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeOpener:
    """미리 정한 순서대로 응답하거나 예외를 낸다."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        outcome = self.outcomes.pop(0) if self.outcomes else b"<html>ok</html>"
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)


def make_client(outcomes=(), **kwargs):
    slept: list[float] = []
    saramin = client_module.SaraminClient(sleep=slept.append, **kwargs)
    saramin.opener = FakeOpener(outcomes)
    return saramin, slept


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x.test", code, "no", {}, None)


# ─────────────────────────────── 일반 ───────────────────────────────

def test_NORMAL_returns_decoded_html():
    saramin, _ = make_client([b"<html>\xed\x95\x9c\xea\xb8\x80</html>"])
    check_equal(saramin.get_html("/path"), "<html>한글</html>", "utf-8 로 읽는다")


def test_NORMAL_browser_headers_are_sent():
    saramin, _ = make_client()
    saramin.get_html("/path")
    headers = saramin.opener.requests[0].headers
    lowered = {key.lower(): value for key, value in headers.items()}
    check("Chrome" in lowered["user-agent"], "실제 브라우저 UA")
    check("ko" in lowered["accept-language"], "한국어 우선")


def test_NORMAL_headless_marker_is_never_sent():
    # 그게 유일한 게이트다. Wanted 는 403 이라도 줬지만 사람인은 응답이 안 온다.
    check("HeadlessChrome" not in client_module.USER_AGENT,
          "UA 에 HeadlessChrome 이 들어가면 안 된다")


def test_NORMAL_query_is_built_from_params():
    saramin, _ = make_client()
    saramin.get_html("/path", {"a": "1", "b": "x"})
    url = saramin.opener.requests[0].full_url
    check("a=1" in url and "b=x" in url, "조건이 질의로 들어가야 한다: %s" % url)


def test_NORMAL_referer_is_sent_when_given():
    saramin, _ = make_client()
    saramin.get_html("/path", referer="https://x.test/list")
    lowered = {k.lower(): v for k, v in saramin.opener.requests[0].headers.items()}
    check_equal(lowered.get("referer"), "https://x.test/list", "Referer")


# ─────────────────────────────── 예외 ───────────────────────────────

def test_EXCEPTION_block_is_not_retried():
    # 결함이 될 뻔한 곳: 403 을 서버 흔들림처럼 다뤄 다시 던지면 차단만 깊어진다.
    saramin, _ = make_client([http_error(403), b"<html>ok</html>"])
    try:
        saramin.get_html("/path")
    except client_module.BlockedError as error:
        check_equal(len(saramin.opener.requests), 1, "한 번만 던져야 한다")
        check("HeadlessChrome" in str(error), "무엇을 의심할지 알려야 한다")
        check("간격" in str(error), "간격도 의심 대상이다")
        return
    raise AssertionError("403 을 차단으로 안 봤다")


def test_EXCEPTION_rate_limit_is_also_a_block():
    saramin, _ = make_client([http_error(429)])
    try:
        saramin.get_html("/path")
    except client_module.BlockedError:
        return
    raise AssertionError("429 를 차단으로 안 봤다")


def test_EXCEPTION_server_error_is_retried_then_raised():
    saramin, slept = make_client([http_error(500)] * client_module.MAX_RETRIES)
    try:
        saramin.get_html("/path")
    except ConnectionError as error:
        check_equal(len(saramin.opener.requests), client_module.MAX_RETRIES, "세 번 시도")
        check("못 받았습니다" in str(error), "실패를 성공처럼 돌려주면 안 된다")
        return
    raise AssertionError("세 번 실패했는데 조용히 넘어갔다")


def test_EXCEPTION_transient_failure_recovers():
    saramin, _ = make_client([urllib.error.URLError("끊김"), b"<html>ok</html>"])
    check_equal(saramin.get_html("/path"), "<html>ok</html>", "다시 시도해 성공한다")


def test_EXCEPTION_broken_encoding_does_not_crash():
    saramin, _ = make_client([b"<html>\xff\xfe</html>"])
    check("html" in saramin.get_html("/path"), "깨진 바이트가 있어도 읽는다")


# ─────────────────────────────── 경계 ───────────────────────────────

def test_BOUNDARY_interval_is_kept_between_requests():
    saramin, slept = make_client([b"a", b"b"], min_interval=1.0)
    saramin.get_html("/one")
    saramin.get_html("/two")
    check(any(value > 0 for value in slept),
          "두 번째 요청 앞에 쉬어야 한다: %r" % slept)


def test_BOUNDARY_backoff_grows_with_each_retry():
    saramin, slept = make_client([http_error(500)] * 3, min_interval=1.0)
    try:
        saramin.get_html("/path")
    except ConnectionError:
        pass
    waits = [value for value in slept if value >= 1.0]
    check(len(waits) >= 2 and waits[-1] > waits[0],
          "물러서는 시간이 늘어야 한다: %r" % waits)


def test_BOUNDARY_empty_params_make_no_query_string():
    saramin, _ = make_client()
    saramin.get_html("/path", {})
    check_equal(saramin.opener.requests[0].full_url,
                client_module.BASE_URL + "/path", "빈 조건은 물음표도 안 붙인다")


def test_BOUNDARY_none_and_blank_values_are_dropped():
    saramin, _ = make_client()
    saramin.get_html("/path", {"a": None, "b": "", "c": "1"})
    url = saramin.opener.requests[0].full_url
    check("a=" not in url and "b=" not in url, "빈 값은 안 보낸다: %s" % url)
    check("c=1" in url, "있는 값은 보낸다")


def test_BOUNDARY_configured_interval_is_reported_in_the_block_message():
    saramin, _ = make_client([http_error(403)], min_interval=2.5)
    try:
        saramin.get_html("/path")
    except client_module.BlockedError as error:
        check("2.5" in str(error), "지금 쓰는 간격을 알려야 한다: %s" % error)


def test_BOUNDARY_list_values_are_joined_not_repeated():
    # 같은 이름을 여러 번 보내면 사람인은 마지막 값만 쓴다. filters 가 이미 문자열로
    # 넘기지만, 여기서도 막아 **두 겹으로** 지킨다.
    saramin, _ = make_client()
    saramin.get_html("/path", {"cat_kewd": ["84", "87"]})
    url = saramin.opener.requests[0].full_url
    check("cat_kewd=84%2C87" in url or "cat_kewd=84,87" in url,
          "콤마로 이어야 한다: %s" % url)
    check(url.count("cat_kewd=") == 1, "같은 이름을 두 번 보내면 안 된다: %s" % url)


def test_BOUNDARY_blank_items_inside_a_list_are_dropped():
    saramin, _ = make_client()
    saramin.get_html("/path", {"a": ["1", "", "  ", "2"]})
    url = saramin.opener.requests[0].full_url
    check("a=1%2C2" in url or "a=1,2" in url, "빈 칸은 빼고 잇는다: %s" % url)


def test_BOUNDARY_empty_list_sends_nothing():
    saramin, _ = make_client()
    saramin.get_html("/path", {"a": [], "b": "1"})
    url = saramin.opener.requests[0].full_url
    check("a=" not in url, "빈 목록은 안 보낸다: %s" % url)
