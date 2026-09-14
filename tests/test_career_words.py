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
