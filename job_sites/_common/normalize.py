"""채용 사이트 공통 기술 이름 정규화.

사이트마다 자기 어휘로 기술 이름을 뱉는다. Wanted 는 `Apache Kafka`, 다른 곳은 `Kafka`
라고 적을 수 있다. 그대로 두면 합쳤을 때 같은 기술이 둘로 갈린다. 그래서 사이트가
뽑은 이름을 여기서 한 표준 이름으로 모은다.

    from job_sites._common.normalize import canonical, kind_of

    canonical("Apache Kafka")   # -> "Kafka"
    canonical("Quarkus")        # -> "Quarkus"   (사전에 없으면 그대로 둔다)
    kind_of("Kafka")            # -> "tool"

**편집거리 매칭을 쓰지 않는다.** Reference Project Repo인 DevSkill 의 `canonicalize()`(rapidfuzz, threshold 70~85)를
채용공고에서 뽑은 174종에 걸어 봤더니 이렇게 붙었다.

    REST         -> Rust          (75)
    Apache Kafka -> Apache Spark  (75)    Kafka 가 사전에 있는데도 Spark 로 갔다
    ML           -> XML           (80)
    MSSQL        -> MySQL         (80)

거기서는 LLM 이 "이건 기술 이름"이라고 판단해 제안한 소수의 이름을 스냅하는 용도라
문제가 없다. 우리는 후보가 많고 기술 약어는 짧고 서로 닮아서 문자열 거리를 믿을 수 없다.
사전에 없는 이름은 억지로 붙이지 않고 그대로 둔다.
"""
from __future__ import annotations

from . import dictionaries


def canonical(name: str | None) -> str:
    """기술 이름 하나를 표준 표기로. 사전에 없으면 다듬기만 하고 그대로 돌려준다.

    문자열이 아닌 값이 오면 조용히 넘기지 않고 `TypeError` 를 낸다 — 데이터 문제가
    아니라 부르는 쪽의 실수이고, 빈 문자열로 삼켜 버리면 기술 하나가 소리 없이 사라진다.
    """
    if name is None:
        return ""
    if not isinstance(name, str):
        raise TypeError(f"기술 이름은 문자열이어야 합니다: {type(name).__name__}")
    name = name.strip()
    if not name:
        return ""
    standard = dictionaries.aliases().get(name.lower())
    if standard:
        name = standard
    entry = dictionaries.corpus().get(name.lower())
    return entry["name"] if entry else name


def kind_of(name: str) -> str | None:
    """표준 이름의 분류(language/framework/library/tool/platform/database/concept/protocol).

    사전에 없으면 `None`. CSV 에는 넣지 않고, 나중에 분석할 때 조인해 쓴다.
    """
    entry = dictionaries.corpus().get(canonical(name).lower())
    return entry["kind"] if entry else None
