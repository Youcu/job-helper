""".env 를 읽어 잡플래닛 수집 조건으로 만든다.

읽는 방법(주석 처리·콤마 목록·셸 환경변수 차단)은 `_common/env.py` 에 있다.
여기에는 **잡플래닛이 무엇을 요구하는가**만 둔다.

## 이 사이트가 다른 점 셋

`.env` 의 같은 항목이 여기서는 다르게 쓰인다. 전부 실측으로 정했고, 실행할 때
화면에 이유를 찍는다 — **조용히 무시하면 다른 사이트와 결과가 어긋난 이유를 못 찾는다.**

| 항목 | 어떻게 되는가 | 왜 |
|---|---|---|
| `EDUCATION` | **안 건다** | 자체 공고 84%가 `학력무관` 이라 걸면 사라진다 (실측 37→6건) |
| `EMPLOYMENT_TYPES` | **정규직만** 건다 | 잡플래닛 고용형태 코드는 정규직·계약직 둘뿐이다 |
| `HOME_LOCATIONS` | 시도까지만 걸고 **나머지는 받은 뒤 거른다** | 지역 코드에 구·시가 없다 |
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from _common import roles
from _common.env import (ENV_PATH, ConfigError, csv_list, int_list, one_int,
                         read_env, strip_comment)

SITE = "jobplanet"
ROLE_MAP = Path(__file__).resolve().parent.parent / "tags" / "jobplanet_role_map.json"

# 잡플래닛 고용형태 코드. **둘뿐이다** — 인턴·파견·프리랜서가 없다.
EMPLOYMENT_TYPE_CODES = {"regular": "3", "contract": "4"}
DEFAULT_EMPLOYMENT_TYPES = ["regular"]

# 학력 코드. 지금은 필터로 안 쓰지만, 상세 응답의 값을 읽을 때 쓰고 README 에도 싣는다.
EDUCATION_CODES = {
    "고졸": "3", "대졸2": "4", "대졸4": "5", "대학원": "6",
    "석사": "7", "박사": "8", "무관": "9",
}

YOE_ALL = -1
YOE_MAX = 11          # 코드표의 위쪽 끝이 "10년 이상"=11 이다


@dataclass
class Config:
    job_ids: list[int] = field(default_factory=list)          # occupation_level2 (중분류)
    employment_types: list[str] = field(default_factory=lambda: list(DEFAULT_EMPLOYMENT_TYPES))
    yoe: int = YOE_ALL
    education: str = ""
    home_locations: list[str] = field(default_factory=list)
    tech_stacks: list[str] = field(default_factory=list)
    hope_annual_salary: str | None = None
    # 이 사이트에 대응 코드가 없어 못 건 역할. **조용히 빠지지 않게** 화면에 찍는다.
    missing_roles: list[str] = field(default_factory=list)

    @property
    def employment_type_codes(self) -> list[str]:
        """**잡플래닛에 있는 것만** 코드로 바꾼다. 없는 것은 `unsupported_employment_types` 다."""
        return [EMPLOYMENT_TYPE_CODES[name] for name in self.employment_types
                if name in EMPLOYMENT_TYPE_CODES]

    @property
    def unsupported_employment_types(self) -> list[str]:
        """이 사이트에 코드가 없어서 못 거는 고용형태. 실행할 때 화면에 찍는다."""
        return [name for name in self.employment_types if name not in EMPLOYMENT_TYPE_CODES]


def load_config(env_path: Path | None = None) -> Config:
    env = read_env(env_path or ENV_PATH)

    job_ids, missing_roles = roles.resolve(env, ROLE_MAP)
    employment_types = csv_list(env.get("EMPLOYMENT_TYPES")) or list(DEFAULT_EMPLOYMENT_TYPES)
    unknown = [name for name in employment_types
               if name not in EMPLOYMENT_TYPE_CODES and name not in _KNOWN_ELSEWHERE]
    if unknown:
        raise ConfigError(
            "EMPLOYMENT_TYPES 에 모르는 값이 있습니다: %s\n"
            "  다른 사이트에서 쓰는 값: %s\n"
            "  이 중 잡플래닛이 거를 수 있는 것: %s"
            % (unknown, ", ".join(sorted(_KNOWN_ELSEWHERE | set(EMPLOYMENT_TYPE_CODES))),
               ", ".join(EMPLOYMENT_TYPE_CODES)))

    education = strip_comment(env.get("EDUCATION"))
    if education and education not in EDUCATION_CODES:
        raise ConfigError("EDUCATION 에 모르는 값이 있습니다: %r. 쓸 수 있는 값: %s"
                          % (education, ", ".join(EDUCATION_CODES)))

    return Config(
        job_ids=[int(code) for code in job_ids],
        missing_roles=missing_roles,
        employment_types=employment_types,
        yoe=one_int(env.get("YOE"), "YOE (신입=0, N년차=N, 전체=-1)",
                    default=YOE_ALL, low=YOE_ALL, high=YOE_MAX),
        education=education,
        home_locations=csv_list(env.get("HOME_LOCATIONS")),
        tech_stacks=csv_list(env.get("TECH_STACKS")),
        hope_annual_salary=env.get("HOPE_ANNUAL_SALARY") or None,
    )


# 다른 사이트에는 있고 잡플래닛에는 없는 고용형태. **오타와 구분하려고 들고 있다** —
# `intern` 은 멀쩡한 값이라 멈추면 안 되고, `정규직` 같은 오타는 멈춰야 한다.
_KNOWN_ELSEWHERE = {"intern", "dispatch", "outsourced", "freelance", "parttime"}
