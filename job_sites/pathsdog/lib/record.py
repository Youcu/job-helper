"""MCP 상세 글 → CSV 한 줄.

응답이 라벨 붙은 글이라 줄 단위로 읽는다.

    📋 ㈜네비웍스 - AI 서비스 백엔드 개발자(신입)
    [기본 정보]
    - 기술스택: Backend, AI/ML, Python, React, Docker
    - 필수 기술: Python 개발 유경험자, Linux 서버 활용 가능자, …
    - 우대 기술: AI관련 개발 유경험자, …
    - 경력: 신입
    - 연봉: 회사 내규에 따름
    - 근무지: 대한민국 경기도 안양시 …
    [일정]
    - 서류 마감: 2026-09-28
    [상세 내용]
    (원문 전체)

## `필수 기술`·`우대 기술` 은 기술이 아니다

이름과 달리 **지원자격 문장을 콤마로 자른 것**이다. 실제로 이렇게 온다 —
`Python 개발 유경험자`, `병역특례 대상자`, `진짜 '성공'을 만들고자 하는 열망이 강한 분`.
게다가 `제출서류`, `절차안내`, `서류전형 > 온라인 테스트` 같은 전형 정보까지 섞인다.

그래서 지원자격·우대사항은 **원문(`[상세 내용]`)을 절로 갈라** 채우고, 절을 못 찾았을
때만 이 칸으로 물러선다. 진짜 기술 태그는 `- 기술스택:` 쪽이다.

## 근무지 표기가 제각각이다

한 조건 29건에서 서로 다른 표기가 20가지였다 — `서울`, `판교`, `미기재`, 전체 주소,
건물 이름(`넛지캠퍼스빌딩`), 심지어 파싱이 어긋난 문장까지. 서버가 지역을 못 걸러
우리가 걸러야 하는데, 이 들쭉날쭉함이 그 일을 어렵게 만든다.
"""
from __future__ import annotations

import re

from _common.sections import split_body_text
from _common.store import COLUMNS

from . import skills as skills_module

SITE_NAME = "pathsdog"
DETAIL_URL = "https://jobs.pathsdog.com/jobs/%s"

MAX_FIELD_LENGTH = 4000

# `- 라벨: 값` 한 줄.
FIELD = "- %s:"
# 원문 절. `[상세 내용]` 부터 꼬리말 앞까지.
BODY = re.compile(r"\[상세 내용\]\s*\n(.*?)(?=\nPathsdog가 기업의|\Z)", re.DOTALL)
# 머리줄. `📋 ㈜네비웍스 - AI 서비스 백엔드 개발자(신입)`
HEAD = re.compile(r"^\s*📋\s*(.+)$", re.MULTILINE)

DATE = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")
# 급여가 실금액인지. `회사 내규에 따름` 이 대부분이라 숫자가 있어야만 받는다.
SALARY_AMOUNT = re.compile(r"([\d,]{3,})\s*(만원|원)")

# 값이 없다는 뜻으로 서버가 쓰는 말. 그대로 CSV 에 넣으면 값처럼 보인다.
BLANKS = frozenset({"미기재", "없음", "-", "회사 내규에 따름", "협의"})

# 원문 맨 앞에 붙는 **메타데이터 줄**. 공고 내용이 아니라 서버가 정리해 둔 요약이라,
# 절 머리말을 못 찾았을 때 이것까지 지원자격으로 들어간다 — 실제로 그랬다.
META_LINE = re.compile(
    r"^\s*(공고명|회사|모집분야|고용형태|근무지|경력|연봉|마감일|지원\s*기간|접수\s*기간)"
    r"\s*[:：]", re.MULTILINE)


def to_row(listing: dict, detail: str, *, candidates_file=None) -> dict:
    """목록 항목과 상세 글을 CSV 한 줄로.

    `id` 가 없으면 URL 을 만들 수 없다 — 키가 없는 행은 병합도 추적도 안 되므로
    조용히 빈 URL 을 넣지 않고 `ValueError` 를 낸다.
    """
    job_id = str(listing.get("id") or "").strip()
    if not job_id:
        raise ValueError("id 가 없는 공고는 행으로 만들 수 없습니다: %r" % (listing,))

    url = listing.get("상세주소") or (DETAIL_URL % job_id)
    qualification, preference = split_sections(detail)
    found = skills_module.extract_skills(listing, detail, source_url=url,
                                         candidates_file=candidates_file)
    row = {
        "기업명": company_name(detail) or listing.get("기업명", ""),
        "마감일": format_deadline(detail, listing),
        "지원자격": _trim(qualification),
        "우대사항": _trim(preference),
        "경력": field(detail, "경력") or _from_conditions(listing, 0),
        "URL": url,
        "연봉": find_salary(detail),
        "기술스택": ", ".join(found),
        "근무지": workplace(detail, listing),
        "사이트명": SITE_NAME,
    }
    return {column: row.get(column, "") for column in COLUMNS}


def field(detail: str, label: str) -> str:
    """`- 라벨: 값` 한 줄에서 값만. **`미기재` 같은 말은 빈칸으로 돌린다.**"""
    head = FIELD % label
    for line in (detail or "").split("\n"):
        stripped = line.strip()
        if stripped.startswith(head):
            value = stripped[len(head):].strip()
            return "" if value in BLANKS else value
    return ""


