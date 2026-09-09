"""잡플래닛 응답 → CSV 한 줄.

**칸을 전부 상세 API 가 채운다.** 자체 공고는 본문 네 칸과 기술스택을 100% 갖고 있어
HTML 을 긁거나 절을 가를 일이 없다 — 사람인·잡코리아에서 하던 일의 대부분이 여기서는
사라진다. 대신 이 사이트만의 일이 둘 있다.

## 근무지를 우리가 거른다

잡플래닛 지역 코드는 **시도까지만** 있다. `성남시` 를 조건으로 걸 수 없어서 `경기` 로
넓게 받고, 받은 뒤 `location` 글로 거른다 (`matches_locations`). 거르는 자리를 옮긴 것이지
조건을 버린 것이 아니다.

## 마감일 표기가 두 가지다

목록은 `end_at: "2026-09-06"`, 상세는 `end_at: "2026.09.15"` 로 온다. 같은 이름인데
구분자가 다르다 — 하나만 가정하면 조용히 원문을 그대로 흘린다.
"""
from __future__ import annotations

import re

from _common.store import COLUMNS

from . import skills as skills_module

SITE_NAME = "jobplanet"
# 공고 주소. `share_link` 는 추적 파라미터가 잔뜩 붙은 단축 주소라, 그것이 향하는
# 깨끗한 주소를 직접 만든다.
DETAIL_URL = "https://www.jobplanet.co.kr/job/search?posting_ids%%5B%%5D=%s"

MAX_FIELD_LENGTH = 4000

# 급여가 실금액인지. "회사 내규에 따름" 이나 `" (  ~  )"` 같은 빈 껍데기가 대부분이다.
SALARY_AMOUNT = re.compile(r"([\d,]{3,})\s*(만원|원)")

DATE = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")


def to_row(posting: dict, detail: dict, *, candidates_file=None) -> dict:
    """목록 항목과 상세를 CSV 한 줄로.

    `id` 가 없으면 URL 을 만들 수 없다 — 키가 없는 행은 병합도 추적도 안 되므로
    조용히 빈 URL 을 넣지 않고 `ValueError` 를 낸다.
    """
    posting_id = str(posting.get("id") or "").strip()
    if not posting_id:
        raise ValueError("id 가 없는 공고는 행으로 만들 수 없습니다: %r" % (posting,))

    url = DETAIL_URL % posting_id
    found = skills_module.extract_skills(detail, source_url=url,
                                         candidates_file=candidates_file)
    row = {
        "기업명": _text(detail.get("name")) or _company_name(posting),
        "공고명": _text(detail.get("title")) or _text(posting.get("title")),
        "마감일": format_deadline(detail.get("end_at") or posting.get("end_at")),
        "지원자격": _trim(_text(detail.get("required_qualification"))),
        "우대사항": _trim(_text(detail.get("preferred_skill"))),
        "경력": career_text(detail, posting),
        "URL": url,
        "연봉": find_salary(detail),
        "기술스택": ", ".join(found),
        "근무지": workplace(detail, posting),
        "사이트명": SITE_NAME,
    }
    return {column: row.get(column, "") for column in COLUMNS}


def _text(value) -> str:
    if value is None:
        return ""
    return re.sub(r"[ \t]+", " ", str(value)).strip()


def _trim(text: str) -> str:
    if len(text) <= MAX_FIELD_LENGTH:
        return text
    return text[:MAX_FIELD_LENGTH].rstrip() + " …"


def _company_name(posting: dict) -> str:
    company = posting.get("company")
    return _text(company.get("name")) if isinstance(company, dict) else ""


def format_deadline(value) -> str:
    """마감일 → `YYYY-MM-DD`.

    **같은 `end_at` 인데 목록은 `2026-09-06`, 상세는 `2026.09.15` 로 온다.**
    구분자를 하나만 가정하면 원문이 그대로 흘러 CSV 안에서 두 표기가 섞인다.
    """
    raw = _text(value)
    if not raw:
        return ""
    found = DATE.search(raw)
    if not found:
        return raw
    year, month, day = found.groups()
    return "%s-%02d-%02d" % (year, int(month), int(day))


def career_text(detail: dict, posting: dict) -> str:
    """경력. `recruitment_text` 가 사람이 읽을 말(`"5 ~ 10년"`, `"신입"`)로 온다.

    없으면 `annual.text`(`"경력"`, `"신입"`)로 물러선다 — 덜 자세하지만 틀리지는 않는다.
    """
    for source in (detail, posting):
        parts = source.get("recruitment_text")
        if isinstance(parts, list) and parts:
            joined = ", ".join(_text(p) for p in parts if _text(p))
            if joined:
                return joined
    for source in (detail, posting):
        annual = source.get("annual")
        if isinstance(annual, dict) and _text(annual.get("text")):
            return _text(annual["text"])
    return ""


def find_salary(detail: dict) -> str:
    """연봉. **실금액일 때만** 채운다.

    대부분 `"-"` 나 `" (  ~  )"` 같은 빈 껍데기로 온다. 값처럼 보이지만 거를 수도
    비교할 수도 없으므로 빈칸으로 둔다 (D-10).
    """
    found = SALARY_AMOUNT.search(_text(detail.get("salary")))
    return "%s%s" % found.groups() if found else ""


def workplace(detail: dict, posting: dict) -> str:
    """근무지. 상세의 `location` 이 `"경기 수원시 영통구 영통2동"` 처럼 자세하다.

    없으면 `working_area`/`cities`(`["경기"]`)로 물러선다 — 시도까지밖에 없지만
    빈칸보다 낫고, 근무지로 거를 때도 쓰인다.
    """
    location = _text(detail.get("location"))
    if location:
        return location
    for source in (detail, posting):
        for key in ("working_area", "cities"):
            areas = source.get(key)
            if isinstance(areas, list) and areas:
                return ", ".join(_text(a) for a in areas if _text(a))
    return ""


def matches_locations(row: dict, wanted: list[str]) -> bool:
    """근무지가 조건에 맞는가. **조건이 없으면 전부 통과한다.**

    잡플래닛 지역 코드는 시도까지라 `성남시` 를 서버에 못 건다. 그래서 `경기` 로 넓게
    받고 여기서 근무지 글로 거른다. 이름을 그대로 견주되 `시`·`구` 를 뗀 것도 본다 —
    사람이 `성남시` 라고 적고 공고는 `경기 성남시 분당구` 라고 쓴다.

    **근무지가 비면 통과시킨다.** 잘못 버리는 것보다 넘기는 쪽이 낫다 — 사람이 URL 을
    열어 보면 알 수 있지만, 버린 공고는 있었다는 사실조차 남지 않는다.
    """
    if not wanted:
        return True
    place = row.get("근무지") or ""
    if not place.strip():
        return True
    return any(_place_matches(place, name) for name in wanted)


def _place_matches(place: str, name: str) -> bool:
    name = " ".join(name.split())
    if not name or name == "전국":
        return True
    if name in place:
        return True
    stem = re.sub(r"(특별시|광역시|특별자치시|특별자치도|시|군|구|도)$", "", name)
    return bool(stem) and stem in place
