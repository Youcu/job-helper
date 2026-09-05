"""`_common/html_text.py` — 보이는 글만 남기는가.

**통과시키려고 쓴 테스트가 아니다.** 처음 쓴 구현을 적대적으로 읽고 "여기서 틀릴 것 같다" 는
곳을 먼저 찔렀고, 실제로 네 군데가 틀렸다. 그 자리에는 `# 결함:` 을 붙여 뒀다.

숨김 판정이 틀리는 방향은 둘이고, 값이 다르다.

- 숨긴 것을 못 알아보면 → **안 보이는 글이 본문으로 들어온다** (틀린 데이터)
- 멀쩡한 것을 숨김으로 보면 → **그 문단이 사라진다** (없어지는 데이터)

그래서 두 방향을 따로 테스트한다.
"""
from __future__ import annotations

from _common.html_text import (
    is_hidden_style,
    split_visible,
    to_text,
    visible_text,
)
from tests.helpers import check, check_equal


# ─────────────────────────────── 일반 ───────────────────────────────

def test_NORMAL_plain_markup_keeps_its_text():
    check_equal(visible_text("<p>Java 와 <b>Spring</b> 경험</p>"),
                "Java 와 Spring 경험", "평범한 마크업은 글이 그대로 남아야 한다")


def test_NORMAL_tags_become_spaces_not_nothing():
    # 결함: 태그를 빈 문자열로 지우면 표의 칸이 붙어 `JavaC` 라는 없는 기술이 생긴다.
    check_equal(visible_text("<td>Java</td><td>C</td>"), "Java C",
                "태그 자리는 공백이어야 인접한 칸이 안 붙는다")


def test_NORMAL_hidden_block_is_separated_not_deleted():
    visible, hidden = split_visible('<p>보임</p><div style="display:none">숨김</div>')
    check_equal(to_text(visible), "보임", "보이는 쪽")
    check_equal(to_text(hidden), "숨김", "숨긴 쪽도 돌려줘야 사이트가 따로 해석할 수 있다")


def test_NORMAL_entities_are_unescaped():
    check_equal(visible_text("<p>C&amp;C++ &lt;태그&gt;</p>"), "C&C++ <태그>",
                "HTML 엔티티를 안 풀면 &amp; 가 기술 이름에 섞인다")


def test_NORMAL_real_saramin_hidden_seo_block_is_dropped():
    # 실제로 겪은 모양 — 본문은 이미지 한 장이고 옆 td 에 분류 덤프가 숨어 있었다.
    fragment = (
        '<table><tr><td><img src="a.png" alt="채용"></td></tr>'
        '<tr><td style="display:block; height: 0; width: 0; font-size: 0;'
        ' line-height: 0; margin: 0; padding: 0; overflow:hidden;">'
        'IT개발·데이터 &gt; 기술스택 &gt; Java Python Kubernetes</td></tr></table>'
    )
    check_equal(visible_text(fragment), "", "화면에 글자가 없으면 결과도 비어야 한다")


# ─────────────────────────────── 예외 ───────────────────────────────

def test_EXCEPTION_empty_and_none_like_input():
    for value in ("", None):
        check_equal(visible_text(value or ""), "", "빈 입력은 빈 결과다")
        check_equal(split_visible(value or ""), ("", ""), "빈 입력은 빈 쌍이다")


def test_EXCEPTION_unclosed_hidden_tag_swallows_rest_not_crashes():
    # 닫는 태그가 없는 깨진 HTML. 예외로 죽지 말고, 남은 것을 숨김으로 보고 끝내야 한다.
    visible, hidden = split_visible('<p>보임</p><div style="display:none">끝까지 안 닫힘')
    check_equal(to_text(visible), "보임", "닫히지 않아도 앞쪽은 살아야 한다")
    check("안 닫힘" in to_text(hidden), "닫히지 않은 숨김은 끝까지 숨김으로 본다")


def test_EXCEPTION_script_and_style_bodies_are_not_text():
    fragment = "<p>본문</p><script>var java='Java';</script><style>.a{font:Python}</style>"
    check_equal(visible_text(fragment), "본문",
                "script/style 안의 글자는 화면에 안 나온다")


