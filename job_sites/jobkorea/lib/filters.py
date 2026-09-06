"""수집 조건 → 잡코리아 검색 파라미터.

**코드표에 있다고 필터가 먹는 게 아니다.** 실측에서 셋이 조용히 어긋났다.

| 함정 | 무슨 일이 나는가 |
|---|---|
| 직무 **대분류** 코드를 `duty` 에 | `duty=10031` 이 기준선과 같은 197,561건. **전체가 나온다** |
| 같은 이름을 여러 번 보내기 | **첫 값만** 먹는다 (사람인은 마지막 값이었다) |
| 구가 있는 시를 이름으로만 | `성남시` 라는 코드가 **아예 없다.** 구로 펼쳐야 한다 |

셋 다 예외가 안 나고 결과도 나온다. 그래서 이 모듈이 파라미터를 만들 때 지킨다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from _common.env import ConfigError

from .config import EDUCATION_CODES

TAGS_DIR = Path(__file__).resolve().parent.parent / "tags"
LOCATION_FILE = TAGS_DIR / "jobkorea_location.json"
DUTY_FILE = TAGS_DIR / "jobkorea_duty.json"

# 잡코리아 경력 코드. `.env` 의 YOE(년차)를 이 구간에 넣는다.
CAREER_NEW = "1"          # 신입
CAREER_ANY = "8"          # 경력무관
CAREER_BANDS = [(1, 3, "2"), (4, 6, "3"), (7, 9, "4"),
                (10, 15, "5"), (16, 20, "6"), (21, 99, "7")]

# 시도 안에서 구가 안 정해진 공고를 뜻하는 코드(`I000_`). 시도 전체와 다르므로 안 쓴다.
UNSPECIFIED_SUFFIX = "_"
NATIONWIDE = "전국"


class LocationError(ValueError):
    """근무지 이름을 코드로 못 옮겼다. **조용히 빼면 전국을 긁는다.**"""


@lru_cache(maxsize=1)
def _location_index() -> dict[str, list[str]]:
    """이름 → 코드들.

    **구가 있는 시는 시 코드가 없다.** 잡코리아에는 `성남시 분당구`·`성남시 수정구`·
    `성남시 중원구` 만 있고 `성남시` 는 없다. 그래서 `성남시` 를 적으면 그 셋으로 펼친다.
    사람인은 시 코드가 따로 있었지만 구를 포함하지 않아 역시 펼쳐야 했다 — 이유는 달라도
    결론은 같다.
    """
    data = json.loads(LOCATION_FILE.read_text(encoding="utf-8"))
    index: dict[str, list[str]] = {}
    ambiguous: set[str] = set()
    for province in data["provinces"]:
        index[province["name"]] = [province["code"]]
        cities: dict[str, list[str]] = {}
        for district in province["districts"]:
            name, code = district["name"], district["code"]
            if code.endswith(UNSPECIFIED_SUFFIX):
                continue
            full = "%s %s" % (province["name"], name)
            index[full] = [code]
            if " " in name:                      # `성남시 분당구` → 시 이름으로도 묶는다
                cities.setdefault(name.split(" ", 1)[0], []).append(code)
            if name in index and index[name] != [code]:
                ambiguous.add(name)              # `중구` 는 여러 시도에 있다
            else:
                index.setdefault(name, [code])
        for city, codes in cities.items():
            index["%s %s" % (province["name"], city)] = codes
            if city in index and sorted(index[city]) != sorted(codes):
                ambiguous.add(city)
            else:
                index[city] = codes
    for name in ambiguous:
        index.pop(name, None)
    return index


def ambiguous_names() -> list[str]:
    """여러 시도에 같은 이름이 있어 혼자서는 못 정하는 구 이름."""
    data = json.loads(LOCATION_FILE.read_text(encoding="utf-8"))
    seen: dict[str, int] = {}
    for province in data["provinces"]:
        for district in province["districts"]:
            if not district["code"].endswith(UNSPECIFIED_SUFFIX):
                seen[district["name"]] = seen.get(district["name"], 0) + 1
    return sorted(name for name, count in seen.items() if count > 1)


def resolve_locations(names: list[str]) -> str:
    """근무지 이름들 → 콤마로 이은 `local` 값. 안 적으면 빈 문자열(전국).

    하나라도 못 옮기면 **멈춘다.** 조용히 빼면 조건이 느슨해져 전국을 긁는데,
    결과가 늘어나는 방향이라 사람이 알아채기 어렵다.
    """
    index = _location_index()
    codes: list[str] = []
    unknown: list[str] = []
    for raw in names:
        name = " ".join(raw.split())
        if name == NATIONWIDE:
            return ""                    # 전국은 조건을 안 거는 것이다
        found = index.get(name)
        if not found:
            unknown.append(raw)
            continue
        for code in found:
            if code not in codes:
                codes.append(code)
    if unknown:
        raise LocationError(
            "근무지 이름을 잡코리아 코드로 옮기지 못했습니다: %s\n"
            "  쓸 수 있는 이름은 job_sites/jobkorea/tags/jobkorea_location.json 에 있습니다.\n"
            "  여러 시도에 같은 이름이 있는 구(%s)는 `대구 중구` 처럼 시도를 붙여 주세요."
            % (", ".join(unknown), ", ".join(ambiguous_names()[:5])))
    return ",".join(codes)


def career_code(yoe: int) -> str:
    """년차 → 경력 코드. 전체면 빈 문자열.

    **경력무관을 따로 안 붙인다.** 사람인에서 `exp_none` 을 경력무관으로 쓰다 경력직이
    섞여 든 적이 있는데, 잡코리아는 `career=8` 이 진짜 경력무관이라 뜻이 어긋나지 않는다.
    다만 신입을 찾을 때 그것까지 더할지는 **측정한 뒤에 정한다** — 지금은 안 더한다.
    """
    if yoe < 0:
        return ""
    if yoe == 0:
        return CAREER_NEW
    for low, high, code in CAREER_BANDS:
        if low <= yoe <= high:
            return code
    return CAREER_BANDS[-1][2]


@lru_cache(maxsize=1)
def _duty_codes() -> dict[str, str]:
    """쓸 수 있는 직무 코드(중분류) → 이름."""
    data = json.loads(DUTY_FILE.read_text(encoding="utf-8"))
    return {s["code"]: s["name"] for g in data["groups"] for s in g["sub"]}


@lru_cache(maxsize=1)
def _duty_groups() -> dict[str, str]:
    """대분류 코드 → 이름. **쓰면 안 되는 것**을 알려 주려고 들고 있다."""
    data = json.loads(DUTY_FILE.read_text(encoding="utf-8"))
    return {g["code"]: g["name"] for g in data["groups"]}


def duty_value(job_ids: list[int]) -> str:
    """직무 코드들 → 콤마로 이은 `duty` 값.

    **대분류 코드가 섞이면 멈춘다.** 그걸 보내면 필터가 통째로 무시돼 전체가 나오는데,
    에러가 안 나서 조건이 먹은 줄 알기 딱 좋다.
    """
    known, groups = _duty_codes(), _duty_groups()
    codes = [str(code) for code in job_ids]
    wrong = [c for c in codes if c in groups]
    if wrong:
        raise ConfigError(
            "직무에 **대분류** 코드가 들어 있습니다: %s\n"
            "  대분류를 보내면 필터가 무시돼 전체가 나옵니다 — 에러도 안 납니다.\n"
            "  중분류 코드를 쓰세요. 예: %s"
            % (", ".join("%s(%s)" % (c, groups[c]) for c in wrong),
               ", ".join(list(known)[:3])))
    unknown = [c for c in codes if c not in known]
    if unknown:
        raise ConfigError(
            "코드표에 없는 직무 코드입니다: %s\n"
            "  job_sites/jobkorea/tags/jobkorea_duty.json 을 보세요." % ", ".join(unknown))
    return ",".join(dict.fromkeys(codes))


def build_conditions(config) -> dict:
    """`.env` 조건 → 잡코리아 `condition[...]` 묶음.

    빈 값은 넣지 않는다 — 잡코리아는 빈 파라미터를 조건으로 잘못 읽을 수 있고,
    무엇이 실제로 걸렸는지 화면에 찍을 때도 헷갈린다.
    """
    conditions = {
        "menucode": "duty",
        "duty": duty_value(config.job_ids),
        "local": resolve_locations(config.home_locations),
        "career": career_code(config.yoe),
        "edu": EDUCATION_CODES.get(config.education, ""),
        "jobtype": ",".join(config.employment_type_codes),
    }
    return {key: value for key, value in conditions.items() if value}
