"""읽어 낸 것을 행에 채운다. **덮지 않고 보강한다.**

그림 공고인데 자격요건이 이미 차 있는 경우가 있다(실측 29건 중 6건). 사람인 모집조건
표에서 온 학력·경력 조건이라 성격이 다르다. 덮어쓰면 그것을 잃고, 통째로 이으면 같은
말이 두 번 들어가 다음 단계가 지저분해진다. 그래서 **없는 것만 더한다.**

**편집거리는 안 쓴다**(D-04). `REST`/`Rust` 를 같은 것으로 볼 위험이 여기서도 같다.
정규화한 뒤 완전히 같거나 기존 글에 통째로 든 것만 건너뛴다. 애매하면 더하는 쪽으로
기운다 — 중복은 거슬리는 정도지만 빠뜨린 자격요건은 그 공고를 잘못 판단하게 만든다.
"""
from __future__ import annotations

import re

from .reader import FIELDS

# 그림에서 읽은 셋을 CSV 의 어느 칸에 넣는가
COLUMN = {"기술스택": "기술스택", "자격요건": "지원자격", "우대사항": "우대사항"}
BULLET = "•-·※*▪◦o"
_DROP = re.compile(r"[\s\W_]+", re.UNICODE)


def normalize(text: str) -> str:
    """견주기 위한 모양. 글머리표·공백·문장부호를 지우고 소문자로."""
    return _DROP.sub("", str(text).lstrip(BULLET).lower())


def has_anything(read: dict) -> bool:
    """셋 중 **하나라도** 얻었는가. 하나도 없으면 그 공고는 버린다."""
    return any(any(str(item).strip() for item in (read.get(name) or []))
               for name in FIELDS)


def _clean(items: list[str]) -> list[str]:
    out = []
    for item in items or []:
        text = " ".join(str(item).split())
        if text and text not in out:
            out.append(text)
    return out


def add_missing(existing: str, items: list[str]) -> str:
    """기존 글에 **없는 것만** 뒤에 더한다."""
    items = _clean(items)
    if not items:
        return existing
    base = (existing or "").strip()
    if not base:
        return "\n".join("• %s" % one for one in items)
    seen = {normalize(line) for line in base.split("\n") if line.strip()}
    whole = normalize(base)
    added = [one for one in items
             if normalize(one) not in seen and normalize(one) not in whole]
    if not added:
        return base
    return base + "\n" + "\n".join("• %s" % one for one in added)


def apply(row: dict, read: dict) -> dict:
    """새 dict 를 돌려준다. `row` 는 고치지 않는다."""
    out = dict(row)
    # 기술스택 칸에는 그림 주소만 들어 있다(실측: 주소와 기술이 섞인 행 0건).
    # 못 얻었으면 빈 칸이 된다 — 주소는 기술이 아니라서 남겨 두면 안 된다.
    out["기술스택"] = ", ".join(_clean(read.get("기술스택")))
    for name in ("자격요건", "우대사항"):
        column = COLUMN[name]
        out[column] = add_missing(out.get(column, ""), read.get(name))
    return out
