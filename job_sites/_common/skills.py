"""공고 산문에서 기술 이름을 찾는다. 사이트 공통 엔진.

사이트마다 다른 것은 **어휘**뿐이다. Wanted 는 자기 스킬 사전 7,956개를 갖고 있고,
다른 사이트는 또 다른 것을 갖고 있을 것이다. 찾는 규칙 — 단어경계, 버전 숫자, 짧은 이름,
한글 처리 — 은 어디서나 같다. 그래서 규칙은 여기 한 번만 두고 어휘를 받는다.

    matcher = build_matcher(site_terms=wanted_skill_names())
    matcher.find("Java Spring 기반, Docker/K8s")   # -> ['Java', 'Spring', 'Docker', 'Kubernetes']

찾은 이름은 `normalize.canonical()` 을 거쳐 표준 표기로 나온다. 사이트가 뭐라 적든
같은 기술이 한 이름으로 모인다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from . import dictionaries
from .normalize import canonical

# 첫 글자로 `.` 을 허용한다 — 안 그러면 `.NET` `.NET Core` 를 산문에서 영영 못 찾는다.
# 다만 글자가 하나도 없는 것(숫자·기호뿐)은 기술 이름이 아니므로 뺀다.
_ASCII_SKILL = re.compile(r"[A-Za-z0-9.][A-Za-z0-9 .+#/_-]*")
_HAS_LETTER = re.compile(r"[A-Za-z]")

# 1~2글자는 대개 오탐(IR, SD, PC)이라 막고, 진짜 기술만 예외로 통과시킨다.
SHORT_NAME_ALLOWLIST = frozenset({"c", "r", "go", "c#", "c++", "js", "ai", "ml"})

# 3글자 이상이면 뒤에 붙는 버전 숫자를 인정한다 (Python3 → Python).
# 짧은 이름에 적용하면 C9·Go2 가 C·Go 로 잡힌다.
_MIN_LENGTH_FOR_VERSION_SUFFIX = 3

# 한글은 단어경계가 없다. `가상화폐` 안에 `가상화` 가, `컨테이너선` 안에 `컨테이너` 가 들어 있다.
# 충돌하는 복합어를 목록으로 적는 방법은 **열린 집합**이라 끝이 없다 — 관측한 것만 막고
# 다음 것은 그대로 통과시킨다.
#
# 대신 **닫힌 부류**로 판정한다. 한국어에서 낱말 뒤에 붙는 조사·어미·접미사는 문법이
# 정해 놓은 유한한 집합이고, 새 기술이 나와도 늘어나지 않는다.
#
#   `컨테이너를`   → `를` 은 조사         → 낱말이 끝났다  → 통과
#   `분산 처리한`  → `한` 은 어미         → 낱말이 끝났다  → 통과
#   `컨테이너화`   → `화` 는 접미사       → 낱말이 끝났다  → 통과
#   `컨테이너선`   → `선` 은 셋 다 아님   → 다른 낱말이다  → 거부
#
# 이 규칙은 놓치는 쪽으로 틀린다(`딥러닝모델` 을 거부). 목록은 틀린 데이터를 넣는 쪽으로
# 틀린다. 둘 중에는 놓치는 편이 낫다.
_PARTICLES = (            # 조사 — 문법이 정한 닫힌 집합
    "을 를 이 가 은 는 에 의 와 과 로 으로 도 만 및 부터 까지 처럼 보다 대로 만큼 "
    "이나 나 든 라도 조차 마저 뿐 께 한테 에서 에게 랑 이며 며 이고 고"
).split()
_ENDINGS = (              # 어미 — 용언이 이어질 때
    "하 한 할 함 해 했 하는 하여 하고 하며 하지 "
    "되 된 될 됨 돼 됐 되는 되어 되고 되며 "
    "인 이 였 이었 라 란 랑"
).split()
_SUFFIXES = "화 적 성 형 기 자 등 들 시 상 중 용 별 내 외 간 어 측 부 군 값 수".split()
KOREAN_TRAILERS = tuple(sorted(set(_PARTICLES + _ENDINGS + _SUFFIXES), key=len, reverse=True))


def _korean_word_ends_here(text: str, end: int) -> bool:
    """`end` 에서 한글 낱말이 끝났다고 볼 수 있나."""
    rest = text[end:]
    if not rest or not ("가" <= rest[0] <= "힣"):
        return True          # 글 끝이거나 한글이 아니면 낱말이 끝난 것이다
    return rest.startswith(KOREAN_TRAILERS)


def _is_ascii_skill(text: str) -> bool:
    return bool(_ASCII_SKILL.fullmatch(text)) and bool(_HAS_LETTER.search(text))


@dataclass(frozen=True)
class SkillMatcher:
    """산문에서 기술 이름을 찾는다. `build_matcher()` 로 만든다."""

    ascii_pattern: re.Pattern
    ascii_names: dict[str, str]          # 소문자로 찾은 말 → 표준 표기
    korean_pattern: re.Pattern | None
    korean_names: dict[str, str]         # 한글로 찾은 말 → 표준 표기

    def find(self, text: str) -> list[str]:
        """찾은 기술을 표준 표기로, 등장 순서대로 중복 없이 돌려준다."""
        if not text:
            return []
        found: list[str] = []
        seen: set[str] = set()

        def add(name: str | None) -> None:
            if name and name.lower() not in seen:
                seen.add(name.lower())
                found.append(name)

        for match in self.ascii_pattern.finditer(text):
            hit = match.group(1).lower()
            add(self.ascii_names.get(hit) or self.ascii_names.get(hit.rstrip("0123456789")))

        # 한글은 단어경계가 없어 포함 여부로 찾되, 뒤에 무엇이 오는지로 낱말 끝을 판정한다.
        if self.korean_pattern:
            for match in self.korean_pattern.finditer(text):
                if _korean_word_ends_here(text, match.end()):
                    add(self.korean_names.get(match.group(1)))
        return found


def _searchable(names: list[str], blocked: frozenset[str]) -> dict[str, str]:
    """찾을 만한 이름만 걸러 (소문자 → 표준 표기) 로 만든다."""
    keep: dict[str, str] = {}
    for name in names:
        low = name.lower()
        if low in blocked or not _is_ascii_skill(name):
            continue
        if len(name) <= 2 and low not in SHORT_NAME_ALLOWLIST:
            continue
        keep[low] = canonical(name)
    return keep


def _alternation(terms: list[str], *, version_suffix: bool) -> str:
    """긴 것부터 맞춰야 'Spring Boot' 가 'Spring' 에 먹히지 않는다."""
    ordered = sorted(terms, key=lambda t: (-len(t), t))
    if not version_suffix:
        return "|".join(re.escape(t) for t in ordered)
    return "|".join(
        re.escape(t) + (r"[0-9]*" if len(t) >= _MIN_LENGTH_FOR_VERSION_SUFFIX else "")
        for t in ordered
    )


def build_matcher(site_terms: list[str] = ()) -> SkillMatcher:
    """사이트 어휘와 공통 사전을 합쳐 매처를 만든다.

    `site_terms` 는 그 사이트가 가진 스킬 이름 목록 — 산문에서 후보를 찾는 넓은 그물이다.
    공통 corpus 와 별칭도 함께 넣는다. 사이트 어휘에 없는 이름이 공통 corpus 에는 있다
    (`Kafka` `Spring` `Google Cloud` `NestJS`). 그걸 넣지 않으면 산문에 적혀 있어도 못 찾는다.

    **쓸 만한 사이트 어휘가 없으면 비워 둔다.** corpus 는 어차피 여기서 더하므로,
    `site_terms=corpus_names()` 로 넘기면 같은 목록을 두 번 넣는 셈이다 — 결과는 같지만
    코드가 "이 사이트의 어휘가 corpus 다" 라는 없는 사실을 말하게 된다.
    """
    blocked = dictionaries.blocklist()
    ascii_names = _searchable(
        list(site_terms) + dictionaries.corpus_names() + dictionaries.alias_spellings(),
        blocked,
    )
    ascii_pattern = re.compile(
        r"(?<![A-Za-z0-9])(" + _alternation(list(ascii_names), version_suffix=True) + r")(?![A-Za-z0-9])",
        re.IGNORECASE,
    )

    korean_names = {found: canonical(standard)
                    for found, standard in dictionaries.korean_terms().items()}
    korean_pattern = (
        re.compile("(" + _alternation(list(korean_names), version_suffix=False) + ")")
        if korean_names else None
    )

    return SkillMatcher(
        ascii_pattern=ascii_pattern,
        ascii_names=ascii_names,
        korean_pattern=korean_pattern,
        korean_names=korean_names,
    )


@lru_cache(maxsize=1)
def corpus_matcher() -> SkillMatcher:
    """**공통 corpus 만으로** 만든 매처.

    쓸 만한 사이트 어휘가 없는 사이트가 쓴다 — 잡코리아(전 직군 어휘라 못 씀)·
    잡플래닛·점핏(코드표를 공개하지 않음)이 그렇다. 셋이 똑같은 세 줄을 각자 쓰고
    있어서 여기로 모았다. 사이트 어휘가 있는 사람인은 `build_matcher` 를 직접 쓴다.

    매처를 만드는 데 사전 세 벌을 읽고 정규식을 컴파일하므로 캐시한다.
    """
    return build_matcher()


def clear_corpus_matcher() -> None:
    """사전을 다시 읽게 한다. 테스트가 사전을 갈아 끼울 때 쓴다."""
    corpus_matcher.cache_clear()


def find_in_corpus(text: str) -> list[str]:
    """산문에서 기술 이름 찾기 — corpus 어휘만으로."""
    return corpus_matcher().find(text or "")
