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
from _common.store import COLUMNS

from . import body, skills

SITE_NAME = "saramin"
DETAIL_URL = "https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=%s"

# 절 머리말. **닫힌 부류가 아니라 관측치**라 놓치는 것이 있을 수 있다 —
# 그래서 못 찾으면 본문 전체를 지원자격으로 돌린다. 틀린 절 구분을 만들지 않는다.
QUALIFICATION_HEADING = re.compile(
    r"(자격\s*요건|지원\s*자격|자격\s*조건|자격\s*사항|필수\s*요건|필수\s*사항"
    r"|이런\s*분을\s*찾|이런\s*분과)")
PREFERENCE_HEADING = re.compile(
    r"(우대\s*사항|우대\s*요건|우대\s*조건|우대\s*능력|이런\s*분이면\s*더|이런\s*경험)")
# 절이 끝나는 곳. 다음 절이 시작되면 앞 절은 거기서 끝난다.
OTHER_HEADING = re.compile(
    r"(담당\s*업무|주요\s*업무|모집\s*부문|모집\s*분야|근무\s*조건|근무\s*환경"
    r"|전형\s*절차|채용\s*절차|제출\s*서류|접수\s*방법|접수\s*기간|복리\s*후생"
    r"|기타\s*사항|유의\s*사항|문의)")

# 한 칸에 넣을 글의 상한. 넘치면 CSV 를 사람이 못 읽고, 엑셀도 잘라 버린다.
MAX_FIELD_LENGTH = 4000

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

    머리말을 못 찾으면 **본문 전체를 지원자격으로** 돌린다 — 내용은 거기 있는데
    우리가 못 나눈 것뿐이다. 우대사항은 못 찾으면 빈칸이다.
    """
    text = visible_lines(body.body_html(page or ""))
    if not text:
        return "", ""
    qualification = _section(text, QUALIFICATION_HEADING)
    preference = _section(text, PREFERENCE_HEADING)
    if not qualification:
        # 자격 머리말이 없다 — 회사가 절을 안 나눴을 뿐 내용은 본문에 있다.
        # 다만 우대사항을 따로 뽑아 놨다면 **거기서 끊는다.** 안 그러면 같은 글이
        # 두 칸에 겹쳐 들어가 CSV 를 읽는 사람이 무엇이 자격인지 못 가린다.
        qualification = _until_first_heading(text, PREFERENCE_HEADING) if preference else text
    return _trim(qualification), _trim(preference)


def _until_first_heading(text: str, heading: re.Pattern[str]) -> str:
    """머리말이 처음 나오는 줄 앞까지."""
    kept = []
    for line in text.split("\n"):
        if heading.search(line) and not _is_column_header(line):
            break
        if line.strip():
            kept.append(line.strip())
    return "\n".join(kept).strip()


def _heading_kinds(line: str) -> int:
    """이 줄이 몇 종류의 절 이름을 담고 있는가."""
    return sum(bool(pattern.search(line)) for pattern in
               (QUALIFICATION_HEADING, PREFERENCE_HEADING, OTHER_HEADING))


def _is_column_header(line: str) -> bool:
    """절 이름을 여럿 나열한 줄 — 절의 시작이 아니라 **표의 열 머리글**이다.

    사람인 양식의 모집부문 표는 `모집분야 업무내용 자격요건 및 우대조건` 같은 줄로
    시작한다. 이걸 절 시작으로 보면 자격과 우대가 **같은 자리에서 시작해 같은 글을
    담는다** — 실제로 두 칸에 똑같은 내용이 들어간 행이 9건 나왔다.

    절 이름 하나만 든 줄은 진짜 머리말이다. 둘 이상이면 머리글이다.
    """
    return _heading_kinds(line) > 1


def _is_heading(line: str) -> bool:
    """어느 절이든 머리말인가.

    자기 머리말과 `OTHER_HEADING` 만 보면 **지원자격이 우대사항을 삼킨다** —
    우대사항은 둘 중 어디에도 없기 때문이다. 절의 끝은 "다음 머리말" 이지
    "내가 아는 다른 머리말" 이 아니다.
    """
    return bool(QUALIFICATION_HEADING.search(line)
                or PREFERENCE_HEADING.search(line)
                or OTHER_HEADING.search(line))


def _section(text: str, heading: re.Pattern[str]) -> str:
    """머리말이 있는 줄 다음부터, **다음 머리말이 나오기 전까지**."""
    lines = text.split("\n")
    start = next((index for index, line in enumerate(lines)
                  if heading.search(line) and not _is_column_header(line)), None)
    if start is None:
        return ""
    collected = []
    # 머리말 줄에 값이 같이 붙어 있는 경우가 있다 — `자격요건 : 대졸 이상`
    tail = heading.split(lines[start], maxsplit=1)[-1].lstrip(" :·-|]）)")
    if tail.strip():
        collected.append(tail.strip())
    for line in lines[start + 1:]:
        if _is_heading(line) and not _is_column_header(line):
            break
        if line.strip():
            collected.append(line.strip())
    return "\n".join(collected).strip()


def _trim(text: str) -> str:
    if len(text) <= MAX_FIELD_LENGTH:
        return text
    return text[:MAX_FIELD_LENGTH].rstrip() + " …"


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
