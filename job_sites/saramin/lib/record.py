"""사람인 응답 → CSV 한 줄.

Wanted 는 API 가 `requirements` `preferred_points` 를 따로 준다. 사람인은 **회사가 쓴
HTML 한 덩어리**뿐이라 절을 직접 갈라야 한다. 공고 131건 실측:

    자격 머리말 있음        104건 (79%)
    우대 머리말 있음         82건 (63%)
    본문은 있는데 머리말 없음    2건 ( 2%)
    본문이 이미지            24건 (18%)

**본문이 이미지인 공고는 그림 주소를 기술스택 칸에 남긴다.** 수집을 돌 때는 그림을
읽지 않는다 — 장당 40초라 수집이 몇 시간이 된다. 전량을 걷은 뒤 따로 한 번에 읽는다.

**머리말이 없으면 지원자격에 본문 전체를 넣는다.** 회사가 절을 안 나눴을 뿐 내용은 거기
있다. 우대사항은 없으면 **빈칸**이다 — 지원자격을 복사해 넣으면 없는 구분을 지어내는 것이다.

목록에서 오는 값(기업명·근무지·경력·마감일)은 131/131 로 채워지므로 그쪽을 먼저 쓰고,
상세는 목록이 못 주는 것(지원자격·우대사항·연봉)에만 쓴다.
"""
from __future__ import annotations

import re

from _common.html_text import visible_lines
from _common.sections import MAX_FIELD_LENGTH, split_body_text
from _common.store import COLUMNS

from . import body, skills

SITE_NAME = "saramin"
DETAIL_URL = "https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=%s"

# 급여의 **금액 부분만**. 같은 칸에 최저임금 안내문이 통째로 붙어 오는데
# (`... 주 40시간 기준 최저임금은 25,882,560원 입니다 ...`) 그걸 같이 넣으면
# 연봉 칸이 문단이 되고, 거기 든 다른 숫자가 급여로 읽힌다.
SALARY_AMOUNT = re.compile(r"(연봉|월급|주급|일급|시급)\s*([\d,]+)\s*(만원|원)")


def to_row(listing: dict, page: str = "", image_urls: list[str] | None = None) -> dict:
    """목록 항목 하나와 상세 페이지를 CSV 한 줄로.

    `rec_idx` 가 없으면 URL 을 만들 수 없다 — 키가 없는 행은 병합도 추적도 안 되므로
    조용히 빈 URL 을 넣지 않고 `ValueError` 를 낸다.

    `image_urls` 는 **아직 안 읽은 이미지 본문의 주소**다. 기술스택 칸 뒤에 그대로
    남긴다 — 스키마를 안 늘리면서 "여기는 나중에 그림을 읽어야 한다" 를 표시한다.
    `http` 로 시작하므로 기술 이름과 섞일 일이 없다.
    """
    rec_idx = str(listing.get("rec_idx") or "").strip()
    if not rec_idx:
        raise ValueError("rec_idx 가 없는 공고는 행으로 만들 수 없습니다: %r" % (listing,))

    qualification, preference = split_sections(page)
    row = {
        "기업명": listing.get("기업명", ""),
        "마감일": find_deadline(page, listing.get("마감일", "")),
        "지원자격": qualification,
        "우대사항": preference,
        "경력": format_career(listing.get("경력", "")),
        "URL": DETAIL_URL % rec_idx,
        "연봉": find_salary(page),
        "기술스택": ", ".join(skills.extract_skills(page) + list(image_urls or [])),
        "근무지": find_workplace(page, listing.get("근무지", "")),
        "사이트명": SITE_NAME,
    }
    return {column: row.get(column, "") for column in COLUMNS}


def split_sections(page: str) -> tuple[str, str]:
    """본문을 (지원자격, 우대사항) 으로 가른다.

    **어디서 글을 뽑을지만 여기서 정한다.** 사람인은 본문 컨테이너 안이다.
    가르는 규칙 자체는 한국 채용공고 일반의 말이라 `_common/sections.py` 에 있다.
    """
    return split_body_text(visible_lines(body.body_html(page or "")))


# 상세의 접수기간에 있는 **절대 날짜**. 목록 카드보다 이쪽이 낫다.
DETAIL_DEADLINE = re.compile(r"마감일\s*(\d{4})\.(\d{2})\.(\d{2})")


