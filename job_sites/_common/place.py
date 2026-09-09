"""근무지 칸의 **맨 앞 시도 이름**을 한 가지 표기로 모은다.

계약(`docs/convention/02-data-contract.md`)은 `시도 구 상세주소` 를 요구한다. 그런데
근무지의 상당 부분이 **회사가 자유롭게 적은 주소**라, 같은 시도가 여러 이름으로 온다 —
실측(2026-09-09) 735행에서 `서울` 539 · `서울특별시` 27 · `서울시` 17 로 쪼개져 있었다.
지역으로 묶으면 44건이 새어 나간다.

**시도 17개는 닫힌 집합이다.** 행정구역이라 관측으로 늘어나지 않는다. 그래서 여기서는
목록을 써도 다음 케이스에서 뚫리지 않는다 (`saramin` 의 고용형태 12개와 같은 이유).

**맨 앞 낱말만 본다.** 주소 안쪽은 건드리지 않는다 — `서울 강남구 서울대로` 의 뒤쪽
`서울` 까지 바꾸면 주소가 망가진다.
"""
from __future__ import annotations

import re

# 짧은 이름 → 그 시도를 가리키는 다른 표기들. 행정구역 17개, 닫힌 집합이다.
SIDO = {
    "서울": ("서울특별시", "서울시"),
    "부산": ("부산광역시", "부산시"),
    "대구": ("대구광역시", "대구시"),
    "인천": ("인천광역시", "인천시"),
    "광주": ("광주광역시", "광주시"),
    "대전": ("대전광역시", "대전시"),
    "울산": ("울산광역시", "울산시"),
    "세종": ("세종특별자치시", "세종시"),
    "경기": ("경기도",),
    "강원": ("강원특별자치도", "강원도"),
    "충북": ("충청북도", "충북도"),
    "충남": ("충청남도", "충남도"),
    "전북": ("전북특별자치도", "전라북도", "전북도"),
    "전남": ("전라남도", "전남도"),
    "경북": ("경상북도", "경북도"),
    "경남": ("경상남도", "경남도"),
    "제주": ("제주특별자치도", "제주도"),
}

# 긴 표기가 먼저 걸리도록 길이 내림차순으로 본다 — `서울시` 를 `서울` 로 먼저 자르면
# 뒤에 `시` 가 남는다.
_LONG_TO_SHORT = sorted(
    ((long, short) for short, longs in SIDO.items() for long in longs),
    key=lambda pair: -len(pair[0]))

# 사람인 목록 카드가 쓰는 `서울전체` 꼴. 시도 뒤에 붙는 군말이라 뗀다.
_ALL = re.compile(r"^(.+?)전체$")

# 잡코리아 구조화 데이터가 앞에 붙이는 나라 이름. 전부 국내 공고라 뜻이 없다 —
# 붙어 있으면 그 뒤의 시도를 못 보고 지나친다 (`대한민국 서울특별시 서초구 …`).
_COUNTRY = ("대한민국", "한국", "Korea", "South Korea")


def standard(text: str | None) -> str:
    """근무지의 맨 앞 시도 이름을 짧은 표기로. 그 밖은 그대로 둔다."""
    place = re.sub(r"\s+", " ", (text or "")).strip()
    if not place:
        return ""
    for country in _COUNTRY:
        if place.startswith(country + " "):
            place = place[len(country) + 1:]
            break
    head, sep, rest = place.partition(" ")
    head = _short(head)
    return head + sep + rest


def _short(head: str) -> str:
    bare, comma = (head[:-1], head[-1]) if head.endswith(",") else (head, "")
    found = _ALL.match(bare)
    if found:
        bare = found.group(1)
        comma = ""            # `서울전체,` 는 목록 표기의 흔적이라 쉼표까지 뗀다
    if bare in SIDO:
        return bare + comma
    for long, short in _LONG_TO_SHORT:
        if bare == long:
            return short + comma
    return head
