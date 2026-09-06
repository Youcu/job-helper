"""HTTP 계층. 네트워크를 타지 않는다 — opener 를 가짜로 바꿔 넣는다.

가장 중요한 것은 **값이 여럿일 때 콤마로 잇는가**다. 같은 이름을 두 번 보내면
잡플래닛은 마지막 값만 쓰고 앞을 버리는데, 결과가 나오므로 조건이 먹은 줄 안다.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse

from lib.client import BlockedError, JobPlanetClient, _query

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
    def __init__(self, answers=None):
        self.requests = []
        self.answers = list(answers or ['{"status":"success","data":{"ok":1}}'])

    def open(self, request, timeout=None):
        self.requests.append(request)
        answer = self.answers.pop(0) if self.answers else '{"data":{}}'
        if isinstance(answer, Exception):
            raise answer
        return FakeResponse(answer)


def _client(answers=None):
    client = JobPlanetClient(min_interval=0, sleep=lambda _s: None)
    client.opener = FakeOpener(answers)
    return client


def test_NORMAL_unwraps_the_data_envelope():
    client = _client(['{"status":"success","code":200,"data":{"total_count":7}}'])
    check_equal(client.get_json("/api/v3/job/postings"), {"total_count": 7},
                "껍데기를 벗기고 data 만 돌려준다")


def test_NORMAL_builds_query():
    client = _client()
    client.get_json("/api/v3/job/postings", {"page": 2, "page_size": 100})
    url = client.opener.requests[0].full_url
    check("page=2" in url and "page_size=100" in url, url)


def test_NORMAL_sends_browser_headers():
    client = _client()
    client.get_json("/api/v3/job/postings")
    headers = client.opener.requests[0].headers
    check("Chrome" in headers["User-agent"], "실제 브라우저 UA")
    check("HeadlessChrome" not in headers["User-agent"], "헤드리스 표식을 남기지 않는다")
    check("jobplanet.co.kr/job" in headers["Referer"], "Referer")


def test_EXCEPTION_403_is_blocked_and_not_retried():
    client = _client([urllib.error.HTTPError("u", 403, "Forbidden", {}, None)])
    error = check_raises(BlockedError, lambda: client.get_json("/x"), "403")
    check_equal(len(client.opener.requests), 1, "차단은 재시도하지 않는다 — 깊어지기만 한다")
    check("HTTP/2" in str(error), "이 사이트 고유의 원인을 알려야 한다: %s" % error)


def test_EXCEPTION_429_is_blocked():
    client = _client([urllib.error.HTTPError("u", 429, "Too Many", {}, None)])
    error = check_raises(BlockedError, lambda: client.get_json("/x"), "429")
    check("간격" in str(error), "무엇을 확인해야 하는지 알려야 한다")


def test_EXCEPTION_404_is_raised_as_is_not_retried():
    # 없는 공고를 세 번 물어봐야 세 번 없다. 재시도는 레이트리밋만 쓴다.
    client = _client([urllib.error.HTTPError("u", 404, "Not Found", {}, None)])
    check_raises(urllib.error.HTTPError, lambda: client.get_json("/x"), "404")
    check_equal(len(client.opener.requests), 1, "404 는 재시도하지 않는다")


def test_EXCEPTION_400_is_not_retried_either():
    # 결함이었던 곳: 접근할 수 없는 공고가 404 가 아니라 **400** 으로 온다 (id 1614345).
    # 404 만 막아 두면 그런 공고 하나에 요청 3개를 쓰고, 그만큼 차단에 가까워진다.
    client = _client([urllib.error.HTTPError("u", 400, "Bad Request", {}, None)])
    check_raises(urllib.error.HTTPError, lambda: client.get_json("/x"), "400")
    check_equal(len(client.opener.requests), 1, "400 도 재시도하지 않는다")


def test_EXCEPTION_500_is_retried_then_gives_up():
    error = urllib.error.HTTPError("u", 500, "Server Error", {}, None)
    client = _client([error, error, error])
    check_raises(ConnectionError, lambda: client.get_json("/x"), "5xx 는 재시도 후 포기")
    check_equal(len(client.opener.requests), 3, "MAX_RETRIES 만큼 시도")


def test_EXCEPTION_transient_failure_recovers():
    client = _client([urllib.error.URLError("끊김"), '{"data":{"ok":1}}'])
    check_equal(client.get_json("/x"), {"ok": 1}, "한 번 실패해도 다음에 받는다")


def test_EXCEPTION_non_json_body_says_what_came_back():
    # Cloudflare 가 HTML 안내문을 200 으로 주는 일이 있다. 그때 무엇이 왔는지 보여야 한다.
    client = _client(["<!DOCTYPE html><title>Attention Required!</title>"])
    error = check_raises(ValueError, lambda: client.get_json("/x"), "JSON 이 아님")
    check("DOCTYPE" in str(error), "받은 것을 보여 줘야 한다: %s" % error)


def test_BOUNDARY_repeated_values_are_comma_joined():
    # 결함이 될 뻔한 곳: `a=1&a=2` 는 **마지막 값만** 먹는다. 실측으로 확인했다.
    check_equal(_query({"occupation_level2": ["11904", "11905"]}),
                "?occupation_level2=11904%2C11905", "콤마 하나로 이어야 한다")
    joined = urllib.parse.unquote(_query({"occupation_level2": ["11904", "11905"]}))
    check("occupation_level2=11904&occupation_level2=11905" not in joined,
          "같은 이름을 두 번 보내면 안 된다")


def test_BOUNDARY_empty_and_none_values_are_dropped():
    check_equal(_query({"a": "", "b": None, "c": "1"}), "?c=1", "빈 값은 안 싣는다")
    check_equal(_query({"a": ["", "  "]}), "", "전부 빈 목록도 안 싣는다")
    check_equal(_query({}), "", "빈 조건")
    check_equal(_query(None), "", "조건 없음")


def test_BOUNDARY_zero_is_a_value_not_emptiness():
    # `page=0` 이나 경력 `0` 이 거짓값이라고 빠지면 조건이 조용히 사라진다.
    check_equal(_query({"page": 0}), "?page=0", "0 은 값이다")


def test_BOUNDARY_rate_limit_waits_between_requests():
    slept = []
    client = JobPlanetClient(min_interval=1.2, sleep=slept.append)
    client.opener = FakeOpener(['{"data":{}}', '{"data":{}}'])
    client.get_json("/1")
    client.get_json("/2")
    check(any(seconds > 0 for seconds in slept),
          "두 번째 요청 전에 기다려야 한다: %r" % slept)
