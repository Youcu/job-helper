"""수집 조건 → 점핏 검색 파라미터.

**앞선 세 사이트와 반대로 도는 것이 둘 있다.** 이 사이트가 순한 편인데, 그 순함을
믿고 넘어가면 다른 사이트에서 배운 대비를 엉뚱하게 적용하게 된다.

| | 사람인 | 잡코리아 | 잡플래닛 | **점핏** |
|---|---|---|---|---|
| 같은 이름을 두 번 | 마지막 값 | 첫 값 | 마지막 값 | **둘 다 먹는다 (OR)** |
| 시 코드가 구를 포함 | 아니오 | 아니오(시 코드가 없음) | — | **예** |

실측 — `jobCategory=1` 139건 · `=2` 73건 · `1&2` **189건** · `1,2` **189건** (둘 다 OR).
`102180`(성남시) 단독 118건 = 성남 구 셋을 함께 보낸 118건.

그래서 여기서는 **펼치지 않는다.** 사람인에서 `성남시` 를 구로 펼쳐야 했던 것을 그대로
가져오면 같은 공고를 여러 번 세지는 않지만, 없는 문제를 푸느라 코드가 무거워진다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from _common.env import ConfigError

TAGS_DIR = Path(__file__).resolve().parent.parent / "tags"
LOCATION_FILE = TAGS_DIR / "jumpit_location.json"
CATEGORY_FILE = TAGS_DIR / "jumpit_job_category.json"

NATIONWIDE = "전국"


class LocationError(ValueError):
    """근무지 이름을 코드로 못 옮겼다. **조용히 빼면 전국을 긁는다.**"""


@lru_cache(maxsize=1)
def _location_index() -> dict[str, list[str]]:
    """이름 → 코드. 시도·시·구를 모두 받는다.

    **시 코드가 구를 포함하므로 펼치지 않는다.** `성남시` 는 코드 하나로 끝난다.
    여러 시도에 같은 이름이 있는 구(`중구` 등)는 혼자서는 못 정하므로 뺀다 —
    `대구 중구` 처럼 시도를 붙여야 한다.
    """
    data = json.loads(LOCATION_FILE.read_text(encoding="utf-8"))
    index: dict[str, list[str]] = {}
    ambiguous: set[str] = set()
    for province in data["provinces"]:
        index[province["name"]] = [province["code"]]
        for district in province["districts"]:
            name, code = district["name"], district["code"]
            index["%s %s" % (province["name"], name)] = [code]
            if name in index and index[name] != [code]:
                ambiguous.add(name)
            else:
                index.setdefault(name, [code])
    for name in ambiguous:
        index.pop(name, None)
    return index


def ambiguous_names() -> list[str]:
    """여러 시도에 같은 이름이 있어 혼자서는 못 정하는 이름."""
    data = json.loads(LOCATION_FILE.read_text(encoding="utf-8"))
    seen: dict[str, int] = {}
    for province in data["provinces"]:
        for district in province["districts"]:
            seen[district["name"]] = seen.get(district["name"], 0) + 1
    return sorted(name for name, count in seen.items() if count > 1)


def resolve_locations(names: list[str]) -> list[str]:
    """근무지 이름들 → `locationTag` 코드 목록. 안 적으면 빈 목록(전국).

    하나라도 못 옮기면 **멈춘다.** 조용히 빼면 조건이 느슨해져 전국을 긁는데,
    결과가 늘어나는 방향이라 사람이 알아채기 어렵다.
    """
    index = _location_index()
    codes: list[str] = []
    unknown: list[str] = []
    for raw in names:
        name = " ".join(raw.split())
        if name == NATIONWIDE:
            return []
        found = index.get(name)
        if not found:
            unknown.append(raw)
            continue
        for code in found:
            if code not in codes:
                codes.append(code)
    if unknown:
        raise LocationError(
            "근무지 이름을 점핏 코드로 옮기지 못했습니다: %s\n"
            "  쓸 수 있는 이름은 job_sites/jumpit/tags/jumpit_location.json 에 있습니다.\n"
            "  여러 시도에 같은 이름이 있는 구(%s)는 `대구 중구` 처럼 시도를 붙여 주세요."
            % (", ".join(unknown), ", ".join(ambiguous_names()[:5])))
    return codes


@lru_cache(maxsize=1)
def _category_names() -> dict[str, str]:
    data = json.loads(CATEGORY_FILE.read_text(encoding="utf-8"))
    return {str(item["code"]): item["name"] for item in data["categories"]}


def category_codes(job_ids: list[int]) -> list[str]:
    """직무 코드들. 코드표에 없으면 멈춘다.

    점핏은 계층이 없다 — 대분류·중분류가 갈리지 않아서, 잡코리아·잡플래닛에서 겪은
    "대분류를 보내면 중분류가 무시된다" 는 함정이 여기에는 없다.
    """
    known = _category_names()
    codes = [str(code) for code in job_ids]
    unknown = [c for c in codes if c not in known]
    if unknown:
        raise ConfigError(
            "코드표에 없는 직무 코드입니다: %s\n"
            "  쓸 수 있는 코드: %s\n"
            "  job_sites/jumpit/tags/jumpit_job_category.json 을 보세요."
            % (", ".join(unknown),
               ", ".join("%s(%s)" % (c, n) for c, n in list(known.items())[:4])))
    return list(dict.fromkeys(codes))


def build_params(config) -> dict:
    """`.env` 조건 → 점핏 질의 파라미터.

    값이 여럿인 것은 **목록으로 넘긴다** — 이 사이트는 같은 이름을 두 번 보내도
    둘 다 먹는다(실측). `client._query` 가 반복 파라미터로 펼친다.

    기술스택·고용형태·학력은 넣지 않는다 — 왜인지는 `config.py` 머리말에 있다.
    """
    params: dict = {"sort": "popular"}
    codes = category_codes(config.job_ids)
    if codes:
        params["jobCategory"] = codes
    locations = resolve_locations(config.home_locations)
    if locations:
        params["locationTag"] = locations
    if config.yoe >= 0:
        # `career=N` 은 **N년차가 지원할 수 있는 공고**다 — `minCareer <= N <= maxCareer`.
        # 표본 177건에서 이를 어기는 공고가 하나도 없었다. `career=0` 은 신입 공고와
        # 정확히 겹쳤다(57/57 이 `newcomer=true`).
        params["career"] = str(config.yoe)
    return params
