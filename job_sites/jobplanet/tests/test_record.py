"""응답 → CSV 한 줄.

여기서 볼 것 둘 —

    마감일 표기가 **같은 이름인데 두 가지**로 온다 (목록 `2026-09-06`, 상세 `2026.09.15`)
    근무지를 **우리가 거른다** — 지역 코드에 구·시가 없어 넓게 받은 뒤 글로 본다
"""
from __future__ import annotations

from _common.store import COLUMNS
from lib.record import (SITE_NAME, career_text, find_salary, format_deadline,
                        matches_locations, to_row, workplace)

from .helpers import (check, check_equal, check_raises, own_detail, relay_detail,
                      temp_json)


def _posting(**fields):
    row = {"id": 1404269, "posting_apply_type": "jobplanet",
           "company": {"name": "목록기업"}, "end_at": "2026-09-06"}
    row.update(fields)
    return row


def test_NORMAL_row_has_every_column():
    row = to_row(_posting(), own_detail(), candidates_file=temp_json())
    check_equal(list(row), list(COLUMNS), "칸 이름과 순서가 스키마와 같아야 한다")
    check_equal(row["사이트명"], SITE_NAME, "사이트명")
    check("posting_ids" in row["URL"] and "1404269" in row["URL"], row["URL"])


def test_NORMAL_real_own_posting_fills_the_body():
    row = to_row(_posting(), own_detail(), candidates_file=temp_json())
    for column in ("기업명", "지원자격", "경력", "근무지", "기술스택"):
        check(row[column].strip(), "%s 가 비었다" % column)


def test_NORMAL_detail_wins_over_listing():
    row = to_row(_posting(company={"name": "목록기업"}),
                 {"name": "상세기업", "end_at": "2026.09.15"},
                 candidates_file=temp_json())
    check_equal(row["기업명"], "상세기업", "상세가 더 정확하다")
    check_equal(row["마감일"], "2026-09-15", "상세 마감일")


def test_EXCEPTION_missing_id_raises():
    # 키가 없는 행은 병합도 추적도 안 된다. 조용히 빈 URL 을 넣으면 안 된다.
    check_raises(ValueError, lambda: to_row(_posting(id=""), {}), "번호 없음")
    check_raises(ValueError, lambda: to_row(_posting(id=None), {}), "번호가 None")


def test_EXCEPTION_relay_posting_leaves_body_blank():
    row = to_row(_posting(posting_apply_type="jobkorea_inlink"), relay_detail(),
                 candidates_file=temp_json())
    check_equal(row["지원자격"], "", "없는 본문을 지어내지 않는다")
    check_equal(row["기술스택"], "", "없는 기술을 지어내지 않는다")


def test_EXCEPTION_empty_detail_falls_back_to_listing():
    row = to_row(_posting(), {}, candidates_file=temp_json())
    check_equal(row["기업명"], "목록기업", "목록 값으로 메운다")
    check_equal(row["마감일"], "2026-09-06", "목록 마감일")


def test_BOUNDARY_two_deadline_notations():
    # 결함이 될 뻔한 곳: 같은 `end_at` 인데 목록은 `-`, 상세는 `.` 으로 온다.
    check_equal(format_deadline("2026-09-06"), "2026-09-06", "목록 표기")
    check_equal(format_deadline("2026.09.15"), "2026-09-15", "상세 표기")
    check_equal(format_deadline("2026/9/5"), "2026-09-05", "한 자리 월·일도 채운다")
    check_equal(format_deadline(""), "", "빈 값")
    check_equal(format_deadline(None), "", "None")
    check_equal(format_deadline("상시채용"), "상시채용", "날짜가 아니면 그대로")


