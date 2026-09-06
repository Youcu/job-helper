"""Pathsdog 공고에서 기술스택을 뽑는다.

Wanted·사람인과 같은 구조다 — **구조화 ① 과 본문 매칭 ② 를 합친다.**

## ① `기술스택` 칸

목록과 상세에 같은 값이 온다. `Backend, AI/ML, Python, React, Docker` 처럼 정리된
태그다. **`필수 기술`·`우대 기술` 칸이 아니다** — 그쪽은 이름과 달리 지원자격 문장을
콤마로 자른 것이라 `Python 개발 유경험자`, `병역특례 대상자` 같은 말이 들어 있다.

**이 칸에는 직무가 섞여 있다.** `Backend`, `Frontend`, `iOS`, `Software Engineering`
같은 것들이다 — 이 사이트가 직무와 기술을 한 칸에 쓰기 때문이다. 공통 코퍼스로 풀리는
것만 남기면 그 대부분은 저절로 빠지고, 못 푼 것은 후보로 쌓여 사람이 본다 (D-14).

## ② 본문 매칭

원문(`[상세 내용]`)을 훑는다. 라벨 칸만으로는 원문에만 적힌 기술을 놓친다.
"""
from __future__ import annotations

from _common import corpus_candidates
from _common.skills import clear_corpus_matcher, find_in_corpus

SITE_NAME = "pathsdog"


def clear_caches() -> None:
    """사전을 다시 읽게 한다. 테스트가 파일을 갈아 끼울 때 쓴다."""
    clear_corpus_matcher()


def raw_stacks(listing: dict, detail: str) -> list[str]:
    """`기술스택` 칸의 이름들. 목록과 상세를 합친다 — 어긋나면 넓은 쪽을 쓴다."""
    from .record import field
    joined = [field(detail, "기술스택"), listing.get("기술", "")]
    names = []
    for text in joined:
        for piece in str(text or "").split(","):
            name = piece.strip()
            if name:
                names.append(name)
    return list(dict.fromkeys(names))


def find_skills_in_text(text: str) -> list[str]:
    """② 산문에서 기술 이름 찾기. 엔진은 `_common` 것을 그대로 쓴다."""
    return find_in_corpus(text)


def structured_skills(listing: dict, detail: str, *, source_url: str = "",
                      candidates_file=None) -> list[str]:
    """① `기술스택` 칸 중 **표준 이름으로 풀리는 것만.**

    못 푼 이름은 버리되 후보로 쌓는다. 이 사이트에서는 직무 이름(`Backend`)이 많이
    올라오는데, 그것도 사람이 보고 판단할 재료다.
    """
    raw = raw_stacks(listing, detail)
    if not raw:
        return []
    corpus_candidates.record(raw, site=SITE_NAME, source_url=source_url,
                             path=candidates_file)
    return corpus_candidates.resolved(raw)


def extract_skills(listing: dict, detail: str, *, source_url: str = "",
                   candidates_file=None) -> list[str]:
    """①∪② 기술스택. 둘 다 비면 빈 목록 — 채워 넣지 않는다."""
    from .record import full_description
    found = structured_skills(listing, detail, source_url=source_url,
                              candidates_file=candidates_file)
    found += find_skills_in_text(full_description(detail))
    seen: dict[str, None] = {}
    for name in found:
        if name:
            seen.setdefault(name, None)
    return list(seen)
