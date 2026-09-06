"""응답 → CSV 한 줄.

JSON-LD 가 12칸을 100% 채우지만 **믿고 그냥 쓰면 안 되는 곳**이 둘 있다.
`baseSalary` 는 값 하나가 아니라 **범위**로 오고, 없는 공고가 81%다.
그리고 본문 절 나누기는 표 머리글에 걸리면 자격과 우대가 **같은 글**을 담는다.
"""
from __future__ import annotations

from _common.store import COLUMNS
from lib.record import (SITE_NAME, find_salary, format_deadline, job_posting,
                        split_sections, to_row)

from .helpers import body_html, check, check_equal, check_raises, detail, posting


def _listing(**fields):
    row = {"gno": "49911986", "기업명": "목록기업", "제목": "백엔드 개발자",
           "조건": ["신입", "대졸", "서울 강남구", "정규직"], "마감일": "~09/30"}
    row.update(fields)
    return row


def test_NORMAL_row_has_every_column():
    row = to_row(_listing(), detail("49911986"), body_html("49911986"))
    check_equal(list(row), list(COLUMNS), "칸 이름과 순서가 스키마와 같아야 한다")
    check_equal(row["사이트명"], SITE_NAME, "사이트명")
    check_equal(row["URL"], "https://www.jobkorea.co.kr/Recruit/GI_Read/49911986", "URL")


def test_NORMAL_structured_data_wins_over_listing():
    html = posting(hiringOrganization={"name": "상세기업"},
                   validThrough="2026-09-30T23:59",
                   experienceRequirements="신입",
                   jobLocation={"address": {"streetAddress": "서울시 강남구 테헤란로"}})
    row = to_row(_listing(), html)
    check_equal(row["기업명"], "상세기업", "상세가 목록보다 정확하다")
    check_equal(row["마감일"], "2026-09-30", "절대 날짜")
    check_equal(row["근무지"], "서울시 강남구 테헤란로", "주소")


def test_NORMAL_image_urls_go_into_skill_column():
    row = to_row(_listing(), "", "", image_urls=["https://a.co/1.png"])
    check_equal(row["기술스택"], "https://a.co/1.png", "아직 안 읽었다는 표시")


def test_NORMAL_sections_split():
    qualification, preference = split_sections(
        "<p>자격요건</p><p>Java 3년</p><p>우대사항</p><p>Kotlin 경험</p>")
    check("Java" in qualification and "Kotlin" not in qualification, qualification)
    check("Kotlin" in preference, preference)


def test_EXCEPTION_missing_gno_raises():
    # 키가 없는 행은 병합도 추적도 안 된다. 조용히 빈 URL 을 넣으면 안 된다.
    check_raises(ValueError, lambda: to_row(_listing(gno="")), "공고번호 없음")
    check_raises(ValueError, lambda: to_row(_listing(gno=None)), "공고번호가 None")


def test_EXCEPTION_broken_json_ld_falls_back_to_listing():
    row = to_row(_listing(), '<script type="application/ld+json">{깨짐</script>')
    check_equal(job_posting('<script type="application/ld+json">{</script>'), {},
                "깨진 구조화 데이터는 빈 사전")
    check_equal(row["기업명"], "목록기업", "목록 값으로 메운다 — 수집이 멈추면 안 된다")


def test_EXCEPTION_json_ld_of_another_type_is_ignored():
    html = '<script type="application/ld+json">{"@type":"Organization","name":"회사"}</script>'
    check_equal(job_posting(html), {}, "JobPosting 이 아니면 안 쓴다")


def test_EXCEPTION_no_detail_at_all():
    row = to_row(_listing(), "", "")
    check_equal(row["기업명"], "목록기업", "상세가 없어도 행은 나온다")
    check_equal(row["경력"], "신입", "목록 조건 셀에서 메운다")


def test_BOUNDARY_salary_is_a_range_not_a_single_value():
    # 결함이었던 곳: `value.value` 하나로 읽었더니 실제로는 min/max 로 와서 터졌다.
    html = posting(baseSalary={"value": {"unitText": "YEAR",
                                         "minValue": 30000000, "maxValue": 50010000}})
    check_equal(find_salary(job_posting(html), {}), "연봉 3,000~5,001만원", "범위")


