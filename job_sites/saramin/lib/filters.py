"""수집 조건 → 사람인 검색 파라미터.

**코드표에 있다고 필터가 먹는 게 아니다.** 실측에서 세 가지가 조용히 어긋났다.

| 함정 | 무슨 일이 나는가 |
|---|---|
| 구 코드를 `loc_mcd` 에 넣기 | **0건**이 나온다. 구는 `loc_bcd` 다 |
| `exp_min` 을 단독으로 주기 | 에러 없이 200 에 **전체**를 돌려준다 |
| `exp_cd=99`(경력무관) | 그것도 **전체**다. 경력무관은 `exp_none=y` |

앞의 것은 결과가 비어서 티라도 나지만, 뒤의 둘은 **필터가 먹은 줄 알기 딱 좋다.**
그래서 이 모듈이 파라미터를 만들 때 그 조합을 지킨다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from _common.env import ConfigError

TAGS_DIR = Path(__file__).resolve().parent.parent / "tags"
LOCATION_FILE = TAGS_DIR / "saramin_location.json"

# 시도 전체는 loc_mcd, 구·시는 loc_bcd. 레벨이 다르면 파라미터도 다르다.
PROVINCE_PARAM = "loc_mcd"
DISTRICT_PARAM = "loc_bcd"

# `전국`(117000)은 "전체" 가 아니라 근무지가 "전국" 이라 적힌 공고 버킷이다.
# 전체를 받으려면 지역 파라미터를 아예 빼야 한다.
NATIONWIDE_BUCKET = "117000"

NEW_GRADUATE = "1"      # exp_cd
EXPERIENCED = "2"       # exp_cd

# 학력. `.env` 의 사람이 읽는 값 → (edu_min, edu_max).
# **min 과 max 가 같은 학력에 다른 번호를 쓴다.** 코드 9 가 min 에선 석사 이상,
# max 에선 고졸 이하다. 한 표를 돌려쓰면 조용히 엉뚱한 것을 긁는다.
EDUCATION_CODES = {
    "고졸":   ("6", "9"),
    "대졸2":  ("7", "10"),
    "대졸4":  ("8", "11"),
    "석사":   ("9", "12"),
    "박사":   ("5", "13"),
}
EDUCATION_ANY = "무관"      # edu_none=y


class LocationError(ValueError):
    """근무지 이름을 코드로 못 옮겼다. **조용히 빼면 전국을 긁는다.**"""


@lru_cache(maxsize=1)
def _sub_districts() -> dict[str, list[str]]:
    """`성남시` → 그 아래 구 코드들.

    **시 코드는 구를 포함하지 않는다.** `성남시`(102180)와 `성남시 분당구`(102190)가
    별개라, 시 코드만 보내면 구에 등록된 공고를 통째로 놓친다 —
    실측에서 신입 조건이 **133건 → 160건** 으로 달라졌다.
    사람인 화면이 시를 고르면 구까지 자동으로 붙이는 이유가 이것이다.
    """
    data = json.loads(LOCATION_FILE.read_text(encoding="utf-8"))
    under: dict[str, list[str]] = {}
    for province in data["domestic"]:
        for district in province["districts"]:
            name = district["name"]
            if " " not in name:
                continue
            city = name.split(" ", 1)[0]
            under.setdefault(city, []).append(district["loc_bcd"])
    return under


@lru_cache(maxsize=1)
def _location_index() -> dict[str, tuple[str, str]]:
    """이름(그리고 흔한 줄임말) → (파라미터, 코드).

    `서울` `서울특별시` `강남구` `경기 성남시` 를 다 받는다. 같은 이름을 가진 구가
    여러 시도에 있으므로(`중구` `서구` `남구`) **시도를 붙인 이름도 함께** 넣는다.
    """
    data = json.loads(LOCATION_FILE.read_text(encoding="utf-8"))
    index: dict[str, tuple[str, str]] = {}
    ambiguous: set[str] = set()
    for province in data["domestic"]:
        name = province["name"]
        for spelling in _province_spellings(name):
            index[spelling] = (PROVINCE_PARAM, province["loc_mcd"])
        for district in province["districts"]:
            key = district["name"]
            value = (DISTRICT_PARAM, district["loc_bcd"])
            index["%s %s" % (name, key)] = value          # `경기 성남시`
            if key in index and index[key] != value:
                ambiguous.add(key)                        # `중구` 는 여러 시도에 있다
            else:
                index.setdefault(key, value)
    for key in ambiguous:
        index.pop(key, None)
    return index


def _province_spellings(name: str) -> list[str]:
    """`서울` `서울특별시` `서울시` 를 다 받는다. 사람이 적는 대로 쓰게 한다."""
    spellings = {name}
    if not name.endswith(("도", "시")):
        spellings |= {name + "시", name + "특별시", name + "광역시"}
    return sorted(spellings)


def ambiguous_names() -> list[str]:
    """여러 시도에 같은 이름이 있어 혼자서는 못 정하는 구 이름."""
    data = json.loads(LOCATION_FILE.read_text(encoding="utf-8"))
    seen: dict[str, int] = {}
    for province in data["domestic"]:
        for district in province["districts"]:
            seen[district["name"]] = seen.get(district["name"], 0) + 1
    return sorted(name for name, count in seen.items() if count > 1)


def resolve_locations(names: list[str]) -> dict[str, list[str]]:
    """근무지 이름들 → `{loc_mcd: [...], loc_bcd: [...]}`.

    하나라도 못 옮기면 **멈춘다.** 조용히 빼면 조건이 느슨해져서 전국을 긁는데,
    그건 결과가 늘어나는 방향이라 사람이 알아채기 어렵다.
    """
    resolved: dict[str, list[str]] = {}
    unknown: list[str] = []
    index = _location_index()
    for raw in names:
        name = " ".join(raw.split())
        found = index.get(name) or index.get(name.replace(" ", ""))
        if not found:
            unknown.append(raw)
            continue
        parameter, code = found
        if code == NATIONWIDE_BUCKET:
            # "전국" 을 적었다면 뜻은 "전부" 다. 버킷 하나로 좁히면 10건만 나온다.
            return {}
        codes = resolved.setdefault(parameter, [])
        # 시를 골랐으면 그 아래 구까지 함께 보낸다 — 시 코드는 구를 포함하지 않는다.
        for one in [code] + (_sub_districts().get(name, [])
                             if parameter == DISTRICT_PARAM else []):
            if one not in codes:
                codes.append(one)
    if unknown:
        raise LocationError(
            "근무지 이름을 사람인 코드로 옮기지 못했습니다: %s\n"
            "  쓸 수 있는 이름은 job_sites/saramin/tags/saramin_location.json 에 있습니다.\n"
            "  여러 시도에 같은 이름이 있는 구(%s)는 `대구 중구` 처럼 시도를 붙여 주세요."
            % (", ".join(unknown), ", ".join(ambiguous_names()[:5])))
    # 콤마 하나로 잇는다 — 같은 이름을 여러 번 보내면 마지막 것만 먹는다.
    return {parameter: ",".join(codes) for parameter, codes in resolved.items()}


def experience_params(yoe: int) -> dict[str, str]:
    """경력 조건 → 파라미터.

    `exp_min` 은 **`exp_cd=2` 와 함께 줘야** 먹는다. 단독으로 주면 에러 없이 전체가
    돌아온다 — 필터가 먹은 줄 알기 딱 좋다.

    **경력무관은 따로 걸 필요가 없다.** `exp_cd=1`(신입) 결과가 이미 품고 있다.
    실측 — 신입 160건의 속을 보면 `신입` 103 + `경력무관` 57 이고,
    경력무관으로 따로 뽑은 58건 중 57건이 그 안에 있었다.

    **`exp_none=y` 를 경력무관으로 쓰면 안 된다.** 그것으로 뽑은 82건은
    `경력무관` 58 + `신입` 16 + **`경력(년수무관)` 8** 이 섞인다 —
    "경력을 안 본다" 가 아니라 "**년수를 안 적었다**" 는 뜻이다.
    신입을 찾는 사람에게 경력직 공고가 딸려 온다.
    """
    if yoe < 0:
        return {}
    if yoe == 0:
        return {"exp_cd": NEW_GRADUATE}
    return {"exp_cd": EXPERIENCED, "exp_min": str(yoe)}


def education_params(level: str) -> dict[str, str]:
    """학력 조건 → 파라미터. `대졸4` 는 **딱 4년제를 요구하는 공고**다.

    `edu_min` 만 주면 "4년제 이상"(869건), `edu_max` 만 주면 "4년제 이하"(1,500건)라
    뜻이 달라진다. 둘을 같이 줘야 그 학력으로 좁혀진다(846건).
    """
    level = (level or "").strip()
    if not level:
        return {}
    if level == EDUCATION_ANY:
        return {"edu_none": "y"}
    if level not in EDUCATION_CODES:
        raise ConfigError("EDUCATION 에 모르는 값이 있습니다: %r. 쓸 수 있는 값: %s, %s"
                          % (level, ", ".join(EDUCATION_CODES), EDUCATION_ANY))
    low, high = EDUCATION_CODES[level]
    return {"edu_min": low, "edu_max": high}


def build_search_params(config) -> dict:
    """`.env` 조건 하나를 사람인 검색 파라미터로."""
    # **값이 여럿이면 콤마 하나로 잇는다.** 같은 이름을 여러 번 보내면 사람인은
    # 마지막 값만 쓴다 — 조건을 넓혔는데 결과가 줄고 예외도 안 난다.
    # `client._query` 도 같은 규칙을 지키지만, 여기서도 문자열로 못박아 두 겹으로 막는다.
    params: dict = {
        "cat_kewd": ",".join(str(code) for code in config.job_ids),
        "search_optional_item": "y",
        "search_done": "y",
        "panel_count": "y",
        "preview": "y",
        "recruitSort": "relation",
        "recruitPageCount": "50",
    }
    params.update(experience_params(config.yoe))
    params.update(education_params(config.education))
    params.update(resolve_locations(config.home_locations))
    if config.employment_type_codes:
        params["job_type"] = ",".join(config.employment_type_codes)
    return params
