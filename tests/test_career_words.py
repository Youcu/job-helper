"""경력 거르기의 **말 규칙** — 누구를 모델에게 물어볼지 가리는 자.

여기가 너무 넓으면 **모델 호출이 돈으로 새고**, 너무 좁으면 모순된 공고를 놓친다.
그런데 둘 중에는 넓은 쪽이 안전하다 — 판정은 모델이 하고, 여기서 걸린 것이 곧
제외가 아니기 때문이다.

실측 문자열은 전부 `csv/merged_core.csv` 66행에서 나온 것이다.
"""
from __future__ import annotations

import career_words as words

from .helpers import check, check_equal


# ── 일반 ────────────────────────────────────────────────────────────────

def test_NORMAL_site_says_newbie_can_apply():
    # 실측 66행에 나온 표기 전부. 띄어쓰기가 사이트마다 흔들린다.
    for value in ("신입", "신입 · 경력", "신입·경력", "경력무관", "경력 무관",
                  "신입~5년", "신입~10년"):
        check(words.accepts_newbie(value), "신입이 지원할 수 있다: %r" % value)


def test_NORMAL_a_year_requirement_is_found():
    for line in ("• 웹서비스 개발 경력 4년 이상",
                 "• Python 기반 백엔드 개발 경력 2년 이상",
                 "ㆍ제품개발 경력이 5~10년 정도",
                 "• 관련 직무 3년 이상 경험자",
                 "• 경력 3년이상"):
        check_equal(words.demands_years(line), line.strip(), "연수를 요구한다: %r" % line)


# ── 예외 ────────────────────────────────────────────────────────────────

def test_EXCEPTION_experience_is_not_a_career_length():
    """**"경험" 과 "경력 연수" 는 다른 것이다** (2026-09-13 사용자).

    신입도 프로젝트·학습으로 경험을 가진다. 여기를 못 가리면 신입 가능 66행 중
    **42행(64%)** 이 후보가 된다 — 실측이다. 모델 호출이 네 배로 는다.
    """
    for line in ("• 백엔드 아키텍처, DB Schema 설계 및 개발 경험이 있으신 분",
                 "ㆍ JAVA / Kotlin - Spring Framework 개발에 능숙한 분",
                 "• 대용량 실시간 어플리케이션/시스템 아키텍쳐 지식과 경험이 있으신 분",
                 "ㆍ설계부터 출시까지 기술적 자립이 가능하신 분"):
        check_equal(words.demands_years(line), None, "역량이지 경력이 아니다: %r" % line)


def test_EXCEPTION_degrees_and_dates_are_not_career_years():
    """`4년제` 는 학력이고 `27년 2월` 은 날짜다. 잡으면 멀쩡한 신입 공채가 사라진다."""
    for line in ("• 대학교졸업(4년)이상, 졸업 예정자 지원가능",
                 "• 4년제 대학에서 컴퓨터공학, 소프트웨어공학을 전공하고 졸업하신 분",
                 "• 4년제 정규대학 기졸업자 또는 27년 2월 졸업예정자 중 26년 11월 입사 가능자",
                 "- 4년제 대학 졸업자 이상"):
        check_equal(words.demands_years(line), None, "학력·날짜다: %r" % line)


def test_EXCEPTION_missing_fields_do_not_crash():
    check_equal(words.accepts_newbie(None), False, "빈 경력 칸")
    check_equal(words.demands_years(None), None, "빈 지원자격")
    check_equal(words.candidate({}), None, "칸이 아예 없어도 터지면 안 된다")


# ── 경계 ────────────────────────────────────────────────────────────────

def test_BOUNDARY_a_newbie_path_on_the_same_line_is_not_a_contradiction():
    """같은 줄에 신입이 적혀 있으면 **신입도 받는다는 뜻**이다.

    이 규칙 하나로 후보 14행이 9행이 된다 (실측). 없으면 `신입 / 경력 1년 이상`
    같은 멀쩡한 공고를 모델에게 물어보게 된다.
    """
    for line in ("• 신입 또는 백엔드 개발 경력 5년 내외이신 분",
                 "• 신입 / 경력 1년 이상 ~ 3년 이하",
                 "• 신입/경력 2년 이상 ~ 9년 이하",
                 "• 경력 무관 (신입 지원 가능)"):
        check_equal(words.demands_years(line), None, "신입 경로가 있다: %r" % line)


def test_BOUNDARY_experienced_only_postings_are_not_candidates():
    """사이트가 **경력만** 받는다고 적었으면 애초에 모순이 아니다. 물어볼 일이 없다."""
    for value in ("경력", "경력 3년 이상", "1년~5년", ""):
        check(not words.accepts_newbie(value), "후보가 아니다: %r" % value)


def test_BOUNDARY_only_the_qualification_is_read():
    """**우대사항은 안 본다.** 우대는 없어도 지원할 수 있어 모순이 아니다.

    실측 `교보다솜케어`: 자격은 `경력 무관` 인데 우대에만 `경력 1년 이상` 이 있었다.
    우대까지 보면 이런 공고가 통째로 후보가 된다.
    """
    row = {"경력": "경력무관",
           "지원자격": "• 학력 무관\n• 경력 무관 (신입 지원 가능)",
           "우대사항": "• 웹 어플리케이션 개발 경력 1년 이상"}
    check_equal(words.candidate(row), None, "우대의 경력은 모순이 아니다")


