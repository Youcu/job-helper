"""`lib/record.py` — 응답을 CSV 한 줄로.

노리는 결함 넷.

1. **없는 값을 그럴듯하게 채우는 것.** "면접 후 결정" 을 연봉 칸에 넣으면 값처럼 보이지만
   비교도 필터도 안 된다. 빈칸이 정직하다 (D-10).
2. **정보를 조각내며 잃는 것.** `신입 · 경력 · 정규직 외` 에서 첫 조각만 취하면 "경력" 이 사라진다.
3. **칸을 잘못 짚는 것.** `<dt>급여</dt><dd>값</dd>` 에서 느슨하게 잡으면 **빈 문자열**이
   잡힌다 — 실제로 131건 전부에서 칸은 찾았는데 값이 0건이었다.
4. **없는 구분을 지어내는 것.** 우대사항 머리말이 없다고 지원자격을 복사하면 안 된다.
"""
from __future__ import annotations

from lib import record
from tests.helpers import check, check_equal, detail_pages

LISTING = {"rec_idx": "123", "기업명": "회사", "근무지": "서울전체 외",
           "경력": "신입 · 정규직", "마감일": "~09.14(월)"}


def body(inner: str) -> str:
    return '<div class="user_content jobsViewDetail_123">%s</div>' % inner


def summary(label: str, value: str) -> str:
    return "<dl><dt>%s</dt><dd> %s </dd></dl>" % (label, value)


# ─────────────────────────────── 일반 ───────────────────────────────

def test_NORMAL_row_has_every_column_in_order():
    from _common.store import COLUMNS
    row = record.to_row(LISTING, body("<p>자격요건</p><p>대졸 이상</p>"))
    check_equal(list(row), COLUMNS, "칸과 순서가 공통 스키마와 같아야 한다")
    check_equal(row["사이트명"], "saramin", "사이트명 고정")
    check_equal(row["URL"], record.DETAIL_URL % "123", "URL 은 키다")


def test_NORMAL_title_comes_from_the_listing_card():
    """공고명은 목록 카드에서 온다.

    상세 페이지에는 같은 글이 제목·탭·og:title 로 여러 자리에 흩어져 있어 무엇이
    공고 제목인지 가리기 어렵다. 카드는 `div.job_tit > span` 한 자리라 확실하다.
    """
    page = body("<p>본문</p>")
    check_equal(record.to_row(dict(LISTING, 제목="백엔드 개발자 (신입)"), page)["공고명"],
                "백엔드 개발자 (신입)", "카드 제목이 그대로 온다")
    check_equal(record.to_row(LISTING, page)["공고명"], "",
                "카드에서 제목을 못 뽑았으면 빈칸이다 — 다른 자리에서 지어내지 않는다")


def test_NORMAL_sections_are_split():
    page = body("<p>자격요건</p><p>대졸 이상</p><p>우대사항</p><p>석사 우대</p>")
    qualification, preference = record.split_sections(page)
    check_equal(qualification, "대졸 이상", "지원자격")
    check_equal(preference, "석사 우대", "우대사항")


def test_NORMAL_section_ends_at_the_next_heading():
    page = body("<p>자격요건</p><p>대졸 이상</p><p>전형절차</p><p>서류 후 면접</p>")
    qualification, _ = record.split_sections(page)
    check_equal(qualification, "대졸 이상", "다음 절이 시작되면 앞 절은 끝난다")


def test_NORMAL_salary_amount_is_kept():
    page = body("<p>본문</p>") + summary("급여", "연봉 3,200 만원")
    check_equal(record.find_salary(page), "연봉 3,200만원", "실금액은 남긴다")


def test_NORMAL_workplace_prefers_the_detail():
    page = body("<p>본문</p>") + summary("근무지역", "서울 강서구, 서울전체")
    check_equal(record.find_workplace(page, "서울전체 외"), "서울 강서구, 서울전체",
                "상세가 목록보다 정확하다")


def test_NORMAL_real_posting_fills_every_expected_column():
    fixture = detail_pages()["52783795"]
    row = record.to_row({"rec_idx": "52783795", "기업명": "회사",
                         "경력": "신입 · 정규직", "마감일": "~09.30(화)"}, fixture["page"])
    for column in ("기업명", "마감일", "경력", "URL", "기술스택", "사이트명"):
        check(row[column], "%s 가 비었다" % column)


# ─────────────────────────────── 예외 ───────────────────────────────

def test_EXCEPTION_missing_rec_idx_raises():
    # URL 이 키다. 조용히 빈 URL 을 넣으면 병합도 추적도 안 되는 행이 쌓인다.
    for listing in ({}, {"rec_idx": ""}, {"rec_idx": "  "}, {"rec_idx": None}):
        try:
            record.to_row(listing)
        except ValueError:
            continue
        raise AssertionError("rec_idx 가 없는데 행을 만들었다: %r" % listing)


