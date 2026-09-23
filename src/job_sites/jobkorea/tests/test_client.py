"""HTTP 계층. 네트워크를 타지 않는다 — opener 를 가짜로 바꿔 넣는다.

가장 중요한 것은 **값이 여럿일 때 콤마로 잇는가**다. 같은 이름을 두 번 보내면
잡코리아는 첫 값만 쓰고 나머지를 버리는데, 결과가 나오므로 조건이 먹은 줄 안다.
"""
from __future__ import annotations

import urllib.error
import urllib.parse

from lib.client import BlockedError, JobKoreaClient, _query

from .helpers import check, check_equal, check_raises


class FakeResponse:
    def __init__(self, text: str):
        self._text = text

    def read(self):
        return self._text.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeOpener:
    """요청을 기록하고 정해진 답을 돌려준다."""

    def __init__(self, answers=None):
        self.requests = []
        self.answers = list(answers or ["<html>ok</html>"])

    def open(self, request, timeout=None):
        self.requests.append(request)
        answer = self.answers.pop(0) if self.answers else "<html>ok</html>"
        if isinstance(answer, Exception):
            raise answer
        return FakeResponse(answer)


def _client(answers=None):
    client = JobKoreaClient(min_interval=0, sleep=lambda _seconds: None)
    client.opener = FakeOpener(answers)
    return client


def _body_of(request) -> dict:
    return dict(urllib.parse.parse_qsl(request.data.decode("utf-8")))


def test_NORMAL_get_builds_query():
    client = _client()
    client.get_html("/Recruit/GI_Read_Comt_Ifrm", {"Gno": "49911986"})
    check("Gno=49911986" in client.opener.requests[0].full_url, "질의 문자열")


def test_NORMAL_post_wraps_conditions():
    client = _client()
    client.post_html("/Recruit/Home/_GI_List/", {"duty": "1000229"}, {"Page": 2})
    fields = _body_of(client.opener.requests[0])
    check_equal(fields["condition[duty]"], "1000229", "조건은 condition[] 로 감싼다")
    check_equal(fields["Page"], "2", "Page 는 조건 바깥이라 감싸지 않는다")


def test_NORMAL_sends_browser_headers():
    client = _client()
    client.get_html("/Recruit/GI_Read/1", referer="https://www.jobkorea.co.kr/recruit/joblist")
    headers = client.opener.requests[0].headers
    check("Chrome" in headers["User-agent"], "실제 브라우저 UA")
    check("HeadlessChrome" not in headers["User-agent"], "헤드리스 표식을 남기지 않는다")
    check_equal(headers["Referer"], "https://www.jobkorea.co.kr/recruit/joblist", "Referer")


def test_NORMAL_post_marks_itself_as_xhr():
    client = _client()
    client.post_html("/Recruit/Home/_GI_List/", {"duty": "1"})
    headers = client.opener.requests[0].headers
    check_equal(headers["X-requested-with"], "XMLHttpRequest", "목록은 XHR 로 온다")
    check("urlencoded" in headers["Content-type"], "폼 본문")


def test_EXCEPTION_403_is_blocked_and_not_retried():
    error = urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
    client = _client([error])
    check_raises(BlockedError, lambda: client.get_html("/x"), "403")
    check_equal(len(client.opener.requests), 1, "차단은 재시도하지 않는다 — 깊어지기만 한다")


def test_EXCEPTION_429_is_blocked():
    client = _client([urllib.error.HTTPError("u", 429, "Too Many", {}, None)])
    error = check_raises(BlockedError, lambda: client.get_html("/x"), "429")
    check("간격" in str(error), "무엇을 확인해야 하는지 알려야 한다")


def test_EXCEPTION_500_is_retried_then_gives_up():
    error = urllib.error.HTTPError("u", 500, "Server Error", {}, None)
    client = _client([error, error, error])
    check_raises(ConnectionError, lambda: client.get_html("/x"), "5xx 는 재시도 후 포기")
    check_equal(len(client.opener.requests), 3, "MAX_RETRIES 만큼 시도")


def test_EXCEPTION_transient_failure_recovers():
    client = _client([urllib.error.URLError("끊김"), "<html>ok</html>"])
    check_equal(client.get_html("/x"), "<html>ok</html>", "한 번 실패해도 다음에 받는다")


def test_BOUNDARY_repeated_values_are_comma_joined():
    # 결함이 될 뻔한 곳: `jobtype=1&jobtype=3` 은 **첫 값만** 먹는다. 실측으로 확인했다.
    check_equal(_query({"jobtype": ["1", "3"]}), "?jobtype=1%2C3",
                "값이 여럿이면 콤마 하나로 이어야 한다")
    check("jobtype=1&jobtype=3" not in urllib.parse.unquote(_query({"jobtype": ["1", "3"]})),
          "같은 이름을 두 번 보내면 안 된다")


def test_BOUNDARY_empty_and_none_values_are_dropped():
    check_equal(_query({"a": "", "b": None, "c": "1"}), "?c=1", "빈 값은 안 싣는다")
    check_equal(_query({"a": ["", "  "]}), "", "전부 빈 목록도 안 싣는다")
    check_equal(_query({}), "", "빈 조건")
    check_equal(_query(None), "", "조건 없음")


def test_BOUNDARY_korean_value_is_percent_encoded():
    check("%" in _query({"kw": "백엔드"}), "한글은 인코딩해서 실어야 한다")


def test_BOUNDARY_rate_limit_waits_between_requests():
    slept = []
    client = JobKoreaClient(min_interval=0.8, sleep=slept.append)
    client.opener = FakeOpener(["a", "b"])
    client.get_html("/1")
    client.get_html("/2")
    check(any(seconds > 0 for seconds in slept),
          "두 번째 요청 전에 기다려야 한다: %r" % slept)
