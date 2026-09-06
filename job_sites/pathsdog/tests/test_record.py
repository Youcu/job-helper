"""MCP 상세 글 → CSV 한 줄.

여기서 볼 것 셋 —

    `필수 기술`·`우대 기술` 은 **기술이 아니라 자격 문장**이다. 원문 절 나누기가 먼저다
    원문 앞머리의 메타데이터(`공고명:`·`회사:`)를 떼야 한다 — 안 떼면 지원자격에 딸려 든다
    `미기재`·`회사 내규에 따름` 은 **값이 아니다.** 그대로 넣으면 값처럼 보인다
"""
from __future__ import annotations

from _common.store import COLUMNS
from lib.record import (BLANKS, SITE_NAME, company_name, field, find_salary,
                        format_deadline, full_description, matches_employment,
                        matches_locations, split_sections, to_row, workplace)

from .helpers import check, check_equal, check_raises, detail_text, temp_json


def _listing(**fields):
    row = {"id": "3354", "기업명": "목록기업", "제목": "공고",
           "기술": "Python, Backend", "조건": "신입 | 근무지: 서울 | 정규직",
           "마감": "2026-09-18", "상세주소": "https://jobs.pathsdog.com/jobs/3354-x"}
    row.update(fields)
    return row


def test_NORMAL_row_has_every_column():
    row = to_row(_listing(), detail_text(), candidates_file=temp_json())
    check_equal(list(row), list(COLUMNS), "칸 이름과 순서가 스키마와 같아야 한다")
    check_equal(row["사이트명"], SITE_NAME, "사이트명")
    check("jobs.pathsdog.com" in row["URL"], row["URL"])


def test_NORMAL_real_detail_fills_the_body():
    row = to_row(_listing(), detail_text(), candidates_file=temp_json())
    for column in ("기업명", "마감일", "경력", "지원자격", "기술스택"):
        check(row[column].strip(), "%s 가 비었다" % column)


def test_NORMAL_reads_labelled_fields():
    text = "- 경력: 신입\n- 근무지: 서울 강남구\n- 고용형태: 정규직\n"
    check_equal(field(text, "경력"), "신입", "라벨 값")
    check_equal(field(text, "근무지"), "서울 강남구", "라벨 값")
    check_equal(field(text, "없는라벨"), "", "없으면 빈칸")


def test_NORMAL_company_from_the_head_line():
    check_equal(company_name("📋 ㈜네비웍스 - AI 서비스 백엔드 개발자(신입)\n"), "㈜네비웍스", "회사")
    check_equal(company_name("📋 회사만있음\n"), "", "가를 수 없으면 빈칸")
    check_equal(company_name("머리줄 없음"), "", "머리줄이 없으면 빈칸")


def test_EXCEPTION_missing_id_raises():
    # 키가 없는 행은 병합도 추적도 안 된다. 조용히 빈 URL 을 넣으면 안 된다.
    check_raises(ValueError, lambda: to_row(_listing(id=""), ""), "번호 없음")
    check_raises(ValueError, lambda: to_row(_listing(id=None), ""), "번호가 None")


def test_EXCEPTION_empty_detail_falls_back_to_listing():
    row = to_row(_listing(), "", candidates_file=temp_json())
    check_equal(row["기업명"], "목록기업", "목록 값으로 메운다")
    check_equal(row["마감일"], "2026-09-18", "목록 마감일")
    check_equal(row["경력"], "신입", "목록 조건 줄에서")
    check_equal(row["근무지"], "서울", "목록 조건 줄에서")


def test_BOUNDARY_blank_words_are_not_values():
    # `미기재` 를 그대로 넣으면 값처럼 보인다. 빈칸이어야 사람이 없는 줄 안다.
    for word in BLANKS:
        check_equal(field("- 근무지: %s\n" % word, "근무지"), "",
                    "%r 는 값이 아니다" % word)
    check_equal(workplace("- 근무지: 미기재\n", {"조건": "신입 | 근무지: 미기재 | 정규직"}), "",
                "목록으로 물러서도 마찬가지")


def test_BOUNDARY_meta_head_is_stripped_from_the_body():
    # 결함이었던 곳: 원문이 `공고명: … / 회사: … / 고용형태: …` 로 시작하는데, 절 머리말을
    # 못 찾으면 본문 전체가 지원자격이 되므로 이것까지 딸려 들어갔다.
    detail = ("[상세 내용]\n공고명: 백엔드 개발자\n\n회사: ㈜테스트\n\n"
              "고용형태: 정규직\n\n기업소개 우리는 …\n")
    body = full_description(detail)
    check(not body.startswith("공고명"), "메타 머리가 남으면 안 된다: %r" % body[:40])
    check(body.startswith("기업소개"), body[:40])


