"""사전 파일을 읽는다. 형식을 아는 곳은 여기 하나뿐이다.

사전은 사이트가 공유한다. 파일 형식을 사이트마다 알고 있으면, 사이트를 하나 붙일 때마다
같은 파싱이 복제되고 형식을 바꿀 때 손댈 곳이 늘어난다.

  tech_corpus.json        표준 이름 + 분류(kind) + devtypes
  tech_aliases.json       별칭 → 표준 이름
  tech_blocklist.txt      산문 매칭에서 걸러 낼 말
  tech_ko_allowlist.txt   산문에서 찾을 한글 기술어 (`표기` 또는 `표기 = 표준표기`)

없는 파일은 빈 사전으로 돌려준다 — 부분 체크아웃이나 손편집으로 파일이 사라져도
수집 자체는 계속 돌아야 한다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DICT_DIR = Path(__file__).resolve().parent

CORPUS_FILE = "tech_corpus.json"
ALIASES_FILE = "tech_aliases.json"
BLOCKLIST_FILE = "tech_blocklist.txt"
KO_ALLOWLIST_FILE = "tech_ko_allowlist.txt"


def _read_json(name: str) -> dict | None:
    path = DICT_DIR / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_lines(name: str) -> list[str]:
    """주석(`#` 뒤)과 빈 줄을 걷어낸 줄 목록."""
    path = DICT_DIR / name
    if not path.exists():
        return []
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


@lru_cache(maxsize=1)
def corpus() -> dict[str, dict]:
    """소문자 표준 이름 → 항목({name, kind, devtypes, source})."""
    data = _read_json(CORPUS_FILE)
    if not data:
        return {}
    return {entry["name"].lower(): entry for entry in data["tech"]}


@lru_cache(maxsize=1)
def aliases() -> dict[str, str]:
    """소문자 별칭 → 표준 이름."""
    data = _read_json(ALIASES_FILE)
    if not data:
        return {}
    return {alias.lower(): standard for alias, standard in data["aliases"].items()}


@lru_cache(maxsize=1)
def alias_spellings() -> list[str]:
    """별칭의 원래 표기. 산문에서 이 말을 찾아야 표준으로 바꿀 수 있다."""
    data = _read_json(ALIASES_FILE)
    return list(data["aliases"]) if data else []


@lru_cache(maxsize=1)
def corpus_names() -> list[str]:
    """표준 이름 목록. 사이트 어휘에 없는 이름을 산문에서 줍는 데 쓴다."""
    data = _read_json(CORPUS_FILE)
    return [entry["name"] for entry in data["tech"]] if data else []


@lru_cache(maxsize=1)
def blocklist() -> frozenset[str]:
    """소문자로 모은, 기술이 아닌 말."""
    return frozenset(line.lower() for line in _read_lines(BLOCKLIST_FILE))


@lru_cache(maxsize=1)
def korean_terms() -> dict[str, str]:
    """산문에서 찾을 한글 기술어 → 표준 표기.

    `표기` 또는 `표기 = 표준표기` 두 형식을 받는다. 왼쪽이 비면 버린다.
    """
    terms: dict[str, str] = {}
    for line in _read_lines(KO_ALLOWLIST_FILE):
        if "=" in line:
            found, standard = (part.strip() for part in line.split("=", 1))
        else:
            found = standard = line
        if found:
            terms[found] = standard
    return terms


def clear_caches() -> None:
    """사전을 다시 읽는다. 테스트가 파일을 바꿔 끼울 때 쓴다."""
    for cached in (corpus, aliases, alias_spellings, corpus_names,
                   blocklist, korean_terms):
        cached.cache_clear()
