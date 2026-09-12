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

from _common.store import trim                                  # noqa: F401

# ## 머리말에는 두 갈래가 있다 — 라벨과 유도문
#
# **라벨형**은 이름표다. `자격요건: Java, Spring` 처럼 같은 줄 뒤에 내용이 이어질 수 있고,
# 그 나머지는 살려야 한다.
#
# **유도문형**은 문장이다. `이런 분을 찾습니다`. 이름이 어디서 끝나는지 정규식으로 못 집기
# 때문에, 매칭된 앞부분만 잘라 내면 **문장의 꼬리가 내용인 척 남는다.** 실제로 그랬다 —
# `이런 분을 찾` 이 매칭되어 `습니다` 가 지원자격의 첫 줄이 됐고, 실측 24칸이 그 꼴이었다
# (사람인 20 · 잡코리아 4, 2026-09-10). 관측된 잔여물:
#
#     '습니다' · '아요' · '고 있어요' · '이 있다면 더 좋아요' · '좋아요 (우대 사항)' · '입니다.)'
#
# 그래서 **유도문형은 줄 전체를 머리말로 보고 나머지를 버린다.** 살리면 쓰레기가 들어오고,
# 버리면 그 줄의 꼬리만 잃는다 — 틀려야 한다면 누락 쪽이다.
SENTENCE_HEADING = re.compile(
    r"(이런\s*분을\s*찾|이런\s*분과|이런\s*분이면\s*더|이런\s*경험)")

QUALIFICATION_HEADING = re.compile(
    r"(자격\s*요건|지원\s*자격|자격\s*조건|자격\s*사항|필수\s*요건|필수\s*사항"
    r"|이런\s*분을\s*찾|이런\s*분과)")
PREFERENCE_HEADING = re.compile(
    r"(우대\s*사항|우대\s*조건|우대\s*요건|우대\s*능력|이런\s*분이면\s*더|이런\s*경험)")
OTHER_HEADING = re.compile(
    r"(담당\s*업무|주요\s*업무|모집\s*부문|모집\s*분야|근무\s*조건|근무\s*환경"
    r"|전형\s*절차|채용\s*절차|제출\s*서류|접수\s*방법|접수\s*기간|복리\s*후생"
    r"|기타\s*사항|유의\s*사항"
    # `문의` 만 두면 산문에서 15번 잘못 잡혔다 (실측 52건) —
    # `고객문의 응대 및 니즈 파악` · `전화문의 사절` · `문의 해주세요`.
    # 이것이 절을 **일찍 끊어** 자격·우대가 중간에 잘린다. 머리말로 쓰이는 모양만 받는다.
    r"|문의\s*(?:사항|처)|채용\s*문의|문의\s*:|^\s*문의\s*$)")




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
        qualification = "" if is_sectioned(text, headings) else (
            until_first_heading(text, PREFERENCE_HEADING, headings)
            if preference else text)
    return trim(qualification), trim(preference)


# 절 이름이 이만큼 나오면 **여러 절로 나뉜 문서**로 본다.
#
# 실측(2026-09-11, 사람인·잡코리아 52건)에서 경계가 깨끗하게 갈렸다. 자격 절이 없어
# 대체 규칙을 타는 공고는 절 이름이 **8~11가지**(사람인 표 양식)거나 **1가지**(대화체
# 유도문 하나)였고, 그 사이가 없었다. 3은 그 틈 안이다.
SECTIONED_AT = 3


def heading_names(text: str, headings=None) -> set[str]:
    """본문에 나오는 절 이름들. 같은 이름이 여러 번 나와도 하나로 센다."""
    found = set()
    for line in (text or "").split("\n"):
        for pattern in (headings or _headings(None)):
            match = pattern.search(line)
            if match:
                found.add(match.group().replace(" ", ""))
    return found