def company_name(detail: str) -> str:
    """머리줄의 회사 이름. `📋 ㈜네비웍스 - AI 서비스 백엔드 개발자(신입)`"""
    found = HEAD.search(detail or "")
    if not found:
        return ""
    company, _, title = found.group(1).partition(" - ")
    return company.strip() if title else ""


def full_description(detail: str) -> str:
    """`[상세 내용]` 절의 원문. 없으면 빈 문자열.

    **맨 앞의 메타데이터 줄은 뗀다.** 원문이 `공고명: … / 회사: … / 고용형태: …` 로
    시작하는데, 그건 서버가 정리해 둔 요약이지 공고 내용이 아니다. 절 머리말을 못 찾으면
    본문 전체가 지원자격이 되므로(그게 `split_body_text` 의 설계다) 이것까지 딸려 들어간다.
    """
    found = BODY.search(detail or "")
    if not found:
        return ""
    return _without_meta_head(found.group(1).strip())


def _without_meta_head(text: str) -> str:
    """앞머리의 `라벨: 값` 줄들을 건너뛴다. 그런 줄이 안 나오면 거기서 본문이 시작한다."""
    lines = text.split("\n")
    start = 0
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if META_LINE.match(line):
            start = index + 1
            continue
        break
    return "\n".join(lines[start:]).strip()


def split_sections(detail: str) -> tuple[str, str]:
    """지원자격·우대사항. **원문 절 나누기가 먼저다.**

    라벨 칸(`- 필수 기술:`)은 이름과 달리 지원자격 문장을 콤마로 자른 것이고 전형 절차·
    제출 서류까지 섞여 있다. 원문에서 절을 찾으면 그쪽이 훨씬 깨끗하다.

    절을 못 찾았을 때만 라벨 칸으로 물러선다 — 지저분해도 빈칸보다는 낫다.
    """
    qualification, preference = split_body_text(full_description(detail))
    if not qualification:
        qualification = field(detail, "필수 기술")
    if not preference:
        preference = field(detail, "우대 기술")
    return qualification, preference


def format_deadline(detail: str, listing: dict) -> str:
    """마감일 → `YYYY-MM-DD`. 상세의 `서류 마감` 이 먼저, 없으면 목록의 `마감`."""
    for value in (field(detail, "서류 마감"), listing.get("마감", "")):
        found = DATE.search(str(value or ""))
        if found:
            year, month, day = found.groups()
            return "%s-%02d-%02d" % (year, int(month), int(day))
    return ""


def find_salary(detail: str) -> str:
    """연봉. **실금액일 때만** 채운다.

    `회사 내규에 따름` 이 대부분이라 `field` 가 이미 빈칸으로 돌리지만, `연봉 협의 후
    결정` 처럼 다른 문구도 온다. 숫자가 있어야만 받는다 (D-10).
    """
    found = SALARY_AMOUNT.search(field(detail, "연봉"))
    return "%s%s" % found.groups() if found else ""


def workplace(detail: str, listing: dict) -> str:
    """근무지. 상세가 먼저, 없으면 목록의 조건 줄에서."""
    place = field(detail, "근무지")
    if place:
        return place
    found = re.search(r"근무지:\s*([^|]+)", listing.get("조건", "") or "")
    value = found.group(1).strip() if found else ""
    return "" if value in BLANKS else value


def matches_locations(row: dict, wanted: list[str]) -> bool:
    """근무지가 조건에 맞는가. **조건이 없으면 전부 통과한다.**

    `search_jobs` 에 지역 파라미터가 없어서 여기서 거른다. 표기가 20가지로 제각각이라
    (`서울` · `판교` · 전체 주소 · 건물 이름) 이름을 그대로 견주되 `시`·`구` 를 뗀 것도 본다.

    **근무지가 비면 통과시킨다.** 29건 중 4건이 `미기재` 였다 — 잘못 버리는 것보다
    넘기는 쪽이 낫다. 버린 공고는 있었다는 사실조차 남지 않는다.
    """
    if not wanted:
        return True
    place = row.get("근무지") or ""
    if not place.strip():
        return True
    return any(_place_matches(place, name) for name in wanted)


def matches_employment(detail: str, wanted: list[str]) -> bool:
    """고용형태가 조건에 맞는가. **조건이 없거나 값이 비면 통과한다.**

    서버 `employment_type` 은 값 하나만 받아서 `정규직,인턴` 중 하나를 잃는다. 그래서
    안 보내고 여기서 거른다 — 근무지와 같은 이유다.

    값이 비면 통과시킨다. 잘못 버리는 것보다 넘기는 쪽이 낫다.
    """
    if not wanted:
        return True
    value = field(detail, "고용형태")
    if not value:
        return True
    return any(name in value for name in wanted)


def _place_matches(place: str, name: str) -> bool:
    name = " ".join(name.split())
    if not name or name == "전국":
        return True
    if name in place:
        return True
    stem = re.sub(r"(특별시|광역시|특별자치시|특별자치도|시|군|구|도)$", "", name)
    return bool(stem) and stem in place


def _from_conditions(listing: dict, index: int) -> str:
    """목록의 조건 줄 `신입 | 근무지: … | 정규직` 에서 index 번째 조각."""
    parts = [p.strip() for p in (listing.get("조건", "") or "").split("|")]
    return parts[index] if index < len(parts) else ""


def _trim(text: str) -> str:
    if len(text) <= MAX_FIELD_LENGTH:
        return text
    return text[:MAX_FIELD_LENGTH].rstrip() + " …"
