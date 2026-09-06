"""수집 조건 → 잡플래닛 검색 파라미터.

**세 함정이 전부 조용하다** — 예외가 안 나고 결과도 나온다. 그래서 이 모듈이 막는다.

| 함정 | 실측 |
|---|---|
| 대분류와 중분류를 같이 보냄 | `level1=11600` 2,779 · `level2=11904` 579 · **둘 다 2,779** (중분류 무시) |
| 같은 이름을 두 번 보냄 | `11904` 579 · `11905` 288 · `11904&11905` **288** · `11904,11905` 673 |
| 경력을 값 하나로 보냄 | `years_of_experience=0` → 34,813(**기준선 그대로**) · `0,0` → 22,508 |

사람인은 반복 파라미터에서 마지막 값을, 잡코리아는 첫 값을 썼다. 방향은 제각각인데
결과는 같다 — 조용히 값을 잃는다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from _common.env import ConfigError

from .config import EMPLOYMENT_TYPE_CODES

TAGS_DIR = Path(__file__).resolve().parent.parent / "tags"
OCCUPATION_FILE = TAGS_DIR / "jobplanet_occupation.json"
FILTER_FILE = TAGS_DIR / "jobplanet_filter.json"

NATIONWIDE = "전국"

# 경력 범위의 위쪽 끝. 코드표의 "10년 이상" 이 11 이다.
YOE_CEILING = 11


class LocationError(ValueError):
    """근무지 이름을 시도 코드로 못 옮겼다. **조용히 빼면 전국을 긁는다.**"""


@lru_cache(maxsize=1)
def _filters() -> dict:
    return json.loads(FILTER_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _city_codes() -> dict[str, str]:
    """시도 이름 → 코드. **구·시는 없다** — 잡플래닛 지역은 시도까지다."""
    return {item["name"]: item["code"] for item in _filters()["city"]["items"]}


@lru_cache(maxsize=1)
def _occupation_codes() -> dict[str, str]:
    data = json.loads(OCCUPATION_FILE.read_text(encoding="utf-8"))
    return {s["code"]: s["name"] for g in data["groups"] for s in g["sub"]}


@lru_cache(maxsize=1)
def _occupation_groups() -> dict[str, str]:
    """대분류 코드 → 이름. **쓰면 안 되는 것**을 알려 주려고 들고 있다."""
    data = json.loads(OCCUPATION_FILE.read_text(encoding="utf-8"))
    return {g["code"]: g["name"] for g in data["groups"]}


def city_names() -> list[str]:
    return list(_city_codes())


def resolve_cities(names: list[str]) -> str:
    """근무지 이름들 → 콤마로 이은 `city` 값.

    **시도까지만 걸린다.** `성남시` 를 적으면 `경기` 로 넓어지고, 시·구 수준의 조건은
    받은 뒤 `record` 가 근무지 글로 거른다 (`matches_locations`). 여기서 못 걸었다고
    조건을 버리는 게 아니라, **거르는 자리를 옮기는 것**이다.

    아예 못 알아본 이름은 멈춘다 — 조용히 빼면 전국을 긁는데, 결과가 늘어나는
    방향이라 사람이 알아채기 어렵다.
    """
    codes: list[str] = []
    unknown: list[str] = []
    for raw in names:
        name = " ".join(raw.split())
        if name == NATIONWIDE:
            return ""
        code = _city_codes().get(name) or _city_codes().get(_province_of(name) or "")
        if not code:
            unknown.append(raw)
        elif code not in codes:
            codes.append(code)
    if unknown:
        raise LocationError(
            "근무지 이름을 잡플래닛 시도 코드로 옮기지 못했습니다: %s\n"
            "  잡플래닛 지역 코드는 **시도까지만** 있습니다: %s\n"
            "  구·시를 적으려면 그 시도 이름으로 적어 주세요 — 받은 뒤 근무지 글로 다시 거릅니다."
            % (", ".join(unknown), ", ".join(city_names())))
    return ",".join(codes)


# 시·구 이름 → 그 시도. 잡플래닛에는 시도 코드밖에 없어서, 좁은 이름을 넓은 코드로 올린다.
# 넓게 받은 뒤 `record.matches_locations` 가 원래 이름으로 다시 거른다.
_PROVINCE_HINTS = {
    "경기": ("성남", "수원", "용인", "화성", "고양", "안산", "부천", "안양", "평택", "시흥",
             "김포", "광주시", "광명", "군포", "하남", "오산", "이천", "안성", "의왕", "양평",
             "여주", "과천", "구리", "남양주", "파주", "의정부", "포천", "동두천", "가평", "연천"),
    "서울": ("강남", "서초", "송파", "마포", "영등포", "종로", "중구", "용산", "성동", "광진",
             "동대문", "중랑", "성북", "강북", "도봉", "노원", "은평", "서대문", "양천", "강서",
             "구로", "금천", "동작", "관악", "강동"),
    "인천": ("남동", "연수", "부평", "계양", "미추홀", "서구", "중구"),
}


def _province_of(name: str) -> str | None:
    """`성남시 분당구` 처럼 좁은 이름이면 그 시도 이름을 돌려준다."""
    head = name.split()[0] if name.split() else name
    for province, hints in _PROVINCE_HINTS.items():
        if name.startswith(province) or any(head.startswith(h) for h in hints):
            return province
    return None


def occupation_value(job_ids: list[int]) -> str:
    """직무 코드들 → 콤마로 이은 `occupation_level2` 값.

    **대분류 코드가 섞이면 멈춘다.** 대분류를 같이 보내면 중분류가 통째로 무시돼
    그 대분류 전체가 나오는데, 에러가 안 나서 조건이 먹은 줄 알기 딱 좋다.
    """
    known, groups = _occupation_codes(), _occupation_groups()
    codes = [str(code) for code in job_ids]
    wrong = [c for c in codes if c in groups]
    if wrong:
        raise ConfigError(
            "직무에 **대분류** 코드가 들어 있습니다: %s\n"
            "  대분류를 같이 보내면 중분류가 무시돼 그 대분류 전체가 나옵니다 — 에러도 안 납니다.\n"
            "  중분류 코드를 쓰세요. 예: %s"
            % (", ".join("%s(%s)" % (c, groups[c]) for c in wrong),
               ", ".join(list(known)[:3])))
    unknown = [c for c in codes if c not in known]
    if unknown:
        raise ConfigError(
            "코드표에 없는 직무 코드입니다: %s\n"
            "  job_sites/jobplanet/tags/jobplanet_occupation.json 을 보세요." % ", ".join(unknown))
    return ",".join(dict.fromkeys(codes))


def experience_range(yoe: int) -> str:
    """년차 → `years_of_experience` 범위. 전체면 빈 문자열.

    **값 하나로는 안 걸린다.** `years_of_experience=0` 은 기준선 그대로 34,813건이 나오고,
    `0,0` 이라야 22,508건으로 걸린다. 범위 필터라 두 값이 있어야 한다.

    신입(0)은 `0,0` 으로 정확히 잡고, N년차는 `0,N` 으로 **그 아래를 포함**한다 —
    "3년차인 내가 지원할 수 있는 공고" 는 3년을 **요구**하는 공고만이 아니다.
    """
    if yoe < 0:
        return ""
    return "0,%d" % min(yoe, YOE_CEILING)


def build_params(config) -> dict:
    """`.env` 조건 → 잡플래닛 질의 파라미터.

    빈 값은 넣지 않는다. **학력은 넣지 않는다** — 자체 공고 84%가 `학력무관` 이라
    걸면 사라진다(실측 37→6건). 그 사실은 엔트리포인트가 화면에 찍는다.
    """
    params = {
        "occupation_level2": occupation_value(config.job_ids),
        "city": resolve_cities(config.home_locations),
        "job_type": ",".join(config.employment_type_codes),
        "years_of_experience": experience_range(config.yoe),
    }
    return {key: value for key, value in params.items() if value}