def test_BOUNDARY_body_without_a_meta_head():
    detail = "[상세 내용]\n주요업무 서버 개발\n자격요건 Java 3년\n"
    check(full_description(detail).startswith("주요업무"), "메타가 없으면 그대로")


def test_BOUNDARY_sections_prefer_the_body_over_the_label():
    # 라벨 칸은 이름과 달리 자격 문장이고 전형 절차까지 섞인다. 원문 절이 먼저다.
    detail = ("- 필수 기술: 제출서류, 이력서, 절차안내\n"
              "[상세 내용]\n자격요건\nJava 3년 이상\n우대사항\nKotlin 경험\n")
    qualification, preference = split_sections(detail)
    check("Java" in qualification and "제출서류" not in qualification, qualification)
    check("Kotlin" in preference, preference)


def test_BOUNDARY_sections_fall_back_to_the_label():
    # 절을 못 찾으면 라벨 칸으로 물러선다 — 지저분해도 빈칸보다는 낫다.
    detail = "- 필수 기술: Python 개발 유경험자\n- 우대 기술: AI 경험자\n"
    qualification, preference = split_sections(detail)
    check_equal(qualification, "Python 개발 유경험자", "필수 기술 칸")
    check_equal(preference, "AI 경험자", "우대 기술 칸")


def test_BOUNDARY_deadline_prefers_the_detail():
    check_equal(format_deadline("- 서류 마감: 2026-09-28\n", {"마감": "2026-01-01"}),
                "2026-09-28", "상세가 먼저")
    check_equal(format_deadline("", {"마감": "2026-01-01"}), "2026-01-01", "없으면 목록")
    check_equal(format_deadline("", {}), "", "둘 다 없으면 빈칸")
    check_equal(format_deadline("- 서류 마감: 2026-9-5\n", {}), "2026-09-05", "한 자리 채움")


def test_BOUNDARY_salary_only_when_it_is_a_number():
    # `회사 내규에 따름` 이 대부분이다 (D-10).
    check_equal(find_salary("- 연봉: 회사 내규에 따름\n"), "", "문구는 값이 아니다")
    check_equal(find_salary("- 연봉: 미기재\n"), "", "미기재")
    check_equal(find_salary(""), "", "없음")
    check_equal(find_salary("- 연봉: 3,400만원 이상\n"), "3,400만원", "실금액")


def test_BOUNDARY_location_filter_matches_narrow_names():
    row = {"근무지": "경기 성남시 분당구 판교역로 220"}
    check(matches_locations(row, ["판교"]), "판교")
    check(matches_locations(row, ["성남시"]), "시 이름")
    check(matches_locations(row, ["성남"]), "`시` 를 뗀 이름")
    check(not matches_locations(row, ["서울"]), "다른 곳은 안 맞아야 한다")


def test_BOUNDARY_blank_location_passes():
    # 29건 중 4건이 `미기재` 였다. 잘못 버리는 것보다 넘기는 쪽이 낫다.
    check(matches_locations({"근무지": ""}, ["서울"]), "빈칸은 통과")
    check(matches_locations({}, ["서울"]), "칸이 없어도 통과")
    check(matches_locations({"근무지": "제주"}, []), "조건이 없으면 전부 통과")


def test_BOUNDARY_employment_filter():
    check(matches_employment("- 고용형태: 정규직\n", ["정규직", "인턴"]), "맞음")
    check(not matches_employment("- 고용형태: 계약직\n", ["정규직"]), "다름")
    check(matches_employment("- 고용형태: 미기재\n", ["정규직"]), "미기재는 통과")
    check(matches_employment("", ["정규직"]), "칸이 없어도 통과")
    check(matches_employment("- 고용형태: 계약직\n", []), "조건이 없으면 전부 통과")


def test_BOUNDARY_row_values_are_all_strings():
    row = to_row(_listing(), detail_text(), candidates_file=temp_json())
    for column, value in row.items():
        check(isinstance(value, str), "%s 가 문자열이 아니다: %r" % (column, value))


def test_BOUNDARY_long_field_is_trimmed_with_a_mark():
    # 표 계산기가 긴 칸에서 느려진다. 자르되 **잘랐다는 표시**를 남긴다.
    from lib.record import MAX_FIELD_LENGTH
    detail = "- 필수 기술: %s\n" % ("가" * (MAX_FIELD_LENGTH + 500))
    row = to_row(_listing(), detail, candidates_file=temp_json())
    check(len(row["지원자격"]) <= MAX_FIELD_LENGTH + 2, len(row["지원자격"]))
    check(row["지원자격"].endswith("…"), "잘랐다는 표시가 있어야 한다")


def test_BOUNDARY_employment_filter_passes_when_nothing_wanted():
    check(matches_employment("- 고용형태: 계약직\n", []), "조건이 없으면 전부 통과")
