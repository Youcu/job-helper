"""계약이 정한 말로 옮기는 일. **`_common` 의 것을 여기서 시험한다** — 모든 사이트가
함께 쓰는 코드라 어느 한 사이트에 붙여 두면 그 사이트를 지웠을 때 시험도 같이 사라진다.

실제로 있었던 일을 굳힌다. 2026-09-09 전량 수집 735행에서, 뜻이 같은데 표기만 다른 값이
이렇게 쪼개져 있었다.

    경력    사람인 `신입 · 경력` 188 · 잡코리아 `신입·경력` 123   → 311건
    마감일  `상시채용` 104 · 사람인 `채용시` 39
    근무지  `서울` 539 · `서울특별시` 27 · `서울시` 17          → 44건

합쳐 놓고 거르거나 묶을 수가 없었다.
"""
from __future__ import annotations

from _common import career, deadline, place
from _common.store import COLUMNS, to_contract

from .helpers import check, check_equal


# ──────────────────────────────────────────────────────────────────────────────
# 경력
# ──────────────────────────────────────────────────────────────────────────────

def test_NORMAL_both_new_and_experienced_becomes_irrelevant():
    """**이것이 이 파일이 생긴 이유다.** 두 사이트가 같은 뜻을 다르게 적었다."""
    check_equal(career.standard("신입 · 경력"), "경력무관", "사람인 표기")
    check_equal(career.standard("신입·경력"), "경력무관", "잡코리아 표기")
    check_equal(career.standard("신입/경력"), "경력무관", "빗금도 같은 뜻")
    check_equal(career.standard("신입 · 경력 · 정규직 외"), "경력무관", "고용형태가 붙어도")


def test_NORMAL_career_ranges_survive():
    check_equal(career.standard("신입"), "신입", "신입")
    check_equal(career.standard("신입~3년"), "신입~3년", "신입부터")
    check_equal(career.standard("3~10년"), "3~10년", "범위")
    check_equal(career.standard("경력 3년 이상"), "3년 이상", "하한만")
    check_equal(career.standard("경력 3년"), "3년", "딱 그만큼")
    check_equal(career.standard("경력무관"), "경력무관", "이미 계약대로")


def test_BOUNDARY_career_is_idempotent():
    """**두 번 걸어도 같아야 한다.** 합본을 다시 쓸 때 또 걸린다."""
    for value in ("신입", "신입~3년", "3~10년", "5년 이상", "8년", "경력무관"):
        check_equal(career.standard(career.standard(value)), career.standard(value), value)


def test_BOUNDARY_career_odd_inputs():
    check_equal(career.standard(""), "경력무관", "빈 값은 계약의 기본값")
    check_equal(career.standard(None), "경력무관", "없어도 터지지 않는다")
    check_equal(career.standard("경력 10~3년"), "3~10년", "뒤집힌 범위는 바로잡는다")
    check_equal(career.standard("신입~0년"), "신입", "0년까지는 신입이다")
    # `2년제` 는 학력이지 연차가 아니다. 이걸 연차로 읽으면 `2년` 경력이 된다.
    check_equal(career.standard("학력 2년제 이상"), "경력무관", "학력을 연차로 읽지 않는다")


# ──────────────────────────────────────────────────────────────────────────────
# 마감일
# ──────────────────────────────────────────────────────────────────────────────

def test_NORMAL_no_deadline_words_become_one_word():
    for word in ("채용시", "채용 시", "상시채용", "수시채용", "충원시"):
        check_equal(deadline.standard(word), "상시채용", word)
    check_equal(deadline.standard(""), "상시채용", "빈 값은 계약의 기본값")


def test_BOUNDARY_deadline_never_touches_a_date():
    check_equal(deadline.standard("2026-09-30"), "2026-09-30", "날짜는 그대로")


def test_BOUNDARY_unknown_deadline_text_is_left_alone():
    """**모르는 글을 `상시채용` 으로 바꾸면 진짜 마감일을 지운다.**

    사람인은 연도를 못 붙일 때 `09-14` 만 준다 — 마감일이 없는 게 아니라 연도를 모르는
    것이다. 그걸 `상시채용` 으로 만들면 마감된 공고가 상시 공고로 남는다.
    """
    check_equal(deadline.standard("09-14"), "09-14", "연도 없는 날짜는 그대로 둔다")
    check_equal(deadline.standard("~09.14(월)"), "~09.14(월)", "못 읽은 글도 그대로")


