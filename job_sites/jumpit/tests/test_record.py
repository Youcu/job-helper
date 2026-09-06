"""응답 → CSV 한 줄.

여기서 볼 것 셋 —

    `newcomer` 를 먼저 본다 — 신입 공고는 `minCareer` 가 **0** 이라, 0 을 거짓으로 다루면
      조용히 빈칸이 된다 (실측: `career=0` 결과 57건이 전부 `newcomer=true`)
    `closedAt` 의 구분자가 목록과 상세에서 다르다 (`T` vs 공백)
    **연봉은 아예 없다** — 상세 43칸에 급여 필드가 하나도 없다
"""
from __future__ import annotations

from _common.store import COLUMNS
from lib.record import (ALWAYS_OPEN, SITE_NAME, career_text, format_deadline,
                        to_row, workplace)

from .helpers import check, check_equal, check_raises, detail, position, temp_json


def test_NORMAL_row_has_every_column():
    row = to_row(position(), detail(), candidates_file=temp_json())
    check_equal(list(row), list(COLUMNS), "칸 이름과 순서가 스키마와 같아야 한다")
    check_equal(row["사이트명"], SITE_NAME, "사이트명")
    check(row["URL"].startswith("https://jumpit.saramin.co.kr/position/"), row["URL"])


def test_NORMAL_real_posting_fills_everything_but_salary():
    row = to_row(position(), detail(), candidates_file=temp_json())
    for column in ("기업명", "마감일", "지원자격", "우대사항", "경력", "근무지", "기술스택"):
        check(row[column].strip(), "%s 가 비었다" % column)
    check_equal(row["연봉"], "", "이 사이트는 급여를 안 준다")


def test_EXCEPTION_missing_id_raises():
    # 키가 없는 행은 병합도 추적도 안 된다. 조용히 빈 URL 을 넣으면 안 된다.
    check_raises(ValueError, lambda: to_row({"id": ""}, {}), "번호 없음")
    check_raises(ValueError, lambda: to_row({"id": None}, {}), "번호가 None")


def test_EXCEPTION_empty_detail_falls_back_to_listing():
    row = to_row({"id": 1, "companyName": "목록기업", "closedAt": "2026-09-18T23:59:59",
                  "locations": ["서울 강남구"], "newcomer": True}, {},
                 candidates_file=temp_json())
    check_equal(row["기업명"], "목록기업", "목록 값으로 메운다")
    check_equal(row["마감일"], "2026-09-18", "목록 마감일")
    check_equal(row["근무지"], "서울 강남구", "목록 근무지")
    check_equal(row["경력"], "신입", "목록 경력")


def test_BOUNDARY_newcomer_wins_over_zero_career():
    # 결함이 될 뻔한 곳: `minCareer=0` 을 거짓으로 다루면 신입이 빈칸이 된다.
    check_equal(career_text({"newcomer": True, "minCareer": 0, "maxCareer": 0}, {}),
                "신입", "신입 공고")
    check_equal(career_text({"newcomer": False, "minCareer": 0, "maxCareer": 3}, {}),
                "0~3년", "신입이 아닌데 0년부터")


def test_BOUNDARY_career_range_shapes():
    check_equal(career_text({"minCareer": 1, "maxCareer": 5}, {}), "1~5년", "범위")
    check_equal(career_text({"minCareer": 3, "maxCareer": 3}, {}), "3년", "같으면 하나로")
    check_equal(career_text({"minCareer": 3, "maxCareer": None}, {}), "3년 이상", "위가 없음")
    check_equal(career_text({"minCareer": None, "maxCareer": 5}, {}), "5년 이상", "아래가 없음")
    check_equal(career_text({}, {}), "", "아무것도 없음")


def test_BOUNDARY_two_deadline_separators():
    # 상세는 `2026-09-18 23:59:59`, 목록은 `2026-09-18T23:59:59` 로 온다.
    check_equal(format_deadline({"closedAt": "2026-09-18 23:59:59"}, {}), "2026-09-18", "상세")
    check_equal(format_deadline({}, {"closedAt": "2026-09-18T23:59:59"}), "2026-09-18", "목록")
    check_equal(format_deadline({"closedAt": "2026-9-5 00:00:00"}, {}), "2026-09-05",
                "한 자리 월·일도 채운다")


def test_BOUNDARY_always_open_has_no_deadline():
    check_equal(format_deadline({"alwaysOpen": True, "closedAt": "2026-09-18 00:00:00"}, {}),
                ALWAYS_OPEN, "상시채용이면 날짜를 안 적는다")
    check_equal(format_deadline({}, {}), ALWAYS_OPEN, "마감일이 없으면 상시채용")
    check_equal(format_deadline({"closedAt": ""}, {}), ALWAYS_OPEN, "빈 값")


def test_BOUNDARY_workplace_falls_back_in_order():
    check_equal(workplace({"location": "서울 강남구 삼성로524"}, {}), "서울 강남구 삼성로524",
                "자세한 주소")
    check_equal(workplace({"workingPlaces": [{"address": "서울 강남구"}]}, {}), "서울 강남구",
                "근무지 목록")
    check_equal(workplace({}, {"locations": ["서울 강남구", "경기 성남시"]}),
                "서울 강남구, 경기 성남시", "목록 값")
    check_equal(workplace({}, {}), "", "아무것도 없음")


def test_BOUNDARY_body_keeps_line_breaks():
    # 본문이 `\r\n` 으로 온다. 줄바꿈을 뭉개면 절이 한 줄로 붙어 사람이 못 읽는다.
    row = to_row({"id": 1, "techStacks": ["java"]},
                 {"qualifications": "• 첫째\r\n• 둘째\r\n• 셋째"},
                 candidates_file=temp_json())
    check_equal(row["지원자격"].count("\n"), 2, "줄바꿈이 살아야 한다: %r" % row["지원자격"])
    check("\r" not in row["지원자격"], "`\\r` 은 남기지 않는다")


def test_BOUNDARY_long_field_is_trimmed_with_a_mark():
    from lib.record import MAX_FIELD_LENGTH
    row = to_row({"id": 1, "techStacks": ["java"]},
                 {"qualifications": "가" * (MAX_FIELD_LENGTH + 500)},
                 candidates_file=temp_json())
    check(len(row["지원자격"]) <= MAX_FIELD_LENGTH + 2, len(row["지원자격"]))
    check(row["지원자격"].endswith("…"), "잘랐다는 표시가 있어야 한다")


def test_BOUNDARY_row_values_are_all_strings():
    row = to_row(position(), detail(), candidates_file=temp_json())
    for column, value in row.items():
        check(isinstance(value, str), "%s 가 문자열이 아니다: %r" % (column, value))