def test_EXCEPTION_salary_placeholder_is_blank():
    for placeholder in ("면접 후 결정", "회사 내규에 따름", "추후 협의", ""):
        page = body("<p>본문</p>") + summary("급여", placeholder)
        check_equal(record.find_salary(page), "",
                    "%r 는 금액이 아니다" % placeholder)


def test_EXCEPTION_salary_notice_text_is_not_swallowed():
    # 같은 칸에 최저임금 안내문이 통째로 붙어 온다. 넣으면 연봉 칸이 문단이 되고
    # 거기 든 다른 숫자가 급여로 읽힌다.
    page = body("<p>본문</p>") + summary(
        "급여", "연봉 3,200 만원 (주 40시간) 주 40시간 기준 최저임금은 25,882,560원 입니다.")
    check_equal(record.find_salary(page), "연봉 3,200만원", "금액만 남긴다")


def test_EXCEPTION_missing_summary_field_is_blank():
    check_equal(record.find_salary(body("<p>본문</p>")), "", "급여 칸이 없으면 빈칸")
    check_equal(record.find_workplace(body("<p>본문</p>"), "서울"), "서울",
                "근무지역이 없으면 목록 값을 쓴다")


def test_EXCEPTION_image_body_leaves_sections_blank():
    page = body('<img src="a.png">')
    check_equal(record.split_sections(page), ("", ""),
                "글이 없으면 지어내지 않는다")


def test_EXCEPTION_no_body_container_is_blank():
    check_equal(record.split_sections("<html><p>본문 밖</p></html>"), ("", ""),
                "본문 컨테이너가 없으면 빈칸")


def test_EXCEPTION_deadline_without_a_date_is_kept_as_written():
    for raw in ("상시채용", "채용시", "오늘마감"):
        check_equal(record.format_deadline(raw), raw,
                    "날짜가 아닌 마감 표기는 원문 그대로 둔다")


# ─────────────────────────────── 경계 ───────────────────────────────

def test_BOUNDARY_career_keeps_every_non_employment_part():
    # 결함: 첫 조각만 취하면 `신입 · 경력` 에서 "경력" 이 사라진다.
    check_equal(record.format_career("신입 · 경력 · 정규직 외"), "신입 · 경력", "둘 다 남긴다")
    check_equal(record.format_career("신입 · 정규직"), "신입", "고용형태만 뺀다")
    check_equal(record.format_career("경력무관"), "경력무관", "구분자가 없어도 값이다")
    check_equal(record.format_career(" · 정규직"), "", "고용형태뿐이면 빈칸")
    check_equal(record.format_career(""), "", "빈 입력")


def test_BOUNDARY_deadline_pads_single_digits():
    check_equal(record.format_deadline("~1.5(금)"), "01-05", "한 자리 월/일을 채운다")
    check_equal(record.format_deadline("~12.31"), "12-31", "두 자리")
    check_equal(record.format_deadline(""), "", "빈 입력")


def test_BOUNDARY_no_year_is_added_to_the_deadline():
    # 12월에 본 `01.05` 에 올해를 붙이면 이미 지난 날짜가 된다.
    check("20" not in record.format_deadline("~01.05(금)"), "연도를 붙이지 않는다")


def test_BOUNDARY_heading_with_value_on_the_same_line():
    qualification, _ = record.split_sections(body("<p>자격요건 : 대졸 이상</p>"))
    check_equal(qualification, "대졸 이상", "머리말 줄에 값이 붙어 있어도 읽는다")


def test_BOUNDARY_no_heading_falls_back_to_the_whole_body():
    qualification, preference = record.split_sections(body("<p>그냥 본문입니다</p>"))
    check_equal(qualification, "그냥 본문입니다", "못 나눴을 뿐 내용은 거기 있다")
    check_equal(preference, "", "우대사항은 지어내지 않는다")


def test_BOUNDARY_preference_alone_does_not_empty_qualification():
    qualification, preference = record.split_sections(
        body("<p>앞머리</p><p>우대사항</p><p>석사 우대</p>"))
    check_equal(preference, "석사 우대", "우대사항")
    check(qualification, "자격 머리말이 없으면 본문 전체가 지원자격이다")


def test_BOUNDARY_long_field_is_trimmed_with_a_mark():
    page = body("<p>" + ("가" * (record.MAX_FIELD_LENGTH + 500)) + "</p>")
    qualification, _ = record.split_sections(page)
    check(len(qualification) <= record.MAX_FIELD_LENGTH + 2,
          "상한을 넘으면 안 된다: %d" % len(qualification))
    check(qualification.endswith("…"), "잘렸다는 표시가 있어야 한다")


