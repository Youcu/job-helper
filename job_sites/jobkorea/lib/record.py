"""잡코리아 응답 → CSV 한 줄.

**칸 대부분을 JSON-LD 가 채운다.** 상세 페이지에 `schema.org/JobPosting` 이 박혀 있고,
공고 67건 전수에서 12칸이 100% 있었다.

    title · hiringOrganization · datePosted · validThrough · employmentType
    experienceRequirements · educationRequirements · jobLocation · identifier · url
    baseSalary 는 13/67 (19%)

Wanted 다음으로 좋은 조건이다. 사람인에서 마감일을 상세에서 다시 파싱하고
근무지를 두 군데서 맞춰야 했던 일이 여기서는 없다.

**본문은 따로 온다.** 지원자격·우대사항은 iframe 본문(`collect.fetch_body`)을 절로 갈라
채운다 — 사람인과 같은 방식이고, 머리말도 한국 채용공고 일반의 말이라 같은 것을 쓴다.
"""
from __future__ import annotations

import html as html_module
import json
import re

from _common.html_text import visible_lines
from _common.sections import MAX_FIELD_LENGTH, split_body_text
from _common.store import COLUMNS

from . import body as body_module
from . import skills

# 잡코리아 공고에서만 절을 끝내는 말. 여기 공고는 `포지션 소개` 로 절을 시작하는데,
# 사람인 표 양식은 `포지션 및 자격요건` 을 **열 머리글**로 써서 뜻이 정반대다.
# 실측 — 넣으면 잡코리아 23행에서 진짜 자격이 살고, 공통에 넣으면 사람인 27건이 깨진다.
EXTRA_HEADING = re.compile(r"(포지션)")

SITE_NAME = "jobkorea"
DETAIL_URL = "https://www.jobkorea.co.kr/Recruit/GI_Read/%s"

JSON_LD = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)

# 급여가 실금액인지. "회사 내규에 따름" 이 대부분이라 숫자가 있어야만 받는다.
SALARY_AMOUNT = re.compile(r"([\d,]{3,})\s*(만원|원)")


def to_row(listing: dict, detail_html: str = "", body_html: str = "",
           image_urls: list[str] | None = None) -> dict:
    """목록 항목 · 상세 · 본문을 CSV 한 줄로.

    `gno` 가 없으면 URL 을 만들 수 없다 — 키가 없는 행은 병합도 추적도 안 되므로
    조용히 빈 URL 을 넣지 않고 `ValueError` 를 낸다.
    """
    gno = str(listing.get("gno") or "").strip()
    if not gno:
        raise ValueError("gno 가 없는 공고는 행으로 만들 수 없습니다: %r" % (listing,))

    posting = job_posting(detail_html)
    qualification, preference = split_sections(body_html)
    found = skills.extract_skills(body_html) + list(image_urls or [])
    row = {
        "기업명": _organization(posting) or listing.get("기업명", ""),
        "마감일": format_deadline(posting.get("validThrough"), listing.get("마감일", "")),
        "지원자격": qualification,
        "우대사항": preference,
        "경력": posting.get("experienceRequirements") or _cell(listing, 0),
        "URL": DETAIL_URL % gno,
        "연봉": find_salary(posting, listing),
        "기술스택": ", ".join(dict.fromkeys(found)),
        "근무지": _location(posting) or _cell(listing, 2),
        "사이트명": SITE_NAME,
    }
    return {column: row.get(column, "") for column in COLUMNS}


def job_posting(detail_html: str) -> dict:
    """상세의 `schema.org/JobPosting`. 없으면 빈 사전 — 목록 값으로 메운다."""
    found = JSON_LD.search(detail_html or "")
    if not found:
        return {}
    try:
        data = json.loads(html_module.unescape(found.group(1)))
    except (json.JSONDecodeError, ValueError):
        # 구조화 데이터가 깨졌다고 수집이 멈추면 안 된다. 목록 값으로 채운다.
        return {}
    return data if data.get("@type") == "JobPosting" else {}


def _organization(posting: dict) -> str:
    org = posting.get("hiringOrganization") or {}
    return (org.get("name") or "").strip() if isinstance(org, dict) else ""


