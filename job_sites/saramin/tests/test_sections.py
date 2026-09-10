"""`_common/sections.py` — 본문을 지원자격과 우대사항으로 가르는 일.

이 모듈에는 그동안 전용 테스트가 **하나도 없었다.** 사이트 두 곳이 같이 쓰는데도 그랬고,
그래서 실측 24칸이 앞 글자가 잘린 채로 CSV 에 들어갔다.

가르기가 틀리는 방향은 둘이고, 값이 다르다.

- 절 경계를 잘못 잡으면 → **엉뚱한 글이 지원자격으로 들어온다** (틀린 데이터)
- 절을 못 찾으면 → 본문 전체가 지원자격이 된다 (덜 나눈 것뿐, 내용은 다 있다)

그래서 애매하면 못 나눈 쪽으로 둔다.
"""
from __future__ import annotations

import re

from _common.sections import (
    PREFERENCE_HEADING,
    QUALIFICATION_HEADING,
    is_column_header,
    section,
    split_body_text,
)
from tests.helpers import check, check_equal


# ─────────────────────────────── 일반 ───────────────────────────────

def test_NORMAL_splits_on_plain_headings():
    text = "자격요건\n- Java 3년\n우대사항\n- Kotlin"
    check_equal(split_body_text(text), ("- Java 3년", "- Kotlin"), "평범한 두 절")


def test_NORMAL_label_heading_keeps_the_rest_of_its_line():
    check_equal(section("자격요건: Java, Spring\n- 3년 이상", QUALIFICATION_HEADING),
                "Java, Spring\n- 3년 이상",
                "**라벨형 머리말 뒤의 글은 내용이다** — 버리면 요건 한 줄이 사라진다")


def test_NORMAL_no_heading_means_everything_is_qualification():
    text = "Java 를 잘 다루는 분\nSpring 경험자"
    check_equal(split_body_text(text), (text, ""),
                "못 나눴을 뿐 내용은 거기 있다. 우대사항에 복사해 넣지 않는다")


# ─────────────────────────────── 예외 ───────────────────────────────

def test_EXCEPTION_sentence_heading_leaves_no_residue():
    # 결함: `이런 분을 찾` 만 매칭돼 `습니다` 가 지원자격의 첫 줄이 됐다.
    # 실측 24칸(사람인 20 · 잡코리아 4, 2026-09-10).
    quality, _ = split_body_text("이런 분을 찾습니다\n· 웹 디자인이 가능한 분")
    check_equal(quality, "· 웹 디자인이 가능한 분", "`습니다` 가 남으면 안 된다")


def test_EXCEPTION_every_observed_residue_is_gone():
    """실측으로 CSV 에 들어갔던 잔여물 전부. 하나라도 남으면 그 칸이 다시 망가진다."""
    observed = [
        ("이런 분을 찾습니다", "습니다"),
        ("이런 분을 찾아요", "아요"),
        ("이런 분을 찾고 있어요", "고 있어요"),
        ("이런 분이면 더 좋아요 (우대 사항)", "좋아요 (우대 사항)"),
        ("이런 경험이 있다면 더 좋아요", "이 있다면 더 좋아요"),
    ]
    for line, residue in observed:
        both = split_body_text("%s\n- 내용" % line)
        joined = "\n".join(both)
        check(residue not in joined,
              "«%s» 에서 «%s» 가 남았다: %r" % (line, residue, both))
        check("- 내용" in joined, "잔여물을 버리면서 **내용까지 버리면 안 된다**")


def test_EXCEPTION_empty_text_is_two_empty_strings():
    check_equal(split_body_text(""), ("", ""), "빈 본문")
    check_equal(split_body_text(None), ("", ""), "본문 자체가 없는 경우")


def test_EXCEPTION_heading_with_nothing_after_it():
    check_equal(section("자격요건", QUALIFICATION_HEADING), "",
                "머리말만 있고 내용이 없으면 빈 문자열")


# ─────────────────────────────── 경계 ───────────────────────────────