def test_EXCEPTION_data_style_attribute_is_not_style():
    # 결함: `style\s*=` 로만 찾으면 `data-style` 도 걸려 멀쩡한 문단이 통째로 사라졌다.
    check_equal(visible_text('<td data-style="display:none">보여야 한다</td>'),
                "보여야 한다", "이름이 style 로 끝나는 다른 속성을 style 로 읽으면 안 된다")


def test_EXCEPTION_single_quoted_style_is_detected():
    # 결함: 큰따옴표만 받으면 작은따옴표로 숨긴 글이 본문에 새어 든다 — 틀린 데이터가 들어오는 쪽이다.
    check_equal(visible_text("<td style='display:none'>숨김</td>보임"), "보임",
                "작은따옴표 style 도 숨김으로 봐야 한다")


def test_EXCEPTION_uppercase_style_and_value():
    check_equal(visible_text('<td STYLE="DISPLAY:NONE">숨김</td>'), "",
                "대소문자를 가리면 안 된다")


def test_EXCEPTION_void_element_does_not_swallow_the_rest():
    # 결함이 될 뻔한 곳: <img> 에 균형 스캔을 걸면 닫는 태그가 없어 문서 끝까지 삼킨다.
    check_equal(visible_text('<img src="a.png"><p>뒤에 오는 본문</p>'), "뒤에 오는 본문",
                "빈 요소 뒤의 글이 살아 있어야 한다")


def test_EXCEPTION_self_closed_div_is_not_treated_as_open():
    check_equal(visible_text('<div/><p>본문</p>'), "본문",
                "자기 완결 태그는 열지도 닫지도 않는다")


# ─────────────────────────────── 경계 ───────────────────────────────

def test_BOUNDARY_zero_value_must_be_exactly_zero():
    # 결함: 문자열 포함으로만 보면 `font-size:0.9rem` 과 `opacity:0.85` 가 숨김이 된다.
    #       작은 글씨로 쓴 우대사항 문단이 통째로 사라진다.
    check(not is_hidden_style("font-size:0.9rem"), "0.9rem 은 보이는 크기다")
    check(not is_hidden_style("opacity:0.85"), "0.85 는 보이는 투명도다")
    check(is_hidden_style("font-size:0"), "정확히 0 이면 숨김이다")
    check(is_hidden_style("opacity: 0"), "공백이 있어도 0 은 0 이다")


def test_BOUNDARY_zero_with_unit_still_counts_as_zero():
    check(is_hidden_style("width:0px;height:0px"), "0px 는 0 이다")
    check(is_hidden_style("width: 0; height: 0"), "공백이 있어도 0 이다")


def test_BOUNDARY_one_zero_dimension_is_not_enough():
    # height 만 0 이고 넘치게 두는 멀쩡한 레이아웃이 있다. 둘 다 0 이어야 숨김이다.
    check(not is_hidden_style("height:0"), "세로만 0 인 것은 숨김이 아니다")
    check(not is_hidden_style("width:0"), "가로만 0 인 것은 숨김이 아니다")


def test_BOUNDARY_max_width_zero_is_not_width_zero():
    check(not is_hidden_style("max-width:0;max-height:0"),
          "max- 접두가 붙은 것은 width/height 가 아니다")


def test_BOUNDARY_nested_hidden_inside_hidden():
    visible, hidden = split_visible(
        '<div style="display:none">겉<div style="display:none">속</div></div>보임')
    check_equal(to_text(visible), "보임", "중첩된 숨김이 바깥을 넘어 새면 안 된다")
    check_equal(to_text(hidden), "겉 속", "안쪽까지 통째로 숨김이다")


def test_BOUNDARY_visible_inside_hidden_stays_hidden():
    # 숨긴 부모 안의 자식은 스타일이 멀쩡해도 화면에 안 나온다.
    check_equal(visible_text('<div style="display:none"><p style="color:red">글</p></div>'),
                "", "숨긴 부모 안은 전부 숨김이다")


def test_BOUNDARY_whitespace_only_body_is_empty_string():
    check_equal(visible_text("<div>   \n\t  </div>"), "", "공백만 있으면 빈 문자열이다")
