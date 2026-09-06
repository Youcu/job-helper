"""수집 조건 → MCP `search_jobs` 인자.

**서버가 거르는 것과 우리가 거르는 것이 갈린다.**

| 조건 | 어디서 | 왜 |
|---|---|---|
| 직무(역할) | 서버 `skills` | 이 사이트는 직무를 기술 칸에 넣는다 |
| 경력 | 서버 `experience_filter` | 서버가 정한 구간을 그대로 쓴다 |
| 고용형태 | **우리가** | 서버가 값 하나만 받아서, 둘 이상이면 나머지를 잃는다 |
| 근무지 | **우리가** | `search_jobs` 에 지역 파라미터가 없다 |
| 기술스택 | **아무도** | 지금은 거르지 않고 전량 받는다 |

## `skills` 는 AND 다

MCP 문서가 "입력한 기술을 모두 포함" 이라고 밝힌다. 화면의 기술 스택 칸에도 같은 설명이
붙어 있다. 그래서 역할을 여럿 적으면 **둘 다 가진 공고만** 나온다 —
`Backend,Frontend` 는 백엔드 겸 프론트엔드 공고다. 여럿을 OR 로 보려면 나눠 돌려야 한다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from _common.env import ConfigError

TAGS_DIR = Path(__file__).resolve().parent.parent / "tags"
ROLE_FILE = TAGS_DIR / "pathsdog_role.json"
FILTER_FILE = TAGS_DIR / "pathsdog_filter.json"

NATIONWIDE = "전국"


class LocationError(ValueError):
    """근무지 이름이 비어 있다. 이 사이트는 서버가 못 걸러서 우리가 거른다."""


@lru_cache(maxsize=1)
def known_roles() -> list[str]:
    data = json.loads(ROLE_FILE.read_text(encoding="utf-8"))
    return [item["name"] for item in data["roles"]]


@lru_cache(maxsize=1)
def _allowed(axis: str) -> tuple[str, ...]:
    data = json.loads(FILTER_FILE.read_text(encoding="utf-8"))
    return tuple(item["code"] for item in data[axis]["items"])


def role_values(job_ids: list[str]) -> list[str]:
    """역할 이름들. 코드표에 없어도 **막지 않는다.**

    이 사이트의 `skills` 는 닫힌 코드표가 아니라 자유로운 이름이다 — 관측해서 모은
    목록일 뿐이라, 없는 이름이라고 멈추면 멀쩡한 조건을 못 쓰게 된다. 대신 화면에
    "코드표에 없는 이름" 이라고 알려서 오타를 눈에 띄게 한다.
    """
    return list(dict.fromkeys(name.strip() for name in job_ids if name.strip()))


def unknown_roles(job_ids: list[str]) -> list[str]:
    """코드표에 없는 역할 이름. **오타일 수도, 새 이름일 수도 있다.**"""
    known = {name.lower() for name in known_roles()}
    return [name for name in role_values(job_ids) if name.lower() not in known]


def wanted_employments(config) -> list[str]:
    """우리가 거를 고용형태 이름.

    **서버에 안 보낸다.** `employment_type` 이 값 하나만 받아서, `정규직,인턴` 을 주면
    하나를 잃는다 — 실측으로 확인했다 (조건 없이 29건 · 정규직만 28건). 근무지와 같은
    이유로 받은 뒤 거른다: 조건을 버리는 게 아니라 거르는 자리를 옮기는 것이다.
    """
    return list(config.employment_names)


def build_arguments(config) -> dict:
    """`.env` 조건 → `search_jobs` 인자. 빈 값은 넣지 않는다."""
    arguments: dict = {}
    roles = role_values(config.job_ids)
    if roles:
        arguments["skills"] = roles
    experience = config.experience_filter
    if experience:
        if experience not in _allowed("experience_filter"):
            raise ConfigError("서버가 모르는 경력 값입니다: %r. 쓸 수 있는 값: %s"
                              % (experience, ", ".join(_allowed("experience_filter"))))
        arguments["experience_filter"] = experience
    return arguments


def wanted_locations(names: list[str]) -> list[str]:
    """우리가 거를 근무지 이름. `전국` 이면 안 거른다.

    서버에 못 보내므로 **코드로 옮기지 않는다** — 받은 뒤 근무지 글과 견줄 이름 그대로다.
    """
    kept = []
    for raw in names:
        name = " ".join(raw.split())
        if name == NATIONWIDE:
            return []
        if name:
            kept.append(name)
    return list(dict.fromkeys(kept))
