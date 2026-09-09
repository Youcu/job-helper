"""직무를 **사이트 중립 이름**으로 적게 한다.

사이트가 직무를 저마다 다른 코드로 받는다 — Wanted `872`, 사람인 `84`,
잡코리아 `1000229`, 잡플래닛 `11904`, 점핏 `1`. 사람이 원하는 것은
"백엔드 공고" 하나인데 사이트 수만큼 따로 적어야 했다.

    .env  JOB_ROLES=백엔드,웹          ← 한 번만 적는다
            ↓
    각 사이트가 자기 `tags/<site>_role_map.json` 으로 자기 코드를 찾는다

## `_common` 은 사이트를 모른다

여기에는 **표준 이름과 그 뜻**만 있다. 어느 이름이 어느 코드인지는 각 사이트의
`tags/` 에 있다 — `_common` 이 사이트 코드를 알면 그건 공통이 아니다
(`docs/convention/01-architecture.md` 의 import 방향).

## 한 이름이 여러 코드로 펼쳐진다

1:1 이 아니다. Wanted 에는 `자바 개발자`·`파이썬 개발자` 처럼 **언어별 직무**가 있는데
다른 사이트에는 없다. 같은 일을 하는 공고를 사이트가 어떻게 쪼개 뒀든 다 걷는 것이
목적이므로, `백엔드` 하나가 Wanted 에서는 코드 셋이 된다.

## 사이트에 없는 역할은 조용히 빠지지 않는다

`게임`은 잡플래닛에 대응하는 코드가 없다. 그럴 때 그 사이트는 그 역할을 못 걸지만,
**무엇을 못 걸었는지 실행 화면에 찍는다** — 조용히 빠지면 왜 결과가 적은지 못 찾는다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .env import ConfigError

ROLES_FILE = Path(__file__).resolve().parent / "roles.json"


class RoleError(ConfigError):
    """모르는 역할 이름. **조용히 빼면 조건이 통째로 사라진다.**

    `ConfigError` 를 물려받는다 — 이것도 `.env` 를 잘못 적은 것이라, 스크래퍼가
    설정 오류로 잡아 **종료 코드 1** 을 내야 한다. 안 그러면 스택 트레이스가 튀어나오고
    오케스트레이터도 "알 수 없는 실패" 로 읽는다.
    """


@lru_cache(maxsize=1)
def _book() -> dict:
    return json.loads(ROLES_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def known_roles() -> tuple[str, ...]:
    """표준 역할 이름들. `.env` 의 `JOB_ROLES` 에 적을 수 있는 값이다."""
    return tuple(item["name"] for item in _book()["roles"])


def describe(name: str) -> str:
    """그 역할이 무엇인지 한 줄. 화면에 찍어 사람이 고르게 한다."""
    for item in _book()["roles"]:
        if item["name"] == name:
            return item.get("설명", "")
    return ""


def normalize(names: list[str]) -> list[str]:
    """적어 준 역할 이름을 다듬는다. **모르는 이름이 있으면 멈춘다.**

    조용히 빼면 조건이 느슨해지거나(다른 역할만 걷힘) 통째로 사라진다. 둘 다 결과가
    이상한데 원인이 안 보인다.

    별칭도 받는다 — `서버`·`Backend` 라고 적어도 `백엔드` 로 알아듣는다.
    """
    aliases = _aliases()
    kept: list[str] = []
    unknown: list[str] = []
    for raw in names:
        name = " ".join(str(raw).split())
        if not name:
            continue
        standard = aliases.get(name.lower())
        if standard is None:
            unknown.append(raw)
        elif standard not in kept:
            kept.append(standard)
    if unknown:
        raise RoleError(
            "모르는 역할 이름입니다: %s\n"
            "  쓸 수 있는 이름: %s\n"
            "  job_sites/_common/roles.json 에 있습니다."
            % (", ".join(unknown), ", ".join(known_roles())))
    return kept


@lru_cache(maxsize=1)
def _aliases() -> dict[str, str]:
    """소문자 별칭 → 표준 이름. 사람이 적는 말이 흔들려도 알아듣게 한다."""
    book: dict[str, str] = {}
    for item in _book()["roles"]:
        name = item["name"]
        book[name.lower()] = name
        for alias in item.get("별칭", []):
            book[str(alias).lower()] = name
    return book


def site_codes(role_map: dict, names: list[str]) -> tuple[list[str], list[str]]:
    """표준 이름들 → 그 사이트의 코드들, 그리고 **대응이 없는 이름들**.

    `role_map` 은 사이트가 자기 `tags/<site>_role_map.json` 에서 읽어 넘긴다.
    한 이름이 코드 여럿으로 펼쳐질 수 있고, 코드가 하나도 없을 수도 있다 —
    그 사이트에 그런 직무 분류가 없는 것이다.
    """
    codes: list[str] = []
    missing: list[str] = []
    for name in names:
        found = [str(code) for code in (role_map.get(name) or [])]
        if not found:
            missing.append(name)
            continue
        for code in found:
            if code not in codes:
                codes.append(code)
    return codes, missing


def load_role_map(path: Path) -> dict:
    """사이트의 역할 대응표를 읽는다. `{표준 이름: [코드, …]}`."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {name: list(codes) for name, codes in (data.get("roles") or {}).items()}


def resolve(env: dict, role_map_path: Path) -> tuple[list[str], list[str]]:
    """`.env` 의 `JOB_ROLES` → 이 사이트의 코드들, 그리고 못 건 역할들.

    다섯 사이트가 똑같은 열 줄을 각자 쓰게 되어 여기로 모았다. 사이트가 하는 일은
    자기 대응표 경로를 넘기는 것뿐이다.

    **비어 있으면 멈춘다.** 직무 없이 돌면 그 사이트 전체를 긁는다.
    """
    names = normalize([piece.strip() for piece in
                       str(env.get("JOB_ROLES") or "").split(",") if piece.strip()])
    if not names:
        raise RoleError(
            "JOB_ROLES 가 비어 있습니다. 원하는 직무를 comma 로 적어 주세요.\n"
            "  **모든 사이트가 함께 씁니다** — 사이트마다 따로 적지 않습니다.\n"
            "  쓸 수 있는 이름: %s\n"
            "  예: JOB_ROLES=백엔드,웹" % ", ".join(known_roles()))
    return site_codes(load_role_map(role_map_path), names)
