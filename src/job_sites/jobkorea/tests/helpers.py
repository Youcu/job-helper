"""테스트 공용 도구. 네트워크를 타지 않는다."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"


def pages() -> dict[str, dict]:
    """실제 공고를 떠 놓은 것. 어떤 사례인지는 각 항목의 `why` 에 적혀 있다."""
    return json.loads((FIXTURES / "pages.json").read_text(encoding="utf-8"))


def detail(gno: str) -> str:
    return pages()[gno]["detail"]


def body_html(gno: str) -> str:
    return pages()[gno]["body"]


def listing_fragment() -> str:
    return pages()["_listing_fragment"]["fragment"]


def img(src: str, extra: str = "") -> str:
    return '<img src="%s"%s>' % (src, (" " + extra) if extra else "")


def json_ld(payload: dict) -> str:
    """상세 페이지에 박히는 구조화 데이터 한 덩이."""
    return ('<script type="application/ld+json">%s</script>'
            % json.dumps(payload, ensure_ascii=False))


def posting(**fields) -> str:
    data = {"@context": "https://schema.org", "@type": "JobPosting"}
    data.update(fields)
    return json_ld(data)


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
    raise Failure("%s\n      %s 가 나야 하는데 조용히 지나갔다" % (message, exception_type.__name__))