def is_sectioned(text: str, headings=None) -> bool:
    """이 공고가 **여러 절로 나뉘어 있는가.**

    나뉘어 있는데도 자격 절이 없으면 **그 공고에 자격 절이 진짜로 없는 것**이다.
    그때 본문 전체를 자격으로 돌리면 회사 소개와 담당업무가 지원자격 칸에 들어간다 —
    실측 29칸이 그 꼴이었다. 예를 들어 `rec_idx=54856893` 은 절이
    `모집분야·모집부문·담당 업무·우대 사항·근무조건·복리후생·전형절차…` 인데 자격 절만
    없어서, 회사 소개부터 우대 앞까지 **2,894자**가 통째로 지원자격이 됐다.

    **차 있지만 틀린 것보다 비어 있는 편이 낫다** — 틀린 값은 다음 단계가 그대로 믿는다
    (2026-09-11 사용자 판단).

    반대로 머리말이 거의 없는 공고는 **나누지 못한 것뿐이고 내용은 거기 있다.**
    그 경우는 지금처럼 본문 전체를 자격으로 돌린다.
    """
    return len(heading_names(text, headings)) >= SECTIONED_AT


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


def stacked_headers(lines: list[str], headings=None) -> set[int]:
    """**세로로 쌓인 열 머리글** 줄의 번호들.

    사람인·잡코리아 표 양식은 열 이름을 한 줄에 하나씩 뽑아 놓는다. `is_column_header`
    는 "한 줄에 이름이 둘 이상" 만 보므로 이 모양을 못 잡는다 — 실측:

        [ 6] 담당업무          ← 열 이름
        [ 7] 자격요건          ← 열 이름 (바로 다음 줄!)
        [ 8] 보안              ← 여기부터 표의 데이터
        [ 9] 연구소

    그러면 `자격요건` 이 절 시작으로 잡혀 **표 전체가 지원자격이 된다** —
    `rec_idx=53930400` 은 그렇게 3,180자가 들어갔다. 실측 18칸이 이 꼴이었다.

    **진짜 절 머리말은 사이에 내용이 있다.** 머리말이 바로 옆 줄에도 있으면 그 둘은
    절의 시작이 아니라 한 표의 열 이름이다.
    """
    marked = set()
    for index, line in enumerate(lines):
        if not is_bare_heading(line, headings):
            continue
        for neighbour in (index - 1, index + 1):
            if 0 <= neighbour < len(lines) and is_bare_heading(lines[neighbour], headings):
                marked.add(index)
                break
    return marked


# 이름 말고 **뜻을 가진 글자**가 남았는가. 글머리표·이모지·구두점은 장식이다.
_MEANINGFUL = re.compile(r"[0-9A-Za-z가-힣]")


def is_bare_heading(line: str, headings=None) -> bool:
    """절 이름**만** 있는 줄인가. 표의 열 이름은 늘 이 모양이다.

        담당업무          ← 이름만 — 열 이름일 수 있다
        📋 자격요건        ← 이모지는 장식이다. 역시 이름만
        ㆍ필수요건 : React ← 내용이 이어진다. **하위 라벨이지 열 이름이 아니다**
        근무환경 을 알려드릴게요!  ← 문장이다

    쌓인 머리말을 셀 때 이 조건을 안 걸면, 하위 라벨이 다음 줄의 **진짜 머리말을
    열 이름으로 만들어 버린다.** 실측(`jobkorea/49907988`): `ㆍ필수요건 : …` 바로
    다음 줄의 `우대사항` 이 그렇게 묻혀 **우대사항 칸이 통째로 비었다.**
    """
    patterns = headings or _headings(None)
    rest, matched = line, False
    for pattern in patterns:
        found = pattern.search(rest)
        if found:
            matched = True
            rest = rest[:found.start()] + rest[found.end():]
    return matched and not _MEANINGFUL.search(rest)


