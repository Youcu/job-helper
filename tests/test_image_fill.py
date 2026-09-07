"""읽어 낸 것을 행에 채운다. **덮지 않고 보강한다.**

그림 공고인데 자격요건이 이미 차 있는 경우가 있다(29건 중 6건). 사람인 모집조건 표에서 온
값이라 성격이 다르다 — 학력·경력 조건이다. 덮어쓰면 그것을 잃고, 통째로 이으면 같은 말이
두 번 들어간다. 그래서 **없는 것만 더한다.**

편집거리는 안 쓴다(D-04). `REST`/`Rust` 를 같은 것으로 볼 위험이 여기서도 같다.
애매하면 더하는 쪽으로 기운다 — 중복은 거슬리는 정도지만, 빠뜨린 자격요건은 그 공고를
잘못 판단하게 만든다.
"""
from __future__ import annotations

from image_process import fill

from .helpers import check, check_equal


def _row(**fields) -> dict:
    row = {"기업명": "회사", "URL": "https://example.com/1", "사이트명": "jobkorea",
           "기술스택": "https://img/1.png", "지원자격": "", "우대사항": ""}
    row.update(fields)
    return row


def test_NORMAL_tech_column_replaces_the_url():
    got = fill.apply(_row(), {"기술스택": ["Java", "Spring"], "자격요건": [], "우대사항": []})
    check_equal(got["기술스택"], "Java, Spring", "주소를 걷어내고 기술로 바꾼다")


def test_NORMAL_empty_columns_are_filled():
    got = fill.apply(_row(), {"기술스택": [], "자격요건": ["3년 이상"], "우대사항": ["석사"]})
    check("3년 이상" in got["지원자격"], "자격요건: %r" % got["지원자격"])
    check("석사" in got["우대사항"], "우대사항: %r" % got["우대사항"])


def test_NORMAL_existing_text_is_kept_and_extended():
    row = _row(지원자격="• 신입 / 경력 (연수 무관)\n• 대학교졸업(4년)이상")
    got = fill.apply(row, {"기술스택": [], "자격요건": ["AWS 운영 경험 1년 이상"], "우대사항": []})
    check("대학교졸업(4년)이상" in got["지원자격"], "기존을 지켜야 한다")
    check("AWS 운영 경험 1년 이상" in got["지원자격"], "새 것을 더해야 한다")


def test_NORMAL_original_row_is_not_mutated():
    row = _row()
    fill.apply(row, {"기술스택": ["Java"], "자격요건": [], "우대사항": []})
    check_equal(row["기술스택"], "https://img/1.png", "원본을 고치면 안 된다")


def test_EXCEPTION_identical_item_is_not_added_twice():
    row = _row(지원자격="• 대학교졸업(4년)이상")
    got = fill.apply(row, {"기술스택": [], "자격요건": ["대학교졸업(4년)이상"], "우대사항": []})
    check_equal(got["지원자격"].count("대학교졸업"), 1, "같은 말은 한 번만: %r" % got["지원자격"])


def test_EXCEPTION_item_already_inside_the_existing_text_is_skipped():
    # 겹쳐 자른 조각에서 같은 줄이 두 번 나오는 것을 여기서 걸러 준다.
    row = _row(지원자격="• AWS 인프라 운영 경험이 1년 이상 5년 미만이신 분")
    got = fill.apply(row, {"기술스택": [], "자격요건": ["AWS 인프라 운영 경험"], "우대사항": []})
    check_equal(got["지원자격"].count("AWS"), 1, "이미 든 말은 안 더한다: %r" % got["지원자격"])


def test_BOUNDARY_bullet_and_spacing_differences_are_ignored():
    row = _row(지원자격="- 대학교졸업(4년) 이상")
    got = fill.apply(row, {"기술스택": [], "자격요건": ["• 대학교졸업(4년)이상"], "우대사항": []})
    check_equal(got["지원자격"].count("대학교졸업"), 1, "글머리표·띄어쓰기만 다른 것: %r"
                % got["지원자격"])


def test_BOUNDARY_has_anything_needs_only_one_of_three():
    check(not fill.has_anything({"기술스택": [], "자격요건": [], "우대사항": []}), "셋 다 비면 없다")
    check(fill.has_anything({"기술스택": ["Java"], "자격요건": [], "우대사항": []}), "기술만 있어도")
    check(fill.has_anything({"기술스택": [], "자격요건": ["3년"], "우대사항": []}), "자격만 있어도")
    check(fill.has_anything({"기술스택": [], "자격요건": [], "우대사항": ["석사"]}), "우대만 있어도")


def test_BOUNDARY_empty_tech_leaves_the_column_blank_not_the_url():
    # 자격요건을 얻어 행은 살아남지만 기술은 못 얻은 경우. **주소는 기술이 아니다.**
    got = fill.apply(_row(), {"기술스택": [], "자격요건": ["3년 이상"], "우대사항": []})
    check_equal(got["기술스택"], "", "주소를 남기면 다음 단계가 기술로 착각한다")


def test_BOUNDARY_blank_and_whitespace_items_are_dropped():
    got = fill.apply(_row(), {"기술스택": ["Java", "", "   "], "자격요건": [], "우대사항": []})
    check_equal(got["기술스택"], "Java", "빈 항목은 버린다")


def test_EXCEPTION_seam_between_unrelated_bullets_is_not_a_match():
    # 서로 다른 두 줄을 통째로 이어 붙여 견주면, 실제로는 없는 문구가 두 줄의
    # 이음매를 걸치고 있다는 이유만으로 "이미 있다" 로 잘못 판정된다.
    row = _row(지원자격="• 자바 스프링부트 우대\n• 3년차 프론트엔드 경험")
    got = fill.apply(row, {"기술스택": [], "자격요건": ["우대 3년차"], "우대사항": []})
    check("우대 3년차" in got["지원자격"],
          "줄 경계를 걸친 것은 원문에 없던 말이다 — 더해야 한다: %r" % got["지원자격"])


def test_BOUNDARY_punctuation_only_item_does_not_count_as_content():
    check(not fill.has_anything({"기술스택": ["..."], "자격요건": [], "우대사항": []}),
          "점만 있는 항목은 내용이 아니다")
    check(not fill.has_anything({"기술스택": ["•"], "자격요건": [], "우대사항": []}),
          "글머리표만 있는 항목도 내용이 아니다")


def test_BOUNDARY_punctuation_only_item_is_not_written_to_empty_column():
    got = fill.apply(_row(), {"기술스택": [], "자격요건": ["•"], "우대사항": []})
    check_equal(got["지원자격"], "",
                "점·글머리표만 있는 항목은 빈 칸에도 쓰면 안 된다: %r" % got["지원자격"])
