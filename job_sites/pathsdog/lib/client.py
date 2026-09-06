"""Pathsdog MCP 클라이언트.

**다섯 사이트 중 유일하게 공식 인터페이스를 준다.** HTML 을 긁거나 비공개 API 를 찾아
헤맬 필요가 없다 — `https://jobs.pathsdog.com/mcp` 가 MCP(Model Context Protocol)
서버이고, `search_jobs` · `get_job_detail` 두 도구로 목록과 상세를 받는다.

    POST /mcp   JSON-RPC 2.0
      initialize        → 서버 정보와 protocolVersion
      tools/call        → {"name": "search_jobs", "arguments": {...}}

인증도 쿠키도 필요 없다. 웹 쪽 `/api/jobs` 는 **401** 이라 오히려 MCP 가 유일한 길이다.

## 응답이 사람이 읽는 글이다

MCP 는 LLM 이 읽으라고 만든 것이라 구조화 JSON 이 아니라 **라벨 붙은 글**을 준다.

    [ID:2565] ㈜네비웍스 - AI 서비스 백엔드 개발자(신입)
      기술: Backend, AI/ML, Python, React, Docker
      경력: 신입 | 근무지: 대한민국 경기도 안양시 … | 정규직

서식이 규칙적이라 파싱은 되지만 **JSON 보다 깨지기 쉽다.** 그래서 `collect.py` 가
읽어 낸 개수를 서버가 말한 개수와 매번 대조한다 — 서식이 바뀌면 거기서 드러난다.

## 세션 헤더가 필요 없다

MCP 명세는 `Mcp-Session-Id` 를 쓸 수 있게 해 두었는데, 이 서버는 `initialize` 응답에
세션을 주지 않고 그 뒤 `tools/call` 도 그냥 받는다. 그래도 `initialize` 는 보낸다 —
명세가 요구하는 첫 인사이고, 서버가 나중에 세션을 요구하게 바뀌면 그때 받아 둘 자리다.
"""
from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.request

MCP_URL = "https://jobs.pathsdog.com/mcp"
PROTOCOL_VERSION = "2025-06-18"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
)
# **`text/event-stream` 을 받겠다고 해야 한다.** 안 그러면 서버가 406 으로 거절한다
# (`Not Acceptable: Client must accept text/event-stream`).
HEADERS = {
    "User-Agent": USER_AGENT,
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

MIN_INTERVAL = 0.4
JITTER = 0.3
TIMEOUT = 60
MAX_RETRIES = 3

# 다시 물어봐야 답이 같은 코드. **없는 공고를 세 번 물어봐야 세 번 없다** — 재시도는
# 레이트리밋만 태운다. 잡플래닛에서 접근 불가 공고 하나에 요청 3개를 쓰다 그만큼
# 차단에 가까워진 적이 있다. 5xx 는 여기 안 넣는다 — 그건 다시 물으면 될 수 있다.
NO_RETRY_CODES = frozenset({400, 404, 410})

# 응답이 SSE(`data: {...}`)로 올 수도, 순수 JSON 으로 올 수도 있다. 둘 다 받는다.
SSE_DATA = re.compile(r"^data:\s*(\{.*)$", re.MULTILINE)


class BlockedError(RuntimeError):
    """차단으로 보이는 응답. **재시도하지 않는다** — 재시도하면 차단만 깊어진다."""


class ToolError(RuntimeError):
    """서버가 도구 호출을 거절했다. 인자가 틀렸거나 그런 도구가 없다."""


class PathsdogClient:
    """MCP 서버에 도구를 부른다. 요청 사이에 간격을 둔다."""

    def __init__(self, *, min_interval: float = MIN_INTERVAL, sleep=time.sleep):
        self.opener = urllib.request.build_opener()
        self.min_interval = min_interval
        self._sleep = sleep
        self._last_request_at = 0.0
        self._next_id = 0
        self._session: str | None = None
        self._greeted = False

    def initialize(self) -> dict:
        """MCP 첫 인사. 서버 정보를 돌려준다."""
        answer = self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "analyze-company", "version": "1.0.0"},
        })
        self._greeted = True
        return answer

    def call_tool(self, name: str, arguments: dict) -> str:
        """도구를 부르고 **글 하나로 이어 붙여** 돌려준다.

        `content` 는 조각 목록으로 오는데, 지금 서버는 늘 글 하나만 보낸다. 여럿이 와도
        잃지 않도록 이어 붙인다 — 조각이 늘면 조용히 앞부분만 읽는 일이 생긴다.
        """
        if not self._greeted:
            self.initialize()
        answer = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if answer.get("isError"):
            raise ToolError("%s 호출을 서버가 거절했습니다: %s"
                            % (name, _texts(answer) or answer))
        text = _texts(answer)
        if not text:
            raise ToolError("%s 가 글을 하나도 안 돌려줬습니다: %r" % (name, answer))
        return text

    def _rpc(self, method: str, params: dict) -> dict:
        self._next_id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self._next_id,
                           "method": method, "params": params}).encode("utf-8")
        raw = self._send(body)
        try:
            payload = json.loads(_json_part(raw))
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError("MCP 응답이 JSON 이 아닙니다 (앞부분: %r)"
                             % raw[:160]) from error
        if "error" in payload:
            error = payload["error"]
            raise ToolError("MCP 오류 %s: %s"
                            % (error.get("code"), error.get("message")))
        return payload.get("result", {})

    def _send(self, body: bytes) -> str:
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            self._wait_turn()
            headers = dict(HEADERS)
            if self._session:
                headers["Mcp-Session-Id"] = self._session
            try:
                request = urllib.request.Request(MCP_URL, data=body, headers=headers)
                with self.opener.open(request, timeout=TIMEOUT) as response:
                    session = response.headers.get("mcp-session-id")
                    if session:
                        self._session = session
                    return response.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as error:
                if error.code in (403, 429):
                    raise BlockedError(
                        "Pathsdog 가 %d 로 막았습니다.\n"
                        "  이 서버는 차단이 관측되지 않던 곳입니다 — 무언가 바뀌었을 수 있습니다.\n"
                        "  · 요청 간격(%.1f초)을 줄이지는 않았는지 확인하세요."
                        % (error.code, self.min_interval)) from error
                if error.code == 406:
                    raise ValueError(
                        "서버가 406 을 냈습니다 — Accept 헤더에 `text/event-stream` 이 "
                        "빠졌는지 확인하세요 (이 서버는 그것을 요구합니다).") from error
                if error.code in NO_RETRY_CODES:
                    raise
                last_error = error
            except (urllib.error.URLError, OSError) as error:
                last_error = error
            self._sleep(self.min_interval * (2 ** attempt))
        raise ConnectionError("MCP 를 %d번 시도해도 못 받았습니다: %s"
                              % (MAX_RETRIES, last_error))

    def _wait_turn(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.min_interval + random.uniform(0, JITTER) - elapsed
        if remaining > 0:
            self._sleep(remaining)
        self._last_request_at = time.monotonic()


def _json_part(raw: str) -> str:
    """SSE 로 오면 `data:` 줄에서, 아니면 통째로."""
    found = SSE_DATA.search(raw or "")
    return found.group(1) if found else (raw or "")


def _texts(answer: dict) -> str:
    """`content` 조각들의 글을 이어 붙인다."""
    parts = []
    for piece in answer.get("content") or []:
        if isinstance(piece, dict) and piece.get("type") == "text":
            parts.append(piece.get("text") or "")
    return "\n".join(p for p in parts if p).strip()