def section(text: str, heading: re.Pattern[str], headings=None) -> str:
    """머리말이 있는 줄 다음부터, **다음 머리말이 나오기 전까지**.

    ## 절을 **끝내지 않는** 줄이 셋 있다

    | 줄 | 왜 안 끝내나 |
    |---|---|
    | 절 이름이 둘 이상 (`is_column_header`) | 표의 열 머리글이다 |
    | 자기 절 이름 + 같은 줄에 내용 | 하위 라벨이다 (`자격요건` 안의 `필수요건 : …`) |
    | 머리말이 아닌 줄 | 내용이다 |

    **쌓인 머리말(`stacked_headers`)은 여기서 안 쓴다 — 절의 *시작*에만 쓴다.**
    그 규칙은 표의 열 이름에서 절이 잘못 *시작되는* 것을 막으려고 만든 것인데,
    끝내기에도 쓰니 **진짜 머리말 둘이 나란히 오면 절이 영영 안 끝났다.**

        ㆍAI/LLM 통합 경험          ← 우대사항 내용
        근무환경 을 알려드릴게요!     ← 진짜 머리말
        근무조건                     ← 진짜 머리말 (바로 다음 줄!)
        ㆍ고용형태 : 정규직          ← 여기부터 우대사항 칸에 섞여 들어왔다

    `전형절차`+`접수기간`, `근무조건`+`근무조건 상세내용`, `모집 부문`+`모집 부문 정보`
    처럼 흔한 모양이다. 실측(2026-09-12, 사람인·잡코리아 본문 434건 전량): 오염된 칸이
    **20 → 8** 로 줄고, 내용을 잃은 칸은 **0**이었다. 표를 만나면 절이 *끝나는* 것은
    오히려 맞다 — 표는 다른 절이다.
    """
    lines = text.split("\n")
    stacked = stacked_headers(lines, headings)
    start = next((index for index, line in enumerate(lines)
                  if heading.search(line) and index not in stacked
                  and not is_column_header(line, headings)), None)
    if start is None:
        return ""
    collected = []
    # 머리말 뒤에 붙은 구두점만 벗긴다. **글머리 기호(`ㆍ`)는 벗기지 않는다** —
    # 첫 줄에서만 떼면 `ㆍ 통계...` 처럼 기호가 남은 뒷줄들과 어긋나 목록이 깨진다.
    tail = _tail_of(lines[start], heading)
    if tail.strip():
        collected.append(tail.strip())
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if heading_kinds(line, headings) and not _keeps_going(line, heading, headings):
            break
        if is_column_header(line, headings):
            # **열 머리글은 내용이 아니다.** 절을 끝내지도 않지만 담지도 않는다 —
            # `부문 직무 담당업무 자격 및 우대요건 경력요건 근무지` 같은 줄이 그대로
            # 지원자격 칸에 들어가면, 다음 단계가 그것을 요건으로 읽는다.
            # 실측(2026-09-12, 434건): 이 한 줄로 오염된 칸이 11 → 6 이 됐다.
            continue
        if line.strip():
            collected.append(line.strip())
    return "\n".join(collected).strip()


def _keeps_going(line: str, heading: re.Pattern[str], headings=None) -> bool:
    """머리말이 있는 줄인데도 **절이 계속되는가.**

    두 경우다.

    **표의 열 머리글**(`is_column_header`) — 절 이름을 여럿 나열한 줄이다.

    **자기 절 이름인데 같은 줄에 내용이 이어질 때** — 하위 라벨이다.

        자격요건                                        ← 절 시작
        ㆍ학력 : 학력무관
        ㆍ필수요건 : React.JS 또는 Vue.JS에 대한 이해     ← 하위 라벨. 끝이 아니다
        우대사항                                        ← 여기가 끝

    이름만 있고 내용이 없으면 새 절(또는 표의 열 이름)로 본다. **꼬리를 조건에 두지
    않으면** 같은 이름이 여러 번 나오는 문서에서 절이 표까지 삼킨다 — 실측으로
    `275자 → 4,002자` 가 됐다 (`rec_idx=54830693`).
    """
    if is_column_header(line, headings):
        return True
    return bool(heading.search(line) and _tail_of(line, heading).strip())


def _tail_of(line: str, heading: re.Pattern[str]) -> str:
    """머리말 줄에서 **내용으로 볼 나머지.** 유도문형이면 없다.

    위 `SENTENCE_HEADING` 주석을 보라 — 유도문은 문장이라 어디서 끝나는지 못 집는다.
    나머지를 살리면 `이런 분을 찾습니다` 에서 `습니다` 가 내용이 된다.
    """
    if SENTENCE_HEADING.search(line):
        return ""
    return heading.split(line, maxsplit=1)[-1].lstrip(" :·-|]）)")


def until_first_heading(text: str, heading: re.Pattern[str], headings=None) -> str:
    """머리말이 처음 나오는 줄 앞까지."""
    kept = []
    for line in text.split("\n"):
        if heading.search(line) and not is_column_header(line, headings):
            break
        if line.strip():
            kept.append(line.strip())
    return "\n".join(kept).strip()


