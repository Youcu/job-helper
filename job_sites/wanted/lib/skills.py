"""공고에서 기술 이름을 찾는다 — Wanted 쪽 어휘와 태그.

기술 이름은 상세 응답 한 벌 안의 **두 자리**에서 나온다.

  ① `job.skill_tags`              회사가 원티드 목록에서 골라 체크한 정형 필드
  ② `job.detail.requirements` 등  회사가 자유롭게 쓴 산문

둘은 서로를 포함하지 않는다 (실측 122건: ①에만 있는 기술 81개, ①이 비고 ②에만 있는 공고 87건).
그래서 합친다.

여기가 맡는 것은 **Wanted 고유한 부분**뿐이다.

  · `tags/wanted_skill.json` — 스킬 id ↔ 표기. Wanted 만의 사전이다
  · `normalize_tag()` — ①을 `tag_type_id` 로 푼다. Wanted 응답 구조를 안다

산문에서 찾는 규칙(단어경계·버전 숫자·짧은 이름·한글)과 표기 통일은 사이트 공통이라
`_common/skills.py` 와 `_common/normalize.py` 가 맡는다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from _common.normalize import canonical
from _common.skills import build_matcher

TAGS_DIR = Path(__file__).resolve().parent.parent / "tags"
SKILL_FILE = "wanted_skill.json"


@lru_cache(maxsize=1)
def _skill_corpus() -> dict[int, str]:
    """Wanted 스킬 id → 표기. 7,956개.

    산문에서 후보를 찾는 **넓은 그물**이자, ① 태그를 푸는 열쇠다.
    """
    data = json.loads((TAGS_DIR / SKILL_FILE).read_text(encoding="utf-8"))
    return {int(skill["id"]): skill["text"].strip() for skill in data["skill"]}


@lru_cache(maxsize=1)
def _matcher():
    return build_matcher(site_terms=list(_skill_corpus().values()))


def normalize_tag(tag: dict) -> str:
    """① 의 태그 하나를 표준 표기로.

    Wanted 가 준 문자열은 그대로 믿지 않는다 — 자기 corpus 표기와 다를 때가 있다
    (실측: `GitHub`/`Github`, `PyTorch`/`Pytorch`). `tag_type_id` 로 corpus 표기를
    먼저 얻고, 그 다음 공통 계층이 사이트 간 표준으로 모은다.
    """
    text = _skill_corpus().get(tag.get("tag_type_id")) or (tag.get("text") or "").strip()
    return canonical(text)


def find_skills_in_text(text: str) -> list[str]:
    """② 산문에서 기술 이름을 찾아 표준 표기로 돌려준다."""
    return _matcher().find(text)


def clear_caches() -> None:
    """어휘를 다시 읽는다. 테스트가 사전을 바꿔 끼울 때 쓴다."""
    _skill_corpus.cache_clear()
    _matcher.cache_clear()
