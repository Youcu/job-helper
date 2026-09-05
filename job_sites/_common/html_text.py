"""HTML 조각에서 **사람 눈에 보이는 글**만 뽑는다. 사이트 공통.

Wanted 는 API 로 본문을 받아 이게 필요 없지만, HTML 을 긁는 사이트는 전부 이 문제를 만난다.
공고 본문 안에 **화면에 안 보이는 글**이 섞여 있고, 태그만 걷어내면 그게 본문인 척 딸려 온다.

사람인에서 실제로 겪은 것 — 본문이 이미지 한 장이고, 그 옆 `<td>` 에 이런 게 붙어 있었다.

    <td style="display:block; height:0; width:0; font-size:0; overflow:hidden;">
      IT개발·데이터 > 직무·직업 > 백엔드/서버개발  IT개발·데이터 > 기술스택 > Java  ... (54개)
    </td>

태그만 걷어내고 기술 이름을 찾으면 **61개**가 나온다. 화면에는 글자가 하나도 없는데도.
`visible_text()` 를 거치면 0개가 된다.

    visible, hidden = split_visible(fragment)   # 보이는 쪽 / 숨긴 쪽
    text = visible_text(fragment)               # 보이는 쪽의 글만

숨긴 쪽도 돌려주는 이유는, 그게 쓰레기가 아니라 **공고 자신의 분류 값**일 때가 있어서다.
버릴지 따로 해석할지는 사이트가 정한다. 여기서는 섞이지만 않게 갈라 놓는다.

## 무엇을 숨김으로 볼 것인가

CSS 로 뭔가를 감추는 방법은 **열린 집합**이다 — 다 적을 수 없다. 그래서 여기 목록은
완전하지 않고, 완전한 척하지도 않는다. 대신 **틀리는 방향**을 골랐다.

- 목록에 없는 수법을 놓치면 → 안 보이는 글이 본문에 섞인다 (**틀린 데이터가 들어온다**)
- 멀쩡한 걸 숨김으로 잘못 보면 → 그 문단이 빠진다 (**데이터가 없어진다**)

둘 중에는 없어지는 편이 낫다. 그래서 애매하면 **숨김으로 본다.**
그리고 이건 방어선 하나일 뿐이다 — 사이트 쪽에서 "보이는 본문이 너무 짧다" 를
따로 재서 이미지 본문을 걸러야 한다 (`saramin/lib/skills.py` 참고).
"""
from __future__ import annotations

import html as html_module
import re

# 여는 태그. 자기 완결 태그(`<br/>`)와 빈 요소는 안쪽이 없으니 따로 다룬다.
_OPEN_TAG = re.compile(r"<([a-zA-Z][\w-]*)\b([^>]*)>")
# 앞의 `(?:^|\s)` 가 없으면 `data-style="display:none"` 같은 다른 속성까지 style 로 읽는다.
# 따옴표는 두 가지를 다 받는다 — 작은따옴표를 놓치면 숨긴 글이 본문으로 새어 든다.
_STYLE_ATTR = re.compile(r"(?:^|\s)style\s*=\s*(\"[^\"]*\"|'[^']*')", re.IGNORECASE)
_SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.DOTALL | re.IGNORECASE)
_ANY_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")

# 안쪽을 가질 수 없는 요소. 균형 스캔을 걸면 문서 끝까지 삼킨다.
VOID_ELEMENTS = frozenset(
    "area base br col embed hr img input link meta param source track wbr".split()
)

# 인라인 스타일이 이 중 하나면 화면에 글자가 안 나온다.
# 공백을 모두 지운 뒤 검사하므로 `font-size: 0` 도 `font-size:0` 으로 걸린다.
#
# **값이 딱 0 이어야 한다.** `(?![.\d])` 가 없으면 `font-size:0.9rem` 과 `opacity:0.85`
# 처럼 멀쩡한 스타일이 숨김으로 잡혀 그 문단이 통째로 사라진다. `0px` 은 0 이 맞으므로
# 숫자·소수점만 막고 단위는 받는다.
_HIDDEN_MARKS = (
    re.compile(r"display:none"),
    re.compile(r"visibility:hidden"),
    re.compile(r"font-size:0(?![.\d])"),
    re.compile(r"opacity:0(?![.\d])"),
)
# 크기를 0 으로 눌러 감추는 수법. 하나만으로는 부족하고 가로·세로가 함께 0 이어야 한다
# — `height:0` 만 쓰고 안이 넘치게 두는 멀쩡한 레이아웃이 있다.
_ZERO_BOX = (re.compile(r"(?<!max-)(?<!min-)width:0(?![.\d])"),
             re.compile(r"(?<!max-)(?<!min-)height:0(?![.\d])"))