# ──────────────────────────────────────────────────────────────────────────────
# 근무지
# ──────────────────────────────────────────────────────────────────────────────

def test_NORMAL_sido_names_become_the_short_form():
    check_equal(place.standard("서울특별시 강남구 역삼로1길 8"), "서울 강남구 역삼로1길 8", "특별시")
    check_equal(place.standard("서울시 서초구 강남대로 311"), "서울 서초구 강남대로 311", "시")
    check_equal(place.standard("경기도 성남시 분당구"), "경기 성남시 분당구", "도")
    check_equal(place.standard("서울 강남구 테헤란로"), "서울 강남구 테헤란로", "이미 짧으면 그대로")


def test_BOUNDARY_place_only_touches_the_head():
    """**주소 안쪽을 건드리면 주소가 망가진다.**"""
    check_equal(place.standard("서울 강남구 서울대로 1"), "서울 강남구 서울대로 1",
                "뒤쪽 `서울대로` 는 그대로")
    check_equal(place.standard("성남시 수정구 고등로4"), "성남시 수정구 고등로4",
                "시도가 없으면 지어내지 않는다")


def test_BOUNDARY_country_prefix_is_dropped():
    """잡코리아 구조화 데이터는 `대한민국 서울특별시 …` 로 온다 (실측 3행).

    나라 이름이 앞에 붙어 있으면 **그 뒤의 시도를 못 보고 지나친다.** 전부 국내
    공고라 나라 이름에는 뜻이 없다.
    """
    check_equal(place.standard("대한민국 서울특별시 서초구 반포대로28길 43"),
                "서울 서초구 반포대로28길 43", "나라 이름을 떼고 시도를 맞춘다")
    check_equal(place.standard("대한민국제약 강남구 1"), "대한민국제약 강남구 1",
                "나라 이름으로 시작하는 다른 낱말은 건드리지 않는다")


def test_BOUNDARY_place_odd_inputs():
    check_equal(place.standard(""), "", "빈 값")
    check_equal(place.standard(None), "", "없어도 터지지 않는다")
    check_equal(place.standard("서울전체, 경기"), "서울 경기", "목록 카드의 `전체` 는 뗀다")
    check_equal(place.standard("서울"), "서울", "한 낱말")


# ──────────────────────────────────────────────────────────────────────────────
# 행 전체
# ──────────────────────────────────────────────────────────────────────────────

def test_NORMAL_to_contract_fixes_a_whole_row():
    row = to_contract({"기업명": "가", "경력": "신입 · 경력", "마감일": "채용시",
                       "근무지": "서울특별시 강남구 1"})
    check_equal(row["경력"], "경력무관", "경력")
    check_equal(row["마감일"], "상시채용", "마감일")
    check_equal(row["근무지"], "서울 강남구 1", "근무지")
    check_equal(row["기업명"], "가", "나머지 칸은 손대지 않는다")


def test_BOUNDARY_to_contract_fills_missing_columns_with_the_default():
    # 빈칸으로 두면 "값이 없다" 와 "따지지 않는다" 가 같은 모양이 된다.
    row = to_contract({"URL": "u"})
    check_equal(row["경력"], "경력무관", "경력의 기본값")
    check_equal(row["마감일"], "상시채용", "마감일의 기본값")
    check_equal(row["근무지"], "", "근무지는 지어낼 것이 없다")


def test_BOUNDARY_to_contract_does_not_change_the_input():
    given = {"경력": "신입 · 경력"}
    to_contract(given)
    check_equal(given["경력"], "신입 · 경력", "받은 행을 고쳐 쓰면 부르는 쪽이 놀란다")


def test_BOUNDARY_every_standardized_column_is_in_the_schema():
    """계약에 없는 칸을 맞추려 들면 그 칸은 CSV 에 나가지도 않는다."""
    from _common.store import STANDARDIZERS
    for column in STANDARDIZERS:
        check(column in COLUMNS, "%s 가 스키마에 없다" % column)
