"""테스트 공용 도구. 네트워크를 타지 않는다."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"


def responses() -> dict:
    """실제 MCP 응답을 떠 놓은 것. 어떤 사례인지는 각 항목의 `why` 에 적혀 있다."""
    return json.loads((FIXTURES / "responses.json").read_text(encoding="utf-8"))


def listing_text() -> str:
    """목록 글 — `이번 페이지 N개` 와 `다음 페이지: offset=` 이 들어 있다."""
    return responses()["listing"]["text"]


def empty_text() -> str:
    """끝 너머 — `검색 결과가 없습니다.` 안내문뿐이다."""
    return responses()["listing_empty"]["text"]


def detail_text() -> str:
    """상세 글 — 라벨 칸과 `[상세 내용]` 절이 다 들어 있다."""
    return responses()["detail"]["text"]


def env_file(text: str) -> Path:
    path = Path(tempfile.mkdtemp()) / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def temp_json() -> Path:
    """후보 파일 자리. **생산 파일에 쓰지 않으려고** 테스트마다 새로 만든다."""
    return Path(tempfile.mkdtemp()) / "candidates.json"


class Failure(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


def check_equal(actual, expected, message: str = "") -> None:
    if actual != expected:
        raise Failure("%s\n      기대: %r\n      실제: %r" % (message, expected, actual))


def check_raises(exception_type, call, message: str = ""):
    try:
        call()
    except exception_type as error:
        return error
    raise Failure("%s\n      %s 가 나야 하는데 조용히 지나갔다"
                  % (message, exception_type.__name__))
