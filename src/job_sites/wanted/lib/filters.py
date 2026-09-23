"""수집 조건을 API 코드로 옮긴다 — 직군·직무·근무지.

`.env` 에는 사람이 읽는 말이 적힌다(`서울`, `강남구`). API 는 코드를 받는다
(`seoul.all`, `seoul.gangnam-gu`). 그 사이를 잇는 곳이다.

코드표는 `tags/` 의 Wanted 원본을 그대로 쓴다.

    wanted_amp.json       직군 코드 → 이름
    wanted_category.json  직군별 직무 목록
    wanted_location.json  시도·구 코드 (사이트 필터 화면에서 뜬 것)
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

TAGS_DIR = Path(__file__).resolve().parent.parent / "tags"


class LocationError(Exception):
    """`.env` 에 적힌 근무지를 코드표에서 찾지 못했다."""


def _load_tag_file(name: str) -> dict:
    return json.loads((TAGS_DIR / name).read_text(encoding="utf-8"))


# --- 직군 · 직무 ---------------------------------------------------------


@lru_cache(maxsize=1)
def job_groups() -> dict[int, str]:
    """직군 코드 → 이름."""
    return {int(code): name for code, name in _load_tag_file("wanted_amp.json")["amp"].items()}


@lru_cache(maxsize=1)
def job_titles() -> dict[int, str]:
    """직무 코드 → 이름. 같은 직무가 여러 직군에 걸리면 먼저 나온 이름을 쓴다."""
    titles: dict[int, str] = {}
    for group in _load_tag_file("wanted_category.json")["category"]:
        for tag in group.get("tags", []):
            titles.setdefault(int(tag["id"]), tag["title"])
    return titles


# --- 근무지 -------------------------------------------------------------


@lru_cache(maxsize=1)
def _location_index() -> tuple[dict[str, list[str]], frozenset[str]]:
    """(한글 이름 → slug 목록, 유효한 slug 전체).

    한 이름이 여러 slug 를 가질 수 있다 — '중구' 는 여섯 시도에 있다.
    """
    by_name: dict[str, list[str]] = {}
    slugs: set[str] = set()

    def add(name: str, slug: str) -> None:
        if slug not in by_name.setdefault(name, []):
            by_name[name].append(slug)
        slugs.add(slug)

    for province in _load_tag_file("wanted_location.json")["locations"]:
        if province["key"] == "all":
            add(province["display"], "all")          # 전국
            continue
        add(province["display"], f"{province['key']}.all")
        for district in province["districts"]:
            if district["display"] == "전체":         # '서울 전체' 는 위에서 이미 넣었다
                slugs.add(district["key"])
                continue
            add(district["display"], district["key"])
            # "서울 강남구" 처럼 시도까지 붙여 쓴 입력도 받는다.
            add(f"{province['display']} {district['display']}", district["key"])
    return by_name, frozenset(slugs)


def resolve_locations(inputs: list[str]) -> tuple[list[str], list[str]]:
    """한글 지역명·slug 목록 → (API 에 보낼 slug 목록, 사람이 읽을 경고 목록).

    비어 있으면 전국(`all`). 모르는 이름은 조용히 버리지 않고 `LocationError` 를 낸다 —
    버리면 사용자는 조건이 걸린 줄 안다.
    """
    if not inputs:
        return ["all"], []

    by_name, valid_slugs = _location_index()
    slugs: list[str] = []
    warnings: list[str] = []

    for raw in inputs:
        name = raw.strip()
        if not name:
            continue
        if name in valid_slugs:
            matched = [name]
        elif name in by_name:
            matched = by_name[name]
            if len(matched) > 1:
                # 하나만 고르면 조용히 틀린다. 전부 넣고 알린다.
                warnings.append(f"'{name}' 은 여러 시도에 있습니다 → {', '.join(matched)} 전부 포함")
        else:
            raise LocationError(
                f"모르는 근무지입니다: {name!r}. "
                "README.md 의 '지역 코드' 표에 있는 한글 이름이나 slug 를 써 주세요."
            )
        for slug in matched:
            if slug not in slugs:
                slugs.append(slug)

    return (slugs or ["all"]), warnings
