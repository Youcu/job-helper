"""공고 본문을 지원자격과 우대사항으로 가른다.

**사이트 지식이 아니라 한국 채용공고 일반의 말이다.** `자격요건` `우대사항` `담당업무` 는
어느 사이트에서 긁든 같은 뜻이라, 사이트마다 따로 두면 규칙이 조용히 갈라진다 —
실제로 사람인과 잡코리아에서 로직은 같은데 **왜 그런지 적은 주석만 한쪽에서 사라졌다.**
그래서 여기로 모았다. 사이트가 할 일은 본문에서 보이는 글을 뽑아 넘기는 것까지다.

머리말 목록은 **닫힌 부류가 아니라 관측치**다. 놓치는 것이 있을 수 있어서, 못 찾으면
본문 전체를 지원자격으로 돌린다 — 틀린 절 구분을 만들지 않는다.

## 로직은 같지만 **어휘는 사이트마다 다르다**

같은 말이 사이트마다 다르게 쓰인다. `포지션` 이 그랬다 — 잡코리아 공고는 `포지션 소개`
를 절 머리말로 쓰는데, 사람인 표 양식은 `포지션 및 자격요건` 을 **열 머리글**로 쓴다.
그래서 `포지션` 을 여기 넣으면 사람인에서 그 줄이 절 이름을 둘 담은 것이 되어 열 머리글로
판정되고(`is_column_header`), 절이 안 끊겨 **지원자격이 문서를 통째로 삼켰다**.
빼면 반대로 잡코리아 23행에서 진짜 자격이 사라지고 공고 제목만 남았다.

그래서 기본 어휘는 여기 두되, 사이트는 `extra_other` 로 자기 말을 더한다.
**한 줄 더하는 것이 안전한 일이 아니다** — 더한 이름이 다른 이름과 **한 줄에 같이 있는
경우**를 반드시 실제 데이터로 재 보라. 랜덤 입력으로는 방향밖에 안 보인다.
"""
from __future__ import annotations

import re

QUALIFICATION_HEADING = re.compile(
    r"(자격\s*요건|지원\s*자격|자격\s*조건|자격\s*사항|필수\s*요건|필수\s*사항"
    r"|이런\s*분을\s*찾|이런\s*분과)")
PREFERENCE_HEADING = re.compile(
    r"(우대\s*사항|우대\s*조건|우대\s*요건|우대\s*능력|이런\s*분이면\s*더|이런\s*경험)")
OTHER_HEADING = re.compile(
    r"(담당\s*업무|주요\s*업무|모집\s*부문|모집\s*분야|근무\s*조건|근무\s*환경"
    r"|전형\s*절차|채용\s*절차|제출\s*서류|접수\s*방법|접수\s*기간|복리\s*후생"
    r"|기타\s*사항|유의\s*사항|문의)")


# CSV 한 칸의 최대 길이. 넘으면 잘라서 표시한다 — 표 계산기가 긴 칸에서 느려진다.
MAX_FIELD_LENGTH = 4000


def split_body_text(text: str, *, extra_other: re.Pattern[str] | None = None
                    ) -> tuple[str, str]:
    """줄로 나뉜 본문 글 → (지원자격, 우대사항).

    받는 것은 **HTML 이 아니라 이미 뽑아낸 글**이다. 어디서 어떻게 뽑을지는 사이트마다
    다르므로 (사람인은 본문 컨테이너, 잡코리아는 iframe) 그 일은 사이트가 한다.

    `extra_other` 로 그 사이트에서만 절을 끝내는 말을 더한다 — 위 "어휘는 사이트마다
    다르다" 를 보라.

    머리말을 못 찾으면 **본문 전체를 지원자격으로** 돌린다 — 내용은 거기 있는데 우리가
    못 나눈 것뿐이다. 우대사항은 못 찾으면 빈칸이다. 지원자격을 복사해 넣으면 없는
    구분을 지어내는 것이다.
    """
    if not text:
        return "", ""
    headings = _headings(extra_other)
    qualification = section(text, QUALIFICATION_HEADING, headings)
    preference = section(text, PREFERENCE_HEADING, headings)
    if not qualification:
        qualification = (until_first_heading(text, PREFERENCE_HEADING, headings)
                         if preference else text)
    return trim(qualification), trim(preference)


def _headings(extra_other: re.Pattern[str] | None) -> tuple[re.Pattern[str], ...]:
    base = (QUALIFICATION_HEADING, PREFERENCE_HEADING, OTHER_HEADING)
    return base + (extra_other,) if extra_other else base


def heading_kinds(line: str, headings: tuple[re.Pattern[str], ...] | None = None) -> int:
    """이 줄이 몇 종류의 절 이름을 담고 있는가."""
    return sum(bool(pattern.search(line)) for pattern in (headings or _headings(None)))


def is_column_header(line: str, headings=None) -> bool:
    """절 이름을 여럿 나열한 줄 — 절의 시작이 아니라 **표의 열 머리글**이다.

    모집부문 표는 `모집분야 업무내용 자격요건 및 우대조건` 같은 줄로 시작한다. 이걸 절
    시작으로 보면 자격과 우대가 **같은 자리에서 시작해 같은 글을 담는다** — 사람인에서
    두 칸에 똑같은 내용이 들어간 행이 9건 나왔다.

    절 이름 하나만 든 줄은 진짜 머리말이다. 둘 이상이면 머리글이다.
    """
    return heading_kinds(line, headings) > 1


def is_heading(line: str, headings=None) -> bool:
    """어느 절이든 머리말인가.

    자기 머리말과 `OTHER_HEADING` 만 보면 **지원자격이 우대사항을 삼킨다** — 우대사항은
    둘 중 어디에도 없기 때문이다. 절의 끝은 "다음 머리말" 이지 "내가 아는 다른 머리말"
    이 아니다.
    """
    return heading_kinds(line, headings) > 0


def section(text: str, heading: re.Pattern[str], headings=None) -> str:
    """머리말이 있는 줄 다음부터, **다음 머리말이 나오기 전까지**."""
    lines = text.split("\n")
    start = next((index for index, line in enumerate(lines)
                  if heading.search(line) and not is_column_header(line, headings)), None)
    if start is None:
        return ""
    collected = []
    # 머리말 뒤에 붙은 구두점만 벗긴다. **글머리 기호(`ㆍ`)는 벗기지 않는다** —
    # 첫 줄에서만 떼면 `ㆍ 통계...` 처럼 기호가 남은 뒷줄들과 어긋나 목록이 깨진다.
    tail = heading.split(lines[start], maxsplit=1)[-1].lstrip(" :·-|]）)")
    if tail.strip():
        collected.append(tail.strip())
    for line in lines[start + 1:]:
        if is_heading(line, headings) and not is_column_header(line, headings):
            break
        if line.strip():
            collected.append(line.strip())
    return "\n".join(collected).strip()


def until_first_heading(text: str, heading: re.Pattern[str], headings=None) -> str:
    """머리말이 처음 나오는 줄 앞까지."""
    kept = []
    for line in text.split("\n"):
        if heading.search(line) and not is_column_header(line, headings):
            break
        if line.strip():
            kept.append(line.strip())
    return "\n".join(kept).strip()


def trim(text: str) -> str:
    if len(text) <= MAX_FIELD_LENGTH:
        return text
    return text[:MAX_FIELD_LENGTH].rstrip() + " …"
