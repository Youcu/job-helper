"""**한 공고에 여러 직군이 섞여 있는가** 를 글자만 보고 가른다. 그물도 모델도 안 탄다.

    role_words.looks_mixed(row, body)  →  걸린 낱말들 (없으면 빈 목록)

여기서 하는 일은 **후보 고르기**뿐이다. 어느 부문이 내 직군인지, 그 부문이 무엇을
요구하는지는 글자로 못 가른다 — 회사마다 공고를 다르게 쓴다. 그건 `role.py` 가
모델에게 묻는다.

## 왜 기계가 먼저 거르나

모델은 느리고 돈이 든다. 실측(2026-09-18, 672행)으로 제목 신호에 걸리는 것은
**8%** 뿐이다. 나머지 92%는 물어볼 것도 없이 단일 직군이다.

## 제목이 본문보다 실하다

처음에는 본문의 `모집부문` 횟수를 세려 했다. **안 된다** — 사람인 28건을 실제로
받아 세어 보니 통합 공고인 한양이엔지도 1회였고, 단일 공고도 1회였다. 표의 열
이름이라 거의 모든 공고에 한 번 나온다.

제목은 다르다. 회사가 통합 공고를 낼 때 **제목에 그렇게 적는다** —
`각 부문별 직원모집` · `2026년 3분기 분야별 공개채용` · `하반기 각 부문 수시채용`.
`merged_rated.csv` 166행에서 18건이 걸렸고 **전부 진짜 통합 공고**였다.

## 그래도 본문을 함께 본다

제목만 보면 `[안랩] 2026 연구소 집중 채용` 처럼 **부문 낱말이 없는** 통합 공고를
놓친다. 본문에 `모집부문` 이 **여러 번** 나오면 그것도 후보로 올린다 — 한 번은
표 머리말이지만 여러 번은 부문이 여럿이라는 뜻이다.

## 넓게 걸어도 된다

헛걸린 공고의 대가는 **모델에게 한 번 더 묻는 것**뿐이고, 모델은 "직군 하나뿐이다"
라고 답한다. 놓친 공고의 대가는 다른 직군의 기술과 자격요건이 최종본까지 가는
것이다. 둘은 값이 다르므로 **넓게** 건다.
"""
from __future__ import annotations

import re

# 제목에 이것이 있으면 후보다. 회사가 "여러 자리를 한 공고에 담았다" 고 밝히는 말이다.
TITLE_SIGNALS = (
    r"각\s*부문", r"부문\s*별", r"분야\s*별", r"직군\s*별", r"각\s*분야",
    r"모집\s*분야", r"공개\s*채용", r"집중\s*채용", r"수시\s*채용",
    r"통합\s*채용", r"채용\s*통합", r"전\s*부문", r"부문\s*채용",
)
TITLE = re.compile("|".join(TITLE_SIGNALS))

# 본문 신호는 **흔한 말과 드문 말을 갈라서** 센다.
#
# 실측(2026-09-18, 본문 682건)으로 낱말마다 흔한 정도가 크게 다르다.
#
#     모집분야  267건(39%)   모집부문  145건(21%)   ← 표 머리말이라 아무 데나 있다
#     채용분야   12건         채용부문    8건
#     모집직무    7건         부문 안내   2건        ← 이 말을 쓰면 대개 진짜 통합 공고다
#
# 흔한 말에 1회 기준을 걸면 절반이 후보가 되어 모델 값이 못 쓰게 오른다. 드문 말에
# 2회 기준을 걸면 **아무것도 안 걸린다** — 위 표의 오른쪽은 2회 이상이 0건이다.
# 실제로 `[안랩] 2026년 연구소 상시채용`(기술 45개짜리 통합 공고)이 `채용부문` 을
# 한 번 쓰고 그대로 빠져나갔다.
COMMON_SIGNAL = re.compile(r"모집\s*부문|모집\s*분야")
COMMON_MINIMUM = 2

RARE_SIGNAL = re.compile(r"채용\s*부문|채용\s*분야|모집\s*직무|부문\s*안내|직군\s*안내")
RARE_MINIMUM = 1

TITLE_COLUMN = "공고명"


def title_hits(title: str) -> list[str]:
    """제목에서 걸린 낱말들. 같은 말이 여러 번이면 한 번만 센다."""
    found: list[str] = []
    for one in TITLE.findall(title or ""):
        word = " ".join(one.split())
        if word and word not in found:
            found.append(word)
    return found


def body_hits(body: str) -> list[str]:
    """본문에서 걸린 근거들. 빈 목록이면 안 걸렸다.

    **흔한 말과 드문 말의 기준이 다르다** — 위 두 상수의 설명을 보라.
    """
    body = body or ""
    found: list[str] = []
    common = len(COMMON_SIGNAL.findall(body))
    if common >= COMMON_MINIMUM:
        found.append("본문에 부문 낱말 %d회" % common)
    rare = RARE_SIGNAL.findall(body)
    if len(rare) >= RARE_MINIMUM:
        found.append("본문에 %s" % " ".join(dict.fromkeys(
            " ".join(one.split()) for one in rare)))
    return found


def looks_mixed(row: dict, body: str = "") -> list[str]:
    """이 공고가 여러 직군을 담았을 후보인가. **걸린 근거**를 돌려준다.

    빈 목록이면 후보가 아니다. 근거를 돌려주는 이유는 리포트에 적기 위해서다 —
    왜 물어봤는지 못 되짚으면 규칙을 고칠 수가 없다.
    """
    return (["제목: %s" % word for word in title_hits(row.get(TITLE_COLUMN, ""))]
            + body_hits(body))
