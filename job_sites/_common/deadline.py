"""마감일 칸을 **계약이 정한 말**로 옮긴다.

계약(`docs/convention/02-data-contract.md`)은 `YYYY-MM-DD`, 마감일이 없으면 `상시채용`
하나만 인정한다. 그런데 사람인은 사이트 문구인 `채용시` 를 그대로 내보냈다 —
실측(2026-09-09) 735행에서 `상시채용` 104건과 `채용시` 39건이 **같은 뜻으로 따로** 있었다.

**날짜는 절대 건드리지 않는다.** 이 단계가 하는 일은 "마감일이 없다" 는 여러 말을
한 말로 모으는 것뿐이다. 날짜로 안 읽히는데 "없다" 는 뜻도 아닌 글은 **그대로 둔다** —
모르는 글을 `상시채용` 으로 바꾸면 진짜 마감일을 지우게 된다.
"""
from __future__ import annotations

import re

ALWAYS = "상시채용"

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 마감일이 없다는 뜻으로 채용 사이트들이 쓰는 말. **닫힌 집합이 아니므로**
# 여기 없는 말은 지어내지 않고 그대로 남긴다 — 남으면 눈에 띄어 여기에 더할 수 있다.
_NO_DEADLINE = ("상시", "채용시", "채용 시", "수시", "충원시", "충원 시", "마감시", "마감 시")


def standard(raw: str | None) -> str:
    """마감일 하나를 계약이 정한 말로. 빈 값은 `상시채용`."""
    text = re.sub(r"\s+", " ", (raw or "")).strip()
    if not text:
        return ALWAYS
    if _DATE.match(text):
        return text
    stripped = text.replace(" ", "")
    if any(word.replace(" ", "") in stripped for word in _NO_DEADLINE):
        return ALWAYS
    return text
