"""점핏 응답 → CSV 한 줄.

**칸을 전부 API 가 채운다.** 30건 표본에서 지원자격·우대사항·담당업무·기술스택·근무지·
마감일이 **전부 100%** 였다. 네 사이트 중 가장 좋다 — HTML 을 긁거나 절을 가를 일이 없다.

**연봉은 없다.** 상세 43칸을 훑어도 급여 관련 필드가 하나도 없다. Wanted 와 같아서
빈칸으로 두고 스키마만 맞춘다.
"""
from __future__ import annotations

import re

from _common.store import COLUMNS

from . import skills as skills_module

SITE_NAME = "jumpit"
DETAIL_URL = "https://jumpit.saramin.co.kr/position/%s"

MAX_FIELD_LENGTH = 4000

DATE = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")

# 마감일이 없는 공고. `alwaysOpen` 이 참이거나 `closedAt` 이 비어 있다.
ALWAYS_OPEN = "상시채용"


def to_row(position: dict, detail: dict, *, candidates_file=None) -> dict:
    """목록 항목과 상세를 CSV 한 줄로.

    `id` 가 없으면 URL 을 만들 수 없다 — 키가 없는 행은 병합도 추적도 안 되므로
    조용히 빈 URL 을 넣지 않고 `ValueError` 를 낸다.
    """
    position_id = str(position.get("id") or "").strip()
    if not position_id:
        raise ValueError("id 가 없는 공고는 행으로 만들 수 없습니다: %r" % (position,))

    url = DETAIL_URL % position_id
    found = skills_module.extract_skills(position, detail, source_url=url,
                                         candidates_file=candidates_file)
    row = {
        "기업명": _text(detail.get("companyName")) or _text(position.get("companyName")),
        "마감일": format_deadline(detail, position),
        "지원자격": _trim(_text(detail.get("qualifications"))),
        "우대사항": _trim(_text(detail.get("preferredRequirements"))),
        "경력": career_text(detail, position),
        "URL": url,
        "연봉": "",          # 이 사이트는 급여를 안 준다 (상세 43칸에 없다)
        "기술스택": ", ".join(found),
        "근무지": workplace(detail, position),
        "사이트명": SITE_NAME,
    }
    return {column: row.get(column, "") for column in COLUMNS}


def _text(value) -> str:
    if value is None:
        return ""
    # 본문이 `\r\n` 으로 온다. 줄바꿈은 살리고 잡공백만 줄인다 — 절이 눈에 보여야 한다.
    return re.sub(r"[ \t]+", " ", str(value).replace("\r\n", "\n").replace("\r", "\n")).strip()


def _trim(text: str) -> str:
    if len(text) <= MAX_FIELD_LENGTH:
        return text
    return text[:MAX_FIELD_LENGTH].rstrip() + " …"


def format_deadline(detail: dict, position: dict) -> str:
    """마감일 → `YYYY-MM-DD`. 상시채용이면 그렇게 적는다.

    `closedAt` 이 상세는 `2026-09-18 23:59:59`, 목록은 `2026-09-18T23:59:59` 로 온다 —
    구분자 하나가 다르다. 날짜만 쓰므로 둘 다 같은 정규식으로 잡힌다.
    """
    for source in (detail, position):
        if source.get("alwaysOpen"):
            return ALWAYS_OPEN
    for source in (detail, position):
        found = DATE.search(_text(source.get("closedAt")))
        if found:
            year, month, day = found.groups()
            return "%s-%02d-%02d" % (year, int(month), int(day))
    return ALWAYS_OPEN


def career_text(detail: dict, position: dict) -> str:
    """경력. `minCareer`~`maxCareer` 를 사람이 읽는 말로.

    **`newcomer` 를 먼저 본다.** 신입 공고는 `minCareer` 가 0 인데, 0 을 거짓으로 다루면
    조용히 빈칸이 된다 — 실제로 `career=0` 결과 57건이 전부 `newcomer=true` 였다.
    """
    for source in (detail, position):
        if source.get("newcomer"):
            return "신입"
    for source in (detail, position):
        low, high = source.get("minCareer"), source.get("maxCareer")
        if low is None and high is None:
            continue
        if low is None or high is None:
            return "%d년 이상" % (high if low is None else low)
        if low == high:
            return "%d년" % low
        return "%d~%d년" % (low, high)
    return ""


def workplace(detail: dict, position: dict) -> str:
    """근무지. 상세의 `location` 이 `"서울 강남구 삼성로524 세화빌딩, 5층"` 처럼 자세하다.

    없으면 `workingPlaces` 나 목록의 `locations`(`["서울 강남구"]`)로 물러선다.
    """
    location = _text(detail.get("location"))
    if location:
        return location
    places = detail.get("workingPlaces")
    if isinstance(places, list):
        joined = ", ".join(_text(p.get("address")) for p in places
                           if isinstance(p, dict) and _text(p.get("address")))
        if joined:
            return joined
    for source in (detail, position):
        spots = source.get("locations")
        if isinstance(spots, list) and spots:
            return ", ".join(_text(s) for s in spots if _text(s))
    return ""
