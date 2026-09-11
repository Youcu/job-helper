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
    heading_names,
    is_column_header,
    is_sectioned,
    section,
    stacked_headers,
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


# ── 여러 절로 나뉜 공고에 자격 절이 없을 때 ──────────────────────────────

_TABLE = """회사 소개
저희는 좋은 회사입니다
모집부문
백엔드 개발
담당 업무
서버 개발
우대 사항
ㆍKubernetes 경험
근무조건
주5일
복리후생
중식 제공
전형절차
서류 → 면접"""


def test_NORMAL_sectioned_posting_without_qualifications_leaves_it_empty():
    """**결함이었다.** 실측 `rec_idx=54856893` 은 절이 일곱인데 자격 절만 없어서,
    회사 소개부터 우대 앞까지 **2,894자**가 통째로 지원자격이 됐다. 전량 29칸이 그 꼴이었다.

    나뉜 문서에 자격 절이 없으면 **진짜로 없는 것**이다. 차 있지만 틀린 것보다 비어 있는
    편이 낫다 — 틀린 값은 다음 단계가 그대로 믿는다 (2026-09-11 사용자 판단).
    """
    quality, preference = split_body_text(_TABLE)
    check_equal(quality, "", "회사 소개와 담당업무가 지원자격에 들어가면 안 된다")
    check_equal(preference, "ㆍKubernetes 경험", "우대는 제대로 나와야 한다")


def test_BOUNDARY_a_posting_with_few_headings_still_falls_back():
    """머리말이 거의 없는 공고는 **나누지 못한 것뿐이고 내용은 거기 있다.**

    실측에서 이런 공고가 한 건 있었다 — 절 이름이 `이런 경험` 하나뿐이었고, 그 앞 글이
    진짜 자격이었다. 그것까지 비우면 멀쩡한 재료를 버린다.
    """
    text = "Java 를 다루는 분\nSpring 경험자\n이런 경험이 있으면 좋아요\nGo"
    check(not is_sectioned(text), "절 이름이 적으면 나뉜 문서가 아니다")
    quality, preference = split_body_text(text)
    check_equal(quality, "Java 를 다루는 분\nSpring 경험자", "우대 앞이 자격이다")
    check_equal(preference, "Go", "우대")


def test_BOUNDARY_no_heading_at_all_still_gives_the_whole_body():
    text = "Java 를 잘 다루는 분\nSpring 경험자"
    check_equal(split_body_text(text), (text, ""), "못 나눴을 뿐 내용은 거기 있다")


def test_BOUNDARY_sectioned_is_counted_by_distinct_names():
    # 같은 이름이 표에서 여러 번 반복돼도 한 가지로 센다 — 안 그러면 표 한 칸짜리
    # 공고가 '나뉜 문서' 로 잘못 판정된다.
    repeated = "자격요건\n가\n자격요건\n나\n자격요건\n다"
    check_equal(heading_names(repeated), {"자격요건"}, "같은 이름은 하나로")
    check(not is_sectioned(repeated), "한 가지 이름이 반복된 것은 나뉜 문서가 아니다")


def test_BOUNDARY_qualification_heading_wins_over_the_rule():
    # 나뉜 문서라도 **자격 절이 있으면** 그것을 쓴다. 규칙은 없을 때만 작동한다.
    text = _TABLE.replace("담당 업무", "자격요건")
    quality, _ = split_body_text(text)
    check_equal(quality, "서버 개발", "자격 절이 있으면 그 내용이다")


# ── `문의` 는 머리말로 쓰이는 모양만 받는다 ─────────────────────────────

def test_EXCEPTION_inquiry_in_prose_does_not_end_a_section():
    """**결함이었다.** `문의` 만 두면 산문에서 15번 잘못 잡혔다 (실측 52건).

    `OTHER_HEADING` 에 있어서 **절을 일찍 끊는다** — 자격·우대가 문장 하나 때문에
    중간에서 잘린다.
    """
    for prose in ("ㆍ고객문의 응대 및 니즈 파악", "고객 문의 대응 및 기술 지원",
                  "전화문의 사절입니다", "문의 해주세요"):
        text = "자격요건\n%s\nㆍJava 경험" % prose
        quality, _ = split_body_text(text)
        check("Java" in quality, "«%s» 에서 절이 끊겼다: %r" % (prose, quality))


