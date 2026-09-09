"""경력 칸을 **계약이 정한 말**로 옮긴다.

사이트마다 경력을 다르게 말한다. 사람인은 `신입 · 경력`, 잡코리아는 `신입·경력` —
가운뎃점 띄어쓰기만 다른 같은 뜻이 CSV 두 곳에 따로 실렸다. 실측(2026-09-09) 735행에서
**311건이 그렇게 쪼개져 있었다.** 합쳐 놓고 경력으로 거르거나 묶을 수가 없다.

계약(`docs/convention/02-data-contract.md`)이 정한 말은 이것뿐이다.

    신입 · 신입~N년 · A~B년 · N년 · N년 이상 · 경력무관

**목록이 아니라 규칙으로 옮긴다.** 사이트가 쓰는 문구를 적어 두고 맞추면 다음 문구에서
뚫린다. 여기서는 글에서 *뜻*을 읽는다 — 숫자가 있으면 범위로, 신입과 경력을 함께
받는다고 하면 `경력무관` 으로.

**못 읽으면 `경력무관`.** 계약이 정한 기본값이고, 뜻이 "따지지 않는다" 라서 모르는 것을
그 자리에 두어도 거짓이 되지 않는다. 없는 연차를 지어내는 것보다 낫다.
"""
from __future__ import annotations

import re

UNKNOWN = "경력무관"
ENTRY = "신입"

# `3~10년` `3-10년` `3 ~ 10년`
_RANGE = re.compile(r"(\d{1,2})\s*[~\-–]\s*(\d{1,2})\s*년")
# `3년 이상` `3년↑` `3년 이상~` `경력 3년+`
_ATLEAST = re.compile(r"(\d{1,2})\s*년\s*(?:이상|↑|\+|~)")
_YEARS = re.compile(r"(\d{1,2})\s*년")

# 연차를 뜻하지 않는 숫자+년. `2년제` 는 학력이고 `3년간` 은 기간 설명이다.
_NOT_CAREER = re.compile(r"\d{1,2}\s*년(제|간|차\s*이내)")


def standard(raw: str | None) -> str:
    """사이트 문구 하나를 계약이 정한 말로. 못 읽으면 `경력무관`."""
    text = re.sub(r"\s+", " ", (raw or "")).strip()
    if not text:
        return UNKNOWN
    if "무관" in text:
        return UNKNOWN
    if _NOT_CAREER.search(text):
        text = _NOT_CAREER.sub(" ", text)

    entry = ENTRY in text
    # **`경력` 이라는 낱말만으로는 안 된다** — `경력무관` 도 `경력 3년` 도 그 말을 담는다.
    # 신입과 나란히 놓였을 때만 "둘 다 받는다" 는 뜻이다.
    experienced = bool(re.search(r"(^|[\s·,/|])경력([\s·,/|]|$)", text))
    if entry and experienced:
        return UNKNOWN

    found = _RANGE.search(text)
    if found:
        low, high = sorted(int(n) for n in found.groups())
        if low == high:
            return "%d년" % low if low else ENTRY
        return "%s~%d년" % (ENTRY if low == 0 else "%d" % low, high)

    found = _ATLEAST.search(text)
    if found:
        years = int(found.group(1))
        return ENTRY if years == 0 else "%d년 이상" % years

    found = _YEARS.search(text)
    if found:
        years = int(found.group(1))
        if entry:
            return "%s~%d년" % (ENTRY, years) if years else ENTRY
        return ENTRY if years == 0 else "%d년" % years

    if entry:
        return ENTRY
    return UNKNOWN