def find_deadline(page: str, fallback: str = "") -> str:
    """마감일. **상세의 절대 날짜를 먼저 쓴다.**

    목록 카드는 `D-5` `내일마감` 처럼 **상대 표기**로 줄 때가 있다 (122건 중 49건).
    그 값은 저장한 다음 날이면 거짓이 된다 — 누적 CSV 는 30일을 보존하는데
    거기 든 `D-5` 는 아무 뜻이 없다.

    상세에는 `마감일 2026.09.10 18:00` 이 있고, 목록이 날짜로 준 것과도 맞는다
    (표본 4/4 일치). 그래서 상세를 먼저 보고, 없을 때만 목록 값을 쓴다.

    상세에도 없으면 `상시채용` `채용시` 처럼 **마감일이 실제로 없는 공고**다.
    그때는 목록 문구를 그대로 둔다 — 없는 날짜를 지어내지 않는다.
    """
    found = DETAIL_DEADLINE.search(re.sub(r"<[^>]+>", " ", page or ""))
    if found:
        return "%s-%s-%s" % found.groups()
    return format_deadline(fallback)


def format_deadline(raw: str) -> str:
    """목록 카드의 마감 표기를 다듬는다. 상세에 날짜가 없을 때만 쓴다.

    `~09.14(월)` → `09-14`. 연도가 없으므로 **붙이지 않는다** — 12월에 본 `01.05` 를
    올해로 붙이면 이미 지난 날짜가 된다. `상시채용` `채용시` 는 원문 그대로 둔다.
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    found = re.search(r"(\d{1,2})\s*[./-]\s*(\d{1,2})", raw)
    if found:
        return "%02d-%02d" % (int(found.group(1)), int(found.group(2)))
    return re.sub(r"\s+", " ", raw)


# 목록 카드의 `career` 칸은 경력과 고용형태를 한 줄에 섞어 준다 — `신입 · 경력 · 정규직 외`.
# 고용형태는 사람인이 정한 **닫힌 12개**라 목록으로 적어도 새 값이 안 늘어난다.
# 첫 조각만 취하면 `신입 · 경력` 에서 "경력" 이 사라진다.
EMPLOYMENT_TYPE_WORDS = frozenset(
    "정규직 계약직 아르바이트 인턴직 프리랜서 파트 위촉직 파견직 전임 병역특례 교육생 해외취업".split())


def format_career(raw: str) -> str:
    """`신입 · 경력 · 정규직 외` → `신입 · 경력`. 고용형태는 이 칸의 값이 아니다."""
    text = re.sub(r"\s+", " ", (raw or "").strip())
    if not text:
        return ""
    kept = [part.strip() for part in text.split("·")]
    kept = [part for part in kept
            if part and part.replace(" 외", "").strip() not in EMPLOYMENT_TYPE_WORDS]
    return " · ".join(kept)


def summary_field(page: str, label: str) -> str:
    """핵심 정보 표(`jv_summary`)의 한 칸. `<dt>이름</dt><dd>값</dd>` 구조다.

    `이름 ... 값` 으로 느슨하게 잡으면 **빈 문자열이 잡힌다** — `급여` 바로 뒤에 오는 것은
    값이 아니라 `</dt>` 라서, 게으른 수량자가 아무것도 안 먹고 `<dd>` 앞에서 멈춘다.
    실제로 131건 전부에서 칸은 찾았는데 값이 0건이었다. **`<dd>` 를 명시해야 한다.**
    """
    found = re.search(r"<dt>\s*%s\s*</dt>\s*<dd>(.*?)</dd>" % re.escape(label),
                      page or "", re.DOTALL)
    if not found:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", found.group(1))).strip()


def find_salary(page: str) -> str:
    """핵심 정보 표의 급여. **실금액일 때만** 채운다.

    대부분 "면접 후 결정" 이다. 그런 문구를 넣으면 연봉 칸이 값처럼 보이지만
    걸러 낼 수도 비교할 수도 없다 — 빈칸이 정직하다 (D-10).
    """
    found = SALARY_AMOUNT.search(summary_field(page, "급여"))
    return "%s %s%s" % found.groups() if found else ""


def find_workplace(page: str, fallback: str = "") -> str:
    """근무지. 상세의 `근무지역` 이 목록보다 정확하다.

    목록은 `서울전체 외` 인데 상세는 `서울 강서구, 서울전체` 다. 상세가 없을 때만
    목록 값을 쓴다.
    """
    text = summary_field(page, "근무지역")
    # `지도보기` 같은 버튼 글자가 딸려 온다
    text = re.sub(r"\s*(지도보기|주변정보|약도)\s*$", "", text).strip(" ,")
    return text or fallback
