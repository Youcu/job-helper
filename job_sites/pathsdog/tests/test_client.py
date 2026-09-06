"""MCP JSON-RPC 계층. 네트워크를 타지 않는다 — opener 를 가짜로 바꿔 넣는다.

**다섯 사이트 중 유일하게 공식 인터페이스를 쓴다.** 그래서 확인할 것도 다르다 —
JSON-RPC 규약을 지키는가, 서버가 요구하는 헤더를 보내는가, 오류를 오류로 알리는가.
"""
from __future__ import annotations

import json
import urllib.error

from lib.client import BlockedError, PathsdogClient, ToolError, _json_part, _texts

from .helpers import check, check_equal, check_raises


class FakeResponse:
    def __init__(self, text, headers=None):
        self._text = text
        self.headers = headers or {}

    def read(self):
        return self._text.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeOpener:
    def __init__(self, answers=None):
        self.requests = []
        self.answers = list(answers or [])

    def open(self, request, timeout=None):
        self.requests.append(request)
        answer = self.answers.pop(0) if self.answers else _ok({})
        if isinstance(answer, Exception):
            raise answer
        return FakeResponse(answer) if isinstance(answer, str) else answer


def _ok(result, rpc_id=1):
    return json.dumps({"jsonrpc": "2.0", "id": rpc_id, "result": result})


def _text_result(text):
    return _ok({"content": [{"type": "text", "text": text}]})


def _client(answers=None):
    client = PathsdogClient(min_interval=0, sleep=lambda _s: None)
    client.opener = FakeOpener(answers)
    return client


def _body(request) -> dict:
    return json.loads(request.data.decode("utf-8"))


def test_NORMAL_initialize_sends_the_protocol_version():
    client = _client([_ok({"protocolVersion": "2025-06-18"})])
    client.initialize()
    body = _body(client.opener.requests[0])
    check_equal(body["method"], "initialize", "첫 인사")
    check(body["params"]["protocolVersion"], "규약 버전을 밝혀야 한다")
    check(body["params"]["clientInfo"]["name"], "우리가 누구인지 밝혀야 한다")


def test_NORMAL_call_tool_returns_the_text():
    client = _client([_ok({}), _text_result("공고 목록")])
    check_equal(client.call_tool("search_jobs", {"limit": 5}), "공고 목록", "글을 그대로")
    body = _body(client.opener.requests[1])
    check_equal(body["method"], "tools/call", "도구 호출")
    check_equal(body["params"]["name"], "search_jobs", "도구 이름")
    check_equal(body["params"]["arguments"], {"limit": 5}, "인자")


def test_NORMAL_greets_before_the_first_tool_call():
    # MCP 는 initialize 를 먼저 요구한다. 도구부터 부르면 서버가 거절할 수 있다.
    client = _client([_ok({}), _text_result("x")])
    client.call_tool("search_jobs", {})
    check_equal(_body(client.opener.requests[0])["method"], "initialize", "먼저 인사")
    check_equal(len(client.opener.requests), 2, "인사 한 번 + 호출 한 번")


def test_NORMAL_sends_the_headers_the_server_demands():
    client = _client([_ok({})])
    client.initialize()
    headers = client.opener.requests[0].headers
    # 이 서버는 event-stream 을 받겠다고 해야 한다 — 아니면 406 이다.
    check("event-stream" in headers["Accept"], headers["Accept"])
    check("json" in headers["Content-type"], headers["Content-type"])


def test_NORMAL_ids_increase():
    client = _client([_ok({}), _text_result("a"), _text_result("b")])
    client.call_tool("t", {})
    client.call_tool("t", {})
    ids = [_body(r)["id"] for r in client.opener.requests]
    check_equal(ids, sorted(set(ids)), "id 가 겹치거나 거꾸로 가면 안 된다: %r" % ids)


def test_EXCEPTION_rpc_error_is_raised():
    client = _client([_ok({}), json.dumps(
        {"jsonrpc": "2.0", "id": 2, "error": {"code": -32602, "message": "그런 도구 없음"}})])
    error = check_raises(ToolError, lambda: client.call_tool("없는도구", {}), "RPC 오류")
    check("그런 도구 없음" in str(error), "서버 말을 그대로 보여야 한다: %s" % error)


def test_EXCEPTION_tool_error_flag_is_raised():
    client = _client([_ok({}), _ok({"isError": True,
                                    "content": [{"type": "text", "text": "인자가 틀렸습니다"}]})])
    error = check_raises(ToolError, lambda: client.call_tool("search_jobs", {}), "isError")
    check("인자가 틀렸습니다" in str(error), error)


def test_EXCEPTION_empty_content_is_an_error():
    # 글이 안 오면 파싱할 것이 없다. 빈 문자열을 돌려주면 "공고 0건" 으로 오해한다.
    client = _client([_ok({}), _ok({"content": []})])
    check_raises(ToolError, lambda: client.call_tool("search_jobs", {}), "빈 응답")