def is_hidden_style(style: str) -> bool:
    """인라인 스타일 문자열이 요소를 화면에서 감추는가."""
    if not style:
        return False
    packed = style.lower().replace(" ", "")
    if any(mark.search(packed) for mark in _HIDDEN_MARKS):
        return True
    return all(mark.search(packed) for mark in _ZERO_BOX)


def split_visible(fragment: str) -> tuple[str, str]:
    """HTML 조각을 (보이는 부분, 숨긴 부분) 으로 가른다.

    숨긴 요소는 **안쪽까지 통째로** 옮긴다. 여는 태그만 지우면 그 안의 글이 남는다.
    """
    if not fragment:
        return "", ""
    visible: list[str] = []
    hidden: list[str] = []
    cursor = 0
    while True:
        match = _OPEN_TAG.search(fragment, cursor)
        if not match:
            visible.append(fragment[cursor:])
            break
        tag = match.group(1).lower()
        attrs = match.group(2)
        self_closing = attrs.rstrip().endswith("/")
        if self_closing or tag in VOID_ELEMENTS:
            visible.append(fragment[cursor:match.end()])
            cursor = match.end()
            continue
        style = _STYLE_ATTR.search(attrs)
        if style and is_hidden_style(style.group(1)[1:-1]):
            visible.append(fragment[cursor:match.start()])
            end = _closing_index(fragment, match.start(), tag)
            hidden.append(fragment[match.start():end])
            cursor = end
        else:
            visible.append(fragment[cursor:match.end()])
            cursor = match.end()
    return "".join(visible), "".join(hidden)


def _closing_index(fragment: str, start: int, tag: str) -> int:
    """`start` 의 여는 태그와 짝이 되는 닫는 태그 뒤 위치. 못 닫혔으면 끝까지."""
    pattern = re.compile(r"<(/?)%s\b[^>]*?(/?)>" % re.escape(tag), re.IGNORECASE)
    depth = 0
    for found in pattern.finditer(fragment, start):
        if found.group(2) == "/":       # <div/> 는 열지도 닫지도 않는다
            continue
        depth += -1 if found.group(1) else 1
        if depth == 0:
            return found.end()
    return len(fragment)


def to_text(fragment: str) -> str:
    """태그를 걷어내고 글만 남긴다. 숨김 여부는 보지 않는다."""
    if not fragment:
        return ""
    without_code = _SCRIPT_OR_STYLE.sub(" ", fragment)
    # 태그 자리를 공백으로 바꾼다 — 안 그러면 `<td>Java</td><td>C</td>` 가 `JavaC` 가 된다
    unescaped = html_module.unescape(_ANY_TAG.sub(" ", without_code))
    return _WHITESPACE.sub(" ", unescaped).strip()


def visible_text(fragment: str) -> str:
    """화면에 보이는 글만. 산문 매칭에 넘길 것은 이것이다."""
    visible, _ = split_visible(fragment)
    return to_text(visible)


# 화면에서 줄을 바꾸는 요소들. 이 경계를 살려야 "자격요건" 같은 머리말로 절을 나눌 수 있다.
_BLOCK_ELEMENTS = (
    "p div br hr li tr h1 h2 h3 h4 h5 h6 ul ol table thead tbody "
    "section article header footer blockquote pre dt dd"
).split()
_BLOCK_BOUNDARY = re.compile(
    r"</?(?:%s)\b[^>]*>" % "|".join(_BLOCK_ELEMENTS), re.IGNORECASE)
_BLANK_LINES = re.compile(r"\n{2,}")
_SPACES = re.compile(r"[^\S\n]+")


def visible_lines(fragment: str) -> str:
    """화면에 보이는 글을 **줄 구조를 살려서**.

    `visible_text()` 는 모든 공백을 하나로 뭉치므로 "자격요건" 다음에 무엇이 오는지를
    알 수 없다. 절을 나눠 읽어야 하는 곳에서는 이쪽을 쓴다.

    태그를 공백으로만 바꾸면 `<li>Java</li><li>C</li>` 가 한 줄이 되어, 목록 항목
    하나하나가 붙는다. 그래서 블록 요소 경계는 줄바꿈으로 바꾼다.
    """
    visible, _ = split_visible(fragment or "")
    without_code = _SCRIPT_OR_STYLE.sub(" ", visible)
    with_breaks = _BLOCK_BOUNDARY.sub("\n", without_code)
    text = html_module.unescape(_ANY_TAG.sub(" ", with_breaks))
    text = _SPACES.sub(" ", text)
    return _BLANK_LINES.sub("\n", "\n".join(
        line.strip() for line in text.split("\n"))).strip()