def test_BOUNDARY_image_urls_go_after_the_skill_names():
    # 나중 단계가 `http` 로 시작하는지로 골라낸다. 순서가 섞여도 되지만
    # 사람이 CSV 를 읽을 때는 기술이 앞에 오는 편이 낫다.
    page = body("<p>자격요건</p><p>Java 를 씁니다</p>")
    row = record.to_row(LISTING, page, image_urls=["https://x.test/a.png"])
    parts = [p.strip() for p in row["기술스택"].split(",")]
    check_equal(parts[-1], "https://x.test/a.png", "주소가 뒤에 온다")
    check("Java" in parts, "본문에서 찾은 기술은 그대로")


def test_BOUNDARY_workplace_strips_map_button_text():
    page = body("<p>본문</p>") + summary("근무지역", "서울 강서구 지도보기")
    check_equal(record.find_workplace(page), "서울 강서구", "버튼 글자를 뺀다")


def test_EXCEPTION_table_column_header_is_not_a_section_start():
    # 사람인 양식의 모집부문 표는 `모집분야 업무내용 자격요건 및 우대조건` 으로 시작한다.
    # 이 줄을 절 시작으로 보면 자격과 우대가 같은 자리에서 시작해 **같은 글을 담는다** —
    # 실제로 두 칸에 똑같은 내용이 들어간 행이 9건 나왔다.
    page = body("<p>모집분야 업무내용 자격요건 및 우대조건</p>"
                "<p>표 내용</p>"
                "<p>[ 자격요건 ]</p><p>대졸 이상</p>"
                "<p>[ 우대조건 ]</p><p>석사 우대</p>")
    qualification, preference = record.split_sections(page)
    check_equal(qualification, "대졸 이상", "진짜 머리말에서 시작해야 한다")
    check_equal(preference, "석사 우대", "우대사항")
    check(preference not in qualification, "두 칸이 같은 글이면 안 된다")


def test_BOUNDARY_single_name_line_is_still_a_heading():
    # 절 이름 하나만 든 줄은 머리글이 아니라 진짜 머리말이다.
    qualification, _ = record.split_sections(body("<p>자격요건</p><p>대졸 이상</p>"))
    check_equal(qualification, "대졸 이상", "이름 하나면 머리말이다")


def test_BOUNDARY_fallback_body_is_cut_at_the_preference_heading():
    # 자격 머리말이 없어 본문 전체를 쓰더라도, 우대사항을 따로 뽑았으면 거기서 끊는다.
    page = body("<p>우리 회사는</p><p>좋은 곳입니다</p><p>우대사항</p><p>석사 우대</p>")
    qualification, preference = record.split_sections(page)
    check_equal(preference, "석사 우대", "우대사항")
    check("석사 우대" not in qualification, "같은 글이 두 칸에 겹치면 안 된다")
    check("좋은 곳입니다" in qualification, "앞부분은 지원자격으로 남는다")


# ────────────────── 마감일은 상세를 먼저 본다 ──────────────────

def period(text: str) -> str:
    return '<div class="info_period"><dt>마감일</dt><dd>%s</dd></div>' % text


def test_NORMAL_absolute_deadline_from_the_detail_wins():
    # 목록은 `D-5` 처럼 상대 표기로 줄 때가 있다 (122건 중 49건).
    # 그 값은 저장한 다음 날이면 거짓이다 — 누적 CSV 는 30일을 보존한다.
    page = body("<p>본문</p>") + period("2026.09.10 18:00")
    check_equal(record.find_deadline(page, "D-5"), "2026-09-10",
                "상세의 절대 날짜를 써야 한다")


def test_NORMAL_detail_wins_even_over_a_list_date():
    # 목록이 날짜를 줘도 상세가 더 정확하다 (표본 4/4 에서 둘이 일치했다).
    page = body("<p>본문</p>") + period("2026.10.02 23:59")
    check_equal(record.find_deadline(page, "~10.02(목)"), "2026-10-02", "연도까지 남는다")


def test_EXCEPTION_no_detail_deadline_falls_back_to_the_list():
    check_equal(record.find_deadline(body("<p>본문</p>"), "~09.14(월)"), "09-14",
                "상세에 없으면 목록 값을 쓴다")


def test_BOUNDARY_posting_without_any_deadline_keeps_the_phrase():
    # `상시채용` `채용시` 는 마감일이 **실제로 없는** 공고다. 지어내지 않는다.
    for phrase in ("상시채용", "채용시"):
        check_equal(record.find_deadline(body("<p>본문</p>"), phrase), phrase,
                    "%s 는 그대로 둬야 한다" % phrase)


def test_BOUNDARY_relative_phrase_without_a_detail_date_is_kept_as_written():
    # 상세에도 없으면 `D-5` 를 날짜로 바꿀 근거가 없다. 지어내는 것보다 원문이 낫다.
    check_equal(record.find_deadline(body("<p>본문</p>"), "D-5"), "D-5",
                "근거 없이 날짜를 만들지 않는다")