def test_EXCEPTION_403_is_blocked_and_not_retried():
    client = _client([urllib.error.HTTPError("u", 403, "Forbidden", {}, None)])
    error = check_raises(BlockedError, lambda: client.initialize(), "403")
    check_equal(len(client.opener.requests), 1, "차단은 재시도하지 않는다")
    check("관측되지 않던" in str(error), "이 서버는 차단이 없던 곳이다: %s" % error)


def test_EXCEPTION_406_says_what_header_is_missing():
    # 실제로 겪은 것 — Accept 에 event-stream 이 없으면 서버가 406 을 낸다.
    client = _client([urllib.error.HTTPError("u", 406, "Not Acceptable", {}, None)])
    error = check_raises(ValueError, lambda: client.initialize(), "406")
    check("event-stream" in str(error), "무엇이 빠졌는지 알려야 한다: %s" % error)


def test_EXCEPTION_500_is_retried_then_gives_up():
    boom = urllib.error.HTTPError("u", 500, "Server Error", {}, None)
    client = _client([boom, boom, boom])
    check_raises(ConnectionError, lambda: client.initialize(), "5xx 는 재시도 후 포기")
    check_equal(len(client.opener.requests), 3, "MAX_RETRIES 만큼")


def test_EXCEPTION_non_json_body():
    client = _client(["<html>점검 중</html>"])
    error = check_raises(ValueError, lambda: client.initialize(), "JSON 이 아님")
    check("html" in str(error).lower(), "받은 것을 보여 줘야 한다: %s" % error)


def test_BOUNDARY_sse_and_plain_json_both_parse():
    # 응답이 SSE(`data: {...}`)로 올 수도, 순수 JSON 으로 올 수도 있다.
    check_equal(_json_part('data: {"a":1}'), '{"a":1}', "SSE")
    check_equal(_json_part('{"a":1}'), '{"a":1}', "순수 JSON")
    check_equal(_json_part(''), '', "빈 응답")
    client = _client(['event: message\ndata: ' + _ok({"content": [{"type": "text", "text": "hi"}]})])
    client._greeted = True
    check_equal(client.call_tool("t", {}), "hi", "SSE 로 와도 읽어야 한다")


def test_BOUNDARY_multiple_content_pieces_are_joined():
    # 지금 서버는 글 하나만 보내지만, 조각이 늘면 조용히 앞부분만 읽게 된다.
    check_equal(_texts({"content": [{"type": "text", "text": "앞"},
                                    {"type": "text", "text": "뒤"}]}),
                "앞\n뒤", "이어 붙여야 한다")


def test_BOUNDARY_non_text_pieces_are_skipped():
    check_equal(_texts({"content": [{"type": "image", "data": "…"},
                                    {"type": "text", "text": "글"}]}),
                "글", "글이 아닌 조각은 건너뛴다")
    check_equal(_texts({}), "", "content 가 없어도 터지지 않는다")


def test_BOUNDARY_session_header_is_remembered_when_given():
    # 이 서버는 세션을 안 주지만, 주기 시작하면 따라가야 한다.
    client = _client([FakeResponse(_ok({}), {"mcp-session-id": "abc"}),
                      FakeResponse(_text_result("x"), {})])
    client.initialize()
    client.call_tool("t", {})
    check_equal(client.opener.requests[1].headers.get("Mcp-session-id"), "abc",
                "받은 세션을 다음 요청에 실어야 한다")


def test_BOUNDARY_rate_limit_waits_between_requests():
    slept = []
    client = PathsdogClient(min_interval=0.4, sleep=slept.append)
    client.opener = FakeOpener([_ok({}), _text_result("x")])
    client.initialize()
    client.call_tool("t", {})
    check(any(s > 0 for s in slept), "두 번째 요청 전에 기다려야 한다: %r" % slept)


def test_EXCEPTION_transient_network_failure_recovers():
    # 끊김은 재시도한다 — 차단과 달리 다시 물으면 될 수 있다.
    client = _client([urllib.error.URLError("끊김"), _ok({})])
    client.initialize()
    check_equal(len(client.opener.requests), 2, "한 번 실패하고 다음에 받는다")


def test_EXCEPTION_no_retry_codes_are_raised_at_once():
    # 없는 공고를 세 번 물어봐야 세 번 없다. 재시도는 레이트리밋만 쓴다 —
    # 잡플래닛에서 400 을 세 번 던지다 그만큼 차단에 가까워진 적이 있다.
    from lib.client import NO_RETRY_CODES
    for code in sorted(NO_RETRY_CODES):
        client = _client([urllib.error.HTTPError("u", code, "no", {}, None)])
        check_raises(urllib.error.HTTPError, lambda: client.initialize(), "%d" % code)
        check_equal(len(client.opener.requests), 1, "%d 는 재시도하지 않는다" % code)


def test_BOUNDARY_no_retry_codes_do_not_swallow_server_errors():
    # 5xx 는 재시도해야 한다. 목록을 너무 넓게 잡으면 일시적 오류를 한 번에 포기한다.
    from lib.client import NO_RETRY_CODES
    for code in (500, 502, 503):
        check(code not in NO_RETRY_CODES, "%d 는 재시도 대상이어야 한다" % code)