def _location(posting: dict) -> str:
    place = posting.get("jobLocation") or {}
    address = place.get("address") if isinstance(place, dict) else None
    if not isinstance(address, dict):
        return ""
    return re.sub(r"\s+", " ", (address.get("streetAddress") or "")).strip()


def _cell(listing: dict, index: int) -> str:
    """목록 카드의 조건 셀. **개수가 5~6개로 들쭉날쭉하다** — 연봉이 있는 공고만
    한 칸 더 붙는다. 그래서 없으면 빈칸이지 오류가 아니다."""
    cells = listing.get("조건") or []
    return cells[index] if index < len(cells) else ""


def split_sections(body_html: str) -> tuple[str, str]:
    """본문을 (지원자격, 우대사항) 으로 가른다.

    **어디서 글을 뽑을지만 여기서 정한다.** 잡코리아는 iframe 본문이 통째로 온다.
    가르는 규칙 자체는 한국 채용공고 일반의 말이라 `_common/sections.py` 에 있다.
    """
    return split_body_text(visible_lines(body_module.visible_body_html(body_html or "")),
                           extra_other=EXTRA_HEADING)


def format_deadline(valid_through: str | None, fallback: str = "") -> str:
    """마감일. **JSON-LD 의 절대 시각을 먼저 쓴다.**

    `validThrough` 가 `2026-09-30T23:59` 로 온다. 목록 카드는 `~09/30` 이라 연도가 없어
    12월에 본 `01/05` 를 올해로 붙이면 이미 지난 날짜가 된다. 그래서 상세를 먼저 본다.
    """
    if valid_through:
        found = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(valid_through))
        if found:
            return "%s-%s-%s" % found.groups()
    raw = re.sub(r"\s+", " ", (fallback or "").strip())
    if not raw:
        return ""
    found = re.search(r"(\d{1,2})\s*[./-]\s*(\d{1,2})", raw)
    if found:
        return "%02d-%02d" % (int(found.group(1)), int(found.group(2)))
    return raw


# JSON-LD 의 급여 단위. `unitText` 가 이 중 하나로 온다.
SALARY_PERIOD = {"YEAR": "연봉", "MONTH": "월급", "WEEK": "주급", "DAY": "일급", "HOUR": "시급"}


def _base_salary(posting: dict) -> str:
    """`baseSalary` → `연봉 3,000~5,001만원`. 원 단위로 오므로 만원으로 바꿔 적는다.

    실제 모양 — `{"value": {"unitText": "YEAR", "minValue": 30000000, "maxValue": 50010000}}`.
    `value.value` 하나가 아니라 **범위**로 온다.
    """
    base = posting.get("baseSalary")
    value = base.get("value") if isinstance(base, dict) else None
    if not isinstance(value, dict):
        return ""
    period = SALARY_PERIOD.get(str(value.get("unitText") or "").upper(), "")
    amounts = [value.get("value"), value.get("minValue"), value.get("maxValue")]
    numbers = [int(a) for a in amounts if isinstance(a, (int, float)) and a > 0]
    if not numbers:
        return ""
    low, high = min(numbers), max(numbers)
    span = ("%s만원" % format(low // 10000, ",") if low == high
            else "%s~%s만원" % (format(low // 10000, ","), format(high // 10000, ",")))
    return ("%s %s" % (period, span)).strip()


def find_salary(posting: dict, listing: dict) -> str:
    """연봉. **실금액일 때만** 채운다.

    JSON-LD 의 `baseSalary` 가 19%(13/67)에 있다. 없으면 목록 조건 셀에 `3,400만원 이상`
    이 끼어 있을 때가 있어 거기서도 찾는다. "회사 내규에 따름" 같은 문구는 빈칸이다 —
    값처럼 보이지만 걸러 낼 수도 비교할 수도 없다 (D-10).
    """
    amount = _base_salary(posting)
    if amount:
        return amount
    for cell in listing.get("조건") or []:
        found = SALARY_AMOUNT.search(cell)
        if found:
            return "%s%s" % found.groups()
    return ""