def test_BOUNDARY_salary_single_value_and_period():
    check_equal(find_salary(job_posting(posting(
        baseSalary={"value": {"unitText": "MONTH", "value": 2500000}})), {}),
        "월급 250만원", "단일 값")
    check_equal(find_salary(job_posting(posting(
        baseSalary={"value": {"unitText": "YEAR", "minValue": 40000000,
                              "maxValue": 40000000}})), {}),
        "연봉 4,000만원", "위아래가 같으면 하나로 적는다")


def test_BOUNDARY_salary_absent_or_meaningless():
    # "회사 내규에 따름" 은 값처럼 보이지만 거를 수도 비교할 수도 없다 (D-10).
    check_equal(find_salary({}, {"조건": ["신입", "회사내규", "서울"]}), "", "문구는 값이 아니다")
    check_equal(find_salary({}, {}), "", "아무것도 없으면 빈칸")
    check_equal(find_salary(job_posting(posting(baseSalary={"value": {}})), {}), "",
                "빈 급여 구조")
    check_equal(find_salary(job_posting(posting(baseSalary="협의")), {}), "",
                "급여가 문자열로 와도 터지지 않는다")


def test_BOUNDARY_salary_from_listing_cell():
    check_equal(find_salary({}, {"조건": ["신입", "3,400만원 이상", "정규직"]}), "3,400만원",
                "목록 셀에서 실금액을 찾는다")


def test_BOUNDARY_deadline_prefers_absolute_date():
    # 목록은 `~01/05` 라 연도가 없다. 12월에 본 것을 올해로 붙이면 이미 지난 날이 된다.
    check_equal(format_deadline("2027-01-05T23:59", "~01/05"), "2027-01-05", "상세 우선")
    check_equal(format_deadline(None, "~09/30"), "09-30", "상세가 없으면 목록 표기 그대로")
    check_equal(format_deadline(None, "상시채용"), "상시채용", "날짜가 아닌 표기")
    check_equal(format_deadline(None, ""), "", "아무것도 없음")
    check_equal(format_deadline("깨진값", "~09/30"), "09-30", "못 읽는 절대 날짜")


def test_BOUNDARY_column_header_is_not_a_section_start():
    # 결함이었던 곳: `자격요건 및 우대조건` 은 표의 열 머리글이다. 절 시작으로 보면
    # 자격과 우대가 같은 자리에서 시작해 **같은 글**을 담는다.
    qualification, preference = split_sections(
        "<p>모집분야 업무내용 자격요건 및 우대조건</p><p>Java 3년</p>")
    check(qualification != preference or not preference,
          "자격과 우대가 같은 글이면 안 된다: %r" % (qualification,))


def test_BOUNDARY_no_heading_puts_everything_in_qualification():
    # 내용은 있는데 우리가 못 나눈 것이다. 우대사항을 복사해 넣으면 없는 구분을 지어낸다.
    qualification, preference = split_sections("<p>Java 를 잘 하는 분을 모십니다</p>")
    check("Java" in qualification, qualification)
    check_equal(preference, "", "못 찾은 절은 빈칸이다")


def test_BOUNDARY_preference_only():
    qualification, preference = split_sections(
        "<p>이런 일을 합니다</p><p>우대사항</p><p>Kotlin</p>")
    check("Kotlin" in preference, preference)
    check("Kotlin" not in qualification, "우대가 자격으로 새면 안 된다: %r" % qualification)


def test_BOUNDARY_empty_body():
    check_equal(split_sections(""), ("", ""), "빈 본문")
    check_equal(split_sections(None), ("", ""), "None")


def test_BOUNDARY_row_values_are_all_strings():
    row = to_row(_listing(), detail("49911986"), body_html("49911986"))
    for column, value in row.items():
        check(isinstance(value, str), "%s 가 문자열이 아니다: %r" % (column, value))