def test_BOUNDARY_inquiry_as_a_real_heading_still_ends_a_section():
    for real in ("문의사항", "문의처", "채용문의", "문의 : hr@example.com"):
        text = "자격요건\nㆍJava 경험\n%s\n02-000-0000" % real
        quality, _ = split_body_text(text)
        check("02-000-0000" not in quality,
              "«%s» 는 머리말이라 절을 끊어야 한다: %r" % (real, quality))


# ── 세로로 쌓인 열 머리글 ────────────────────────────────────────────────

_STACKED = """모집부문
채용부서
포지션명
담당업무
자격요건
보안
연구소
SSE팀
- 네트워크 트래픽 실시간 분석·제어 엔진 개발
- C/C++ 개발 가능자"""


def test_NORMAL_stacked_column_headers_do_not_start_a_section():
    """**결함이었다.** 표 양식은 열 이름을 한 줄에 하나씩 뽑아 놓는데,
    `is_column_header` 는 "한 줄에 이름 둘 이상" 만 봐서 못 잡았다.

    그래서 `자격요건` 이 절 시작으로 잡혀 **표 전체가 지원자격이 됐다** —
    실측 `rec_idx=53930400` 이 3,180자, `rec_idx=54573076` 이 584자. 전량 18칸이었다.
    """
    check_equal(sorted(stacked_headers(_STACKED.split("\n"))), [3, 4],
                "바로 옆 줄에도 머리말이면 열 이름이다")
    quality, _ = split_body_text(_STACKED)
    check("네트워크 트래픽" not in quality,
          "표 내용이 지원자격에 들어가면 안 된다: %r" % quality[:60])


def test_BOUNDARY_real_headings_with_content_between_are_not_stacked():
    # **진짜 절 머리말은 사이에 내용이 있다.** 이걸 못 지키면 멀쩡한 공고가 전부 빈다.
    text = "자격요건\nㆍJava 경험\n우대사항\nㆍGo 경험"
    check_equal(stacked_headers(text.split("\n")), set(), "쌓인 것이 없다")
    check_equal(split_body_text(text), ("ㆍJava 경험", "ㆍGo 경험"), "정상 공고는 그대로")


def test_BOUNDARY_stacked_headers_do_not_end_a_section_either():
    """열 머리글은 절을 **끝내지도** 않는다. 끝내면 표 한 칸에서 절이 잘린다.

    **이 규칙의 한계가 여기 있다.** 머리말 둘이 붙어 있으면 표의 열 이름으로 보므로,
    진짜 절 머리말 둘이 내용 없이 이어지는 공고에서는 앞 절이 뒤를 삼킨다.
    실측 52건에서 그런 공고는 안 나왔지만 없다고 증명한 것은 아니다 —
    나오면 `stacked_headers` 에 "몇 줄까지를 한 블록으로 볼지" 를 더해야 한다.
    """
    text = "자격요건\nㆍJava\n담당업무\n근무조건\nㆍ표 데이터"
    quality, _ = split_body_text(text)
    check("ㆍJava" in quality, "자격 내용은 들어 있어야 한다")
    check("담당업무" in quality,
          "지금은 붙어 있는 둘을 열 이름으로 보므로 절이 안 끊긴다 — 위 docstring 참조")


def test_BOUNDARY_a_lone_heading_is_still_a_section():
    text = "모집부문\n백엔드\n자격요건\nㆍJava 경험"
    check_equal(stacked_headers(text.split("\n")), set(), "사이에 내용이 있으면 안 쌓인 것")
    quality, _ = split_body_text(text)
    check_equal(quality, "ㆍJava 경험", "단독 머리말은 절 시작이다")
