"""HTTP 클라이언트 — 차단 감지·재시도."""
from __future__ import annotations

import tempfile
from pathlib import Path

import requests

from lib import client as client_module
from lib.client import BlockedError, WantedClient
from tests.helpers import FakeResponse, assert_raises, make_client


def test_BOUNDARY_client_zero_retries():
    c = make_client([FakeResponse(200, {"ok": 1})], retries=0)
    assert_raises(RuntimeError, c.get_json, "/api/x", referer="r")
    assert c.session.requests == []


def test_EXCEPTION_client_403_is_blocked_error_with_a_hint():
    """403 은 재시도해도 소용없다. 즉시 멈추고 UA 를 의심하라고 알려야 한다."""
    c = make_client([FakeResponse(403)])
    try:
        c.get_json("/api/x", referer="r")
    except BlockedError as exc:
        assert "User-Agent" in str(exc) and "HeadlessChrome" in str(exc)
    else:
        raise AssertionError("BlockedError 가 나야 한다")
    assert len(c.session.requests) == 1, "403 에 재시도하면 차단만 깊어진다"


def test_EXCEPTION_client_4xx_other_than_403_is_raised():
    """404 를 재시도하는 건 낭비다. 그대로 올린다."""
    c = make_client([FakeResponse(404)])
    assert_raises(requests.HTTPError, c.get_json, "/api/x", referer="r")


def test_EXCEPTION_client_invalid_json_propagates():
    """본문이 JSON 이 아니면 삼키지 않는다 — 부르는 쪽이 이유를 남기고 멈춘다."""
    c = make_client([FakeResponse(200, ValueError("JSON 아님"))])
    assert_raises(ValueError, c.get_json, "/api/x", referer="r")


def test_EXCEPTION_client_recovers_on_retry():
    c = make_client([FakeResponse(429), FakeResponse(500), FakeResponse(200, {"ok": True})])
    assert c.get_json("/api/x", referer="r") == {"ok": True}
    assert len(c.session.requests) == 3


def test_EXCEPTION_client_retries_network_errors():
    c = make_client([requests.ConnectionError("끊김"), requests.Timeout("느림"),
                     FakeResponse(200, {"ok": 1})])
    assert c.get_json("/api/x", referer="r") == {"ok": 1}


def test_EXCEPTION_client_retries_then_gives_up():
    """429·5xx 는 재시도하되, 끝내 안 되면 조용히 빈 값을 주면 안 된다."""
    for status in (429, 500, 503):
        c = make_client([FakeResponse(status)] * 3, retries=3)
        assert_raises(RuntimeError, c.get_json, "/api/x", referer="r")
        assert len(c.session.requests) == 3


def test_NORMAL_client_returns_parsed_json():
    c = make_client([FakeResponse(200, {"data": [1, 2]})])
    assert c.get_json("/api/x", referer="r") == {"data": [1, 2]}


def test_NORMAL_client_sends_browser_headers_and_referer():
    """UA 에 `HeadlessChrome` 이 들어가면 CloudFront 가 403 을 준다 (실측).

    차단 회피의 전제라 헤더를 실제로 확인한다. 여기가 깨지면 수집이 통째로 멈춘다.
    """
    c = make_client([FakeResponse(200, {"data": []})])
    c.get_json("/api/x", params=[("a", "1")], referer="https://www.wanted.co.kr/wdlist/518")

    assert "HeadlessChrome" not in c.session.headers["User-Agent"]
    assert "Chrome/" in c.session.headers["User-Agent"]
    for header in ("Accept-Language", "sec-ch-ua", "sec-fetch-mode", "Origin"):
        assert header in c.session.headers, f"{header} 가 빠졌다"

    sent = c.session.requests[0]
    assert sent["url"] == "https://www.wanted.co.kr/api/x"
    assert sent["headers"]["Referer"] == "https://www.wanted.co.kr/wdlist/518"
    assert sent["timeout"] == 30, "타임아웃이 없으면 한 요청에 영원히 매달린다"
