"""점핏 공고에서 기술스택을 뽑는다.

Wanted·사람인과 같은 구조다 — **구조화 ① 과 본문 매칭 ② 를 합친다.**

## ① 구조화 `techStacks`

**목록에도 상세에도 있다.** 모양이 다르다 — 목록은 문자열 배열, 상세는 객체 배열이다.

    목록  "techStacks": ["Git", "Next.js", "React", "TypeScript"]
    상세  "techStacks": [{"stack": "Git", "imagePath": "…/git.png"}, …]

30건 표본에서 100% 차 있었다. 네 사이트 중 가장 좋은 구조화 소스다.

**그래도 그대로 쓰지 않는다.** 표기가 사이트마다 흔들리고(`Next.js`·`NextJS`),
기술이 아닌 것이 섞일 수 있다. 공통 코퍼스로 풀리는 것만 남기고, 못 푼 이름은
`corpus_candidates` 로 쌓아 사람이 보게 한다 (D-14).

## ② 본문 매칭

`qualifications` · `preferredRequirements` · `responsibility` 를 이어 붙여 훑는다.
**사이트가 붙인 딱지와 본문이 어긋난다는 것이 이 사이트의 특징**이라 ② 가 특히 중요하다 —
`Spring Boot` 딱지가 없는 공고의 본문이 `Spring Framework` 를 요구한다.

**그림 본문이 없다.** 전부 글로 온다 (사람인 18% · 잡코리아 24%가 그림이었던 것과 다르다).
"""
from __future__ import annotations

from _common import corpus_candidates
from _common.skills import clear_corpus_matcher, find_in_corpus

SITE_NAME = "jumpit"

# 산문에서 훑을 칸들. 순서가 곧 기술 이름이 나오는 순서다.
PROSE_FIELDS = ("qualifications", "preferredRequirements", "responsibility")


def clear_caches() -> None:
    """사전을 다시 읽게 한다. 테스트가 파일을 갈아 끼울 때 쓴다."""
    clear_corpus_matcher()


def raw_stacks(source: dict) -> list[str]:
    """`techStacks` 를 이름 목록으로. **목록과 상세의 모양이 다르다.**

    목록은 `["Git", …]`, 상세는 `[{"stack": "Git", …}, …]` 로 온다. 하나만 가정하면
    한쪽에서 조용히 빈 목록이 나온다.
    """
    names = []
    for item in source.get("techStacks") or []:
        name = item.get("stack") if isinstance(item, dict) else item
        if name and str(name).strip():
            names.append(str(name).strip())
    return list(dict.fromkeys(names))


def structured_skills(position: dict, detail: dict, *, source_url: str = "",
                      candidates_file=None) -> list[str]:
    """① `techStacks` 중 **표준 이름으로 풀리는 것만.**

    목록과 상세를 합친다 — 둘이 어긋날 때 넓은 쪽을 쓴다. 못 푼 이름은 버리되 후보로
    쌓는다. 사람이 보고 코퍼스에 넣으면 다음 실행부터 잡힌다.
    """
    raw = list(dict.fromkeys(raw_stacks(detail) + raw_stacks(position)))
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
    return find_in_corpus(text)


def extract_skills(position: dict, detail: dict, *, source_url: str = "",
                   candidates_file=None) -> list[str]:
    """①∪② 기술스택. 둘 다 비면 빈 목록 — 채워 넣지 않는다."""
    found = structured_skills(position, detail, source_url=source_url,
                              candidates_file=candidates_file)
    found += find_skills_in_text(prose_text(detail))
    seen: dict[str, None] = {}
    for name in found:
        if name:
            seen.setdefault(name, None)
    return list(seen)
