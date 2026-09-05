"""테스트 공용 도구. 네트워크를 타지 않는다."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"


def detail_pages() -> dict[str, dict]:
    """실제 공고 3건을 떠 놓은 것. 어떤 사례인지는 각 항목의 `why` 에 적혀 있다."""
    return json.loads((FIXTURES / "detail_pages.json").read_text(encoding="utf-8"))


def page(rec_idx: str) -> str:
    return detail_pages()[rec_idx]["page"]


def tag_link(code: str, label: str = "이름") -> str:
    """상세 아래쪽 `#태그` 링크 한 줄."""
    return (
        '<a href="/zf_user/jobs/list/job-category?cat_kewd=%s" target="_blank">#%s</a>'
        % (code, label)
    )


def body(inner_html: str, rec_idx: str = "1234") -> str:
    """본문 컨테이너로 감싼다."""
    return '<div class="user_content jobsViewDetail_%s">%s</div>' % (rec_idx, inner_html)


class Failure(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


def check_equal(actual, expected, message: str = "") -> None:
    if actual != expected:
        raise Failure("%s\n      기대: %r\n      실제: %r" % (message, expected, actual))