def test_BOUNDARY_a_later_line_still_counts():
    """첫 줄이 멀쩡해도 **뒷줄에서 요구하면** 후보다.

    실측 `(주)일루니`: 첫 줄이 `신입 / 경력 2년 이상` 이라 넘어가지만, 아래에
    `소프트웨어 개발 경력 2년 이상 …` 이 따로 있다.
    """
    row = {"경력": "신입 · 경력",
           "지원자격": "• 신입 / 경력 2년 이상\n• 소프트웨어 개발 경력 2년 이상 보유하신 분"}
    got = words.candidate(row)
    check(got and "보유하신 분" in got, "뒷줄을 찾아야 한다: %r" % got)


# ── 대놓고 경력직인 공고 (`closed_to_newbie`) ────────────────────────────
#
# 여기 문자열은 전부 `csv/merged_role.csv` 588행에서 나온 것이다 — **`role.py` 가
# 고친 뒤의 값**이다. 사이트가 준 값에는 이런 모양이 안 나온다.

def test_NORMAL_a_career_only_field_is_closed():
    for value in ("경력 3년 이상", "경력 3년이상", "5년 이상", "4년 이상",
                  "경력 5년 이상", "서버관리 경력 5년 이상", "경력(5년 이상)",
                  "3~5년 경력자", "4년 ~ 10년", "4년~6년 이하", "경력(6년~12년)",
                  "3년이상 7년이하", "5년 이상 15년 이하", "경력 4년 이상 ~ 20년 이하"):
        check(words.closed_to_newbie(value), "경력직이다: %r" % value)


def test_NORMAL_every_part_must_be_closed():
    """부문이 여럿이면 **전부** 닫혀 있어야 뺀다. 실측 2건(청오디피케이·도미노피자)."""
    value = ("정보전략팀-백엔드: 6년 이상 / 플랫폼개발팀-백엔드: 3년 이상 / "
             "플랫폼개선팀-Java백엔드: 5년 이상 / 플랫폼개선팀-ReactJS프론트엔드: 8년 이상")
    check(words.closed_to_newbie(value), "네 부문이 다 경력직이다")


# ── 예외 ────────────────────────────────────────────────────────────────

def test_EXCEPTION_a_blank_career_field_is_not_a_career_posting():
    """**안 적힌 것을 경력직으로 읽으면 안 된다.**

    실측으로 `csv/merged_role.csv` 588행 중 20행이 빈 칸인데, 그건 수집이 본문을
    못 가져온 것이지 회사가 경력직이라고 말한 것이 아니다. 여기가 뚫리면 그 20행이
    근거 없이 사라진다.
    """
    for value in ("", "   ", None):
        check_equal(words.closed_to_newbie(value), None,
                    "빈 칸은 판단하지 않는다: %r" % value)


def test_EXCEPTION_a_field_without_years_is_not_closed():
    """연수가 없으면 닫혔다고 못 한다. `경력` 한 글자로는 아무것도 모른다."""
    for value in ("경력", "경력자", "개발자"):
        check_equal(words.closed_to_newbie(value), None, "연수가 없다: %r" % value)


# ── 경계 ────────────────────────────────────────────────────────────────

def test_BOUNDARY_one_open_part_keeps_the_whole_posting():
    """한 부문이라도 신입을 받으면 **그 자리로 지원한다.** 실측 5건."""
    for value in ("[Web 개발] 유관 경력 2년 이상 / [SW 개발(Server)] 신입 또는 경력 3년 이상",
                  "컨버전스개발팀(서버파트): 5년 이상 / "
                  "해외AP개발팀(SE파트): 신입 또는 경력(소프트웨어 개발) 2년 이상",
                  "경력(3년 이내) / 신입",
                  "경력 1년 이상 또는 신입",
                  "경력자 및 신입"):
        check_equal(words.closed_to_newbie(value), None, "신입 경로가 있다: %r" % value)


def test_BOUNDARY_a_slash_without_spaces_is_not_a_part_break():
    """`React/Spring Boot` 를 두 부문으로 가르면 안 된다.

    가르면 `React` 라는 빈 부문이 생기고 판단이 흔들린다. 실측 1건.
    """
    value = "React/Spring Boot 개발자: 4년 이상 경력자 (웹개발자·Backend 개발자는 경력 미기재)"
    check_equal(words.closed_to_newbie(value), None, "미기재가 있으니 남긴다")


def test_BOUNDARY_ambiguous_fields_are_kept():
    """**애매하면 남긴다** (2026-09-13 사용자). 지우는 판단에 "모르겠으면" 은 없다.

    `8~9년차 우대` 는 연수를 요구하는 것인지 선호하는 것인지 가를 신호가 없다.
    `경력 년수 무관` 은 무관이라 적었으니 열려 있다.
    """
    for value in ("8~9년차 우대", "경력 년수 무관"):
        check_equal(words.closed_to_newbie(value), None, "애매하면 남긴다: %r" % value)


def test_BOUNDARY_site_supplied_values_are_never_closed():
    """**사이트가 준 값에는 작동하지 않는다.**

    실측으로 `history/history_read.csv` 949행에 이 규칙을 대면 0건이다. 수집이
    검색에서 이미 신입으로 좁히기 때문이다. 이 성질이 깨지면 이 규칙이 예전
    파이프라인까지 거슬러 올라가 멀쩡한 행을 지운다.
    """
    for value in ("신입", "신입 · 경력", "신입·경력", "경력무관", "경력 무관",
                  "신입~5년", "신입~10년", "신입/경력", "신입, 경력"):
        check_equal(words.closed_to_newbie(value), None,
                    "사이트 값은 안 걸린다: %r" % value)


def test_BOUNDARY_the_reason_names_the_part_that_closed_it():
    """보고 CSV 에서 되짚으려면 **어느 부문이 닫았는지**가 나와야 한다."""
    check_equal(words.closed_to_newbie("경력 3년이상"), "경력 3년이상",
                "걸린 부문을 그대로 돌려준다")
