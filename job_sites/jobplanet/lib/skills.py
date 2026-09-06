"""잡플래닛 공고에서 기술스택을 뽑는다.

Wanted·사람인과 같은 구조다 — **구조화 ① 과 본문 매칭 ② 를 합친다.**

## ① 구조화 `skills` 배열

자체 공고는 이걸 100% 갖고 있다. 잡플래닛의 큰 장점이다.

    "skills": ["java", "kotlin", "MYSQL", "JIRA", "spring boot", "mybatis",
               "backend", "slack", "confluence"]

**그대로 쓰면 안 된다.** 표기가 흔들리고(`MYSQL`·`java`), 기술이 아닌 것이 섞인다
(`backend`, `slack`, `confluence`, `백엔드 개발`). 코퍼스로 표준 이름을 찾아 거른다 —
가르는 기준은 개념이냐가 아니라 **변별력이 있느냐**다 (D-14).

못 푼 이름은 `corpus_candidates` 로 쌓아 사람이 보게 한다. 코퍼스는 사람이 승인해야 는다.

## ② 본문 매칭

`required_qualification` · `preferred_skill` · `primary_responsibility` 를 이어 붙여 훑는다.
**여기는 그림 본문이 없다** — 잡플래닛 자체 공고는 본문이 전부 글로 온다.
사람인 18%, 잡코리아 24%가 그림이었던 것과 다르다.
"""
from __future__ import annotations

from functools import lru_cache

from _common import corpus_candidates, dictionaries
from _common.skills import build_matcher

SITE_NAME = "jobplanet"

# 산문에서 훑을 칸들. 순서가 곧 기술 이름이 나오는 순서다.
PROSE_FIELDS = ("required_qualification", "preferred_skill", "primary_responsibility")


@lru_cache(maxsize=1)
def _matcher():
    """어휘는 **공통 코퍼스**다. 잡플래닛에는 따로 쓸 만한 사이트 어휘가 없다 —
    `skills` 배열은 공고마다 자유롭게 적은 것이라 코드표가 아니다."""
    return build_matcher(site_terms=dictionaries.corpus_names())


def clear_caches() -> None:
    """사전을 다시 읽게 한다. 테스트가 파일을 갈아 끼울 때 쓴다."""
    _matcher.cache_clear()


def structured_skills(detail: dict, *, source_url: str = "",
                      candidates_file=None) -> list[str]:
    """① `skills` 배열 중 **표준 이름으로 풀리는 것만.**

    못 푼 이름은 버리되 후보로 쌓는다 — 사람이 보고 코퍼스에 넣으면 다음 실행부터 잡힌다.
    """
    raw = [str(name).strip() for name in (detail.get("skills") or []) if str(name).strip()]
    if not raw:
        return []
    corpus_candidates.record(raw, site=SITE_NAME, source_url=source_url,
                             path=candidates_file)
    return corpus_candidates.resolved(raw)


def prose_text(detail: dict) -> str:
    """② 로 훑을 글. 본문 칸들을 이어 붙인다."""
    return "\n".join(str(detail.get(field) or "") for field in PROSE_FIELDS).strip()


def find_skills_in_text(text: str) -> list[str]:
    """② 산문에서 기술 이름 찾기. 엔진은 `_common` 것을 그대로 쓴다."""
    return _matcher().find(text or "")


def extract_skills(detail: dict, *, source_url: str = "",
                   candidates_file=None) -> list[str]:
    """①∪② 기술스택. 둘 다 비면 빈 목록 — 채워 넣지 않는다.

    순수하다 — 같은 입력에 늘 같은 값을 낸다 (후보 파일에 쌓는 것만 바깥에 남는다).
    """
    found = structured_skills(detail, source_url=source_url,
                              candidates_file=candidates_file)
    found += find_skills_in_text(prose_text(detail))
    seen: dict[str, None] = {}
    for name in found:
        if name:
            seen.setdefault(name, None)
    return list(seen)
