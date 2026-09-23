"""테스트 공용 도구. 네트워크를 타지 않는다."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"


def responses() -> dict:
    """실제 응답을 떠 놓은 것. 어떤 사례인지는 각 항목의 `why` 에 적혀 있다."""
    return json.loads((FIXTURES / "responses.json").read_text(encoding="utf-8"))


def listing_data() -> dict:
    """목록 응답 — `techStacks` 가 **문자열 배열**로 온다."""
    return responses()["listing"]["data"]


def position() -> dict:
    return listing_data()["positions"][0]


def detail() -> dict:
    """상세 — `techStacks` 가 **객체 배열**이고 본문 네 칸이 다 찼다."""
    return responses()["detail"]["data"]


def empty_listing() -> dict:
    """끝 너머 — `emptyPosition=true` 이고 **`totalCount` 까지 0** 이다."""
    return responses()["listing_empty"]["data"]


def env_file(text: str) -> Path:
    path = Path(tempfile.mkdtemp()) / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def temp_json() -> Path:
    """후보 파일 자리. **생산 파일에 쓰지 않으려고** 테스트마다 새로 만든다 —
    사람인에서 테스트가 진짜 `corpus_candidates.json` 을 더럽힌 적이 있다."""
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
