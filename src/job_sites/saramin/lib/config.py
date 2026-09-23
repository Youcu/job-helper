""".env 를 읽어 사람인 수집 조건으로 만든다.

읽는 방법(주석 처리·콤마 목록·셸 환경변수 차단)은 `_common/env.py` 에 있다.
여기에는 **사람인이 무엇을 요구하는가**만 둔다.

`.env` 는 **여섯 사이트가 함께 쓰는 한 벌**이다. 직무도 `JOB_ROLES=백엔드,웹` 처럼
이름으로 적고, `tags/saramin_role_map.json` 이 그것을 사람인 코드(`84`)로 옮긴다 —
Wanted 의 `872` 와 같은 칸에 넣을 수 없는 값이라 사람이 직접 적게 하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from _common import roles
from _common.env import (ENV_PATH, ConfigError, csv_list, int_list, one_int,
                         read_env, strip_comment)

SITE = "saramin"
ROLE_MAP = Path(__file__).resolve().parent.parent / "tags" / "saramin_role_map.json"

# `.env` 의 짧은 이름 → 사람인 `job_type` 코드.
EMPLOYMENT_TYPE_CODES = {
    "regular": "1",       # 정규직
    "contract": "2",      # 계약직
    "intern": "4",        # 인턴직
    "parttime": "5",      # 아르바이트
    "freelance": "9",     # 프리랜서
    "dispatch": "6",      # 파견직
}
DEFAULT_EMPLOYMENT_TYPES = ["regular", "intern"]

# YOE 를 사람인 파라미터로 옮기는 규칙은 filters.py 에 있다. 여기서는 값만 받는다.
YOE_ALL = -1
YOE_MAX = 20



@dataclass
class Config:
    job_ids: list[int] = field(default_factory=list)          # cat_kewd
    employment_types: list[str] = field(default_factory=lambda: list(DEFAULT_EMPLOYMENT_TYPES))
    yoe: int = YOE_ALL
    education: str = ""                    # 고졸 · 대졸2 · 대졸4 · 석사 · 박사 · 무관
    home_locations: list[str] = field(default_factory=list)
    tech_stacks: list[str] = field(default_factory=list)
    hope_annual_salary: str | None = None
    # 이 사이트에 대응 코드가 없어 못 건 역할. **조용히 빠지지 않게** 화면에 찍는다.
    missing_roles: list[str] = field(default_factory=list)

    @property
    def employment_type_codes(self) -> list[str]:
        return [EMPLOYMENT_TYPE_CODES[name] for name in self.employment_types]


def load_config(env_path: Path | None = None) -> Config:
    env = read_env(env_path or ENV_PATH)

    job_ids, missing_roles = roles.resolve(env, ROLE_MAP)
    employment_types = csv_list(env.get("EMPLOYMENT_TYPES")) or list(DEFAULT_EMPLOYMENT_TYPES)
    unknown = [name for name in employment_types if name not in EMPLOYMENT_TYPE_CODES]
    if unknown:
        raise ConfigError("EMPLOYMENT_TYPES 에 모르는 값이 있습니다: %s. 쓸 수 있는 값: %s"
                          % (unknown, ", ".join(EMPLOYMENT_TYPE_CODES)))

    return Config(
        job_ids=[int(code) for code in job_ids],
        missing_roles=missing_roles,
        employment_types=employment_types,
        yoe=one_int(env.get("YOE"), "YOE (신입=0, N년차=N, 전체=-1)",
                    default=YOE_ALL, low=YOE_ALL, high=YOE_MAX),
        education=strip_comment(env.get("EDUCATION")),
        home_locations=csv_list(env.get("HOME_LOCATIONS")),
        tech_stacks=csv_list(env.get("TECH_STACKS")),
        hope_annual_salary=env.get("HOPE_ANNUAL_SALARY") or None,
    )