def test_BOUNDARY_salary_only_when_it_is_a_number():
    # 대부분 `"-"` 나 `" (  ~  )"` 로 온다. 값처럼 보이지만 거를 수도 비교할 수도 없다 (D-10).
    check_equal(find_salary({"salary": "-"}), "", "빈 껍데기")
    check_equal(find_salary({"salary": " (  ~  )"}), "", "빈 범위")
    check_equal(find_salary({"salary": "회사 내규에 따름"}), "", "문구는 값이 아니다")
    check_equal(find_salary({}), "", "없음")
    check_equal(find_salary({"salary": "3,400만원 이상"}), "3,400만원", "실금액")


def test_BOUNDARY_career_prefers_the_readable_text():
    check_equal(career_text({"recruitment_text": ["5 ~ 10년"]}, {}), "5 ~ 10년", "자세한 쪽")
    check_equal(career_text({"annual": {"text": "경력"}}, {}), "경력", "없으면 물러선다")
    check_equal(career_text({"recruitment_text": []}, {"annual": {"text": "신입"}}), "신입",
                "빈 목록이면 목록 값으로")
    check_equal(career_text({}, {}), "", "아무것도 없음")


def test_BOUNDARY_workplace_falls_back_to_province():
    check_equal(workplace({"location": "서울시 강남구 테헤란로 427"}, {}),
                "서울시 강남구 테헤란로 427", "자세한 주소")
    check_equal(workplace({"working_area": ["경기"]}, {}), "경기", "없으면 시도라도")
    check_equal(workplace({}, {"cities": ["서울", "경기"]}), "서울, 경기", "목록 값")
    check_equal(workplace({}, {}), "", "아무것도 없음")


def test_BOUNDARY_location_filter_matches_narrow_names():
    # 서버에 `성남시` 를 못 걸어서 `경기` 로 받은 뒤 여기서 거른다.
    row = {"근무지": "경기 성남시 분당구 판교로"}
    check(matches_locations(row, ["성남시"]), "시 이름")
    check(matches_locations(row, ["성남"]), "`시` 를 뗀 이름")
    check(matches_locations(row, ["분당구"]), "구 이름")
    check(matches_locations(row, ["경기"]), "시도 이름")
    check(not matches_locations(row, ["수원시"]), "다른 시는 안 맞아야 한다")


def test_BOUNDARY_location_filter_with_no_condition_passes_all():
    check(matches_locations({"근무지": "부산 해운대구"}, []), "조건이 없으면 전부 통과")
    check(matches_locations({"근무지": "부산 해운대구"}, ["전국"]), "전국도 전부 통과")


def test_BOUNDARY_blank_workplace_passes_the_filter():
    # 잘못 버리는 것보다 넘기는 쪽이 낫다 — 버린 공고는 있었다는 사실조차 안 남는다.
    check(matches_locations({"근무지": ""}, ["서울"]), "근무지가 비면 통과시킨다")
    check(matches_locations({}, ["서울"]), "칸이 아예 없어도 통과")


def test_BOUNDARY_seoul_matches_both_notations():
    # 회사마다 `서울` 과 `서울특별시` 를 섞어 쓴다.
    for place in ("서울 구로구 디지털로", "서울특별시 구로구 디지털로", "서울시 강남구"):
        check(matches_locations({"근무지": place}, ["서울"]), place)


def test_BOUNDARY_row_values_are_all_strings():
    row = to_row(_posting(), own_detail(), candidates_file=temp_json())
    for column, value in row.items():
        check(isinstance(value, str), "%s 가 문자열이 아니다: %r" % (column, value))


def test_BOUNDARY_long_field_is_trimmed_with_a_mark():
    # 표 계산기가 긴 칸에서 느려진다. 자르되 **잘랐다는 표시**를 남긴다.
    from lib.record import MAX_FIELD_LENGTH
    long_text = "가" * (MAX_FIELD_LENGTH + 500)
    row = to_row(_posting(), {"required_qualification": long_text},
                 candidates_file=temp_json())
    check(len(row["지원자격"]) <= MAX_FIELD_LENGTH + 2, len(row["지원자격"]))
    check(row["지원자격"].endswith("…"), "잘랐다는 표시가 있어야 한다")