def test_BOUNDARY_sentence_heading_mid_line_still_drops_the_whole_line():
    # 유도문은 어디서 끝나는지 못 집는다. 앞뒤 어느 쪽을 살려도 문장 조각이 남는다.
    quality, _ = split_body_text("저희는 이런 분을 찾고 있습니다!\n- Java")
    check_equal(quality, "- Java", "줄 전체를 머리말로 본다")


def test_BOUNDARY_label_heading_is_untouched_by_the_fix():
    for line, expected in (("지원자격 : Java", "Java"),
                           ("필수요건 - Python", "Python"),
                           ("자격조건| Go", "Go")):
        check_equal(section("%s\n- 뒷줄" % line, QUALIFICATION_HEADING),
                    "%s\n- 뒷줄" % expected,
                    "«%s» 는 라벨형이라 뒤가 내용이다" % line)


def test_BOUNDARY_column_header_line_does_not_start_a_section():
    # 절 이름을 둘 이상 나열한 줄은 표의 열 머리글이다. 절 시작으로 보면
    # 자격과 우대가 같은 자리에서 시작해 **두 칸에 같은 글이 들어간다**.
    line = "모집분야 업무내용 자격요건 및 우대조건"
    check(is_column_header(line), "열 머리글로 봐야 한다")
    quality, preference = split_body_text("%s\n가나다" % line)
    check(quality != preference or not preference,
          "두 칸에 똑같은 글이 들어가면 안 된다: %r" % (quality,))


def test_BOUNDARY_sentence_heading_that_is_also_a_preference_heading():
    text = "이런 분을 찾아요\n- React\n이런 분이면 더 좋아요\n- Next.js"
    check_equal(split_body_text(text), ("- React", "- Next.js"),
                "유도문 둘이 이어져도 절이 제대로 갈려야 한다")


def test_BOUNDARY_preference_section_ends_at_the_next_heading():
    text = "우대사항\n- Kotlin\n복리후생\n- 점심 제공"
    _, preference = split_body_text(text)
    check_equal(preference, "- Kotlin", "다음 머리말에서 끊긴다")


def test_BOUNDARY_bullet_marks_are_not_stripped_from_the_first_line():
    # 첫 줄에서만 글머리 기호를 떼면 뒷줄들과 어긋나 목록이 깨진다.
    got = section("자격요건\nㆍJava\nㆍPython", QUALIFICATION_HEADING)
    check_equal(got, "ㆍJava\nㆍPython", "기호는 그대로 둔다")


def test_BOUNDARY_extra_other_heading_still_ends_a_section():
    extra = re.compile(r"(포지션)")
    quality, _ = split_body_text("자격요건\n- Java\n포지션 소개\n- 회사 이야기",
                                 extra_other=extra)
    check_equal(quality, "- Java", "사이트가 더한 말도 절을 끝내야 한다")


def test_BOUNDARY_preference_heading_alone_still_fills_qualification():
    # 자격 머리말이 없고 우대 머리말만 있으면, 그 앞이 자격이다.
    quality, preference = split_body_text("- Java 3년\n우대사항\n- Kotlin")
    check_equal(quality, "- Java 3년", "우대 앞은 자격으로 본다")
    check_equal(preference, "- Kotlin", "우대는 우대로")


def test_BOUNDARY_sentence_heading_vocabulary_matches_both_tables():
    # `이런 분을 찾`·`이런 분과` 는 자격 쪽, `이런 분이면 더`·`이런 경험` 은 우대 쪽에도
    # 들어 있다. 한쪽만 고치면 나머지에서 잔여물이 다시 나온다.
    check(QUALIFICATION_HEADING.search("이런 분과 함께해요"), "자격 쪽 유도문")
    check(PREFERENCE_HEADING.search("이런 경험 있으신 분"), "우대 쪽 유도문")
    for line in ("이런 분과 함께 일하고 싶어요", "이런 경험 있으신 분을 찾아요"):
        joined = "\n".join(split_body_text("%s\n- 내용" % line))
        check("- 내용" in joined, "«%s» 의 내용이 살아 있어야 한다" % line)
