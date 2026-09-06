""".env 를 읽어 잡코리아 수집 조건으로 만든다.

읽는 방법(주석 처리·콤마 목록·셸 환경변수 차단)은 `_common/env.py` 에 있다.
여기에는 **잡코리아가 무엇을 요구하는가**만 둔다.

`YOE` `HOME_LOCATIONS` `EDUCATION` `EMPLOYMENT_TYPES` 는 뜻이 사이트 중립이라
Wanted·사람인과 같은 이름을 쓴다. 직무 코드만 값 체계가 달라 `JOBKOREA_JOB_IDS` 로 나눈다 —
사람인의 `84` 와 잡코리아의 `1000229` 는 같은 칸에 넣을 수 없다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from _common.env import (ENV_PATH, ConfigError, csv_list, int_list, one_int,
                         read_env, site_key, strip_comment)

SITE = "jobkorea"

# `.env` 의 짧은 이름 → 잡코리아 `jobtype` 코드.
EMPLOYMENT_TYPE_CODES = {
    "regular": "1",       # 정규직
    "contract": "2",      # 계약직
    "intern": "3",        # 인턴
    "dispatch": "4",      # 파견직
    "outsourced": "5",    # 도급
    "freelance": "6",     # 프리랜서
    "parttime": "7",      # 아르바이트
}
DEFAULT_EMPLOYMENT_TYPES = ["regular", "intern"]

# 사이트 중립 학력 이름 → 잡코리아 `edu` 코드.
# 사람인은 min/max 두 축이라 범위를 줘야 했는데, 잡코리아는 **한 축**이라 값 하나면 된다.
EDUCATION_CODES = {
    "고졸": "3", "대졸2": "4", "대졸4": "5", "석사": "6", "박사": "7", "무관": "0",
}

YOE_ALL = -1
YOE_MAX = 20


@dataclass
class Config:
    job_ids: list[int] = field(default_factory=list)          # duty 중분류
    employment_types: list[str] = field(default_factory=lambda: list(DEFAULT_EMPLOYMENT_TYPES))
    yoe: int = YOE_ALL
    education: str = ""
    home_locations: list[str] = field(default_factory=list)
    tech_stacks: list[str] = field(default_factory=list)
    hope_annual_salary: str | None = None

    @property
    def employment_type_codes(self) -> list[str]:
        return [EMPLOYMENT_TYPE_CODES[name] for name in self.employment_types]


def load_config(env_path: Path | None = None) -> Config:
    env = read_env(env_path or ENV_PATH)

    job_ids = int_list(site_key(env, SITE, "JOB_IDS"), "JOBKOREA_JOB_IDS")
    if not job_ids:
        raise ConfigError(
            "JOBKOREA_JOB_IDS 가 비어 있습니다. 잡코리아 직무 코드를 comma 로 적어 주세요.\n"
            "  코드표는 job_sites/jobkorea/README.md 의 '직무 코드' 표에 있습니다.\n"
            "  **중분류 코드를 넣어야 합니다** — 대분류는 필터가 통째로 무시됩니다.\n"
            "  예: JOBKOREA_JOB_IDS=1000229,1000231   (백엔드개발자, 웹개발자)")

    employment_types = csv_list(env.get("EMPLOYMENT_TYPES")) or list(DEFAULT_EMPLOYMENT_TYPES)
    unknown = [name for name in employment_types if name not in EMPLOYMENT_TYPE_CODES]
    if unknown:
        raise ConfigError("EMPLOYMENT_TYPES 에 모르는 값이 있습니다: %s. 쓸 수 있는 값: %s"
                          % (unknown, ", ".join(EMPLOYMENT_TYPE_CODES)))

    education = strip_comment(env.get("EDUCATION"))
    if education and education not in EDUCATION_CODES:
        raise ConfigError("EDUCATION 에 모르는 값이 있습니다: %r. 쓸 수 있는 값: %s"
                          % (education, ", ".join(EDUCATION_CODES)))

    return Config(
        job_ids=job_ids,
        employment_types=employment_types,
        yoe=one_int(env.get("YOE"), "YOE (신입=0, N년차=N, 전체=-1)",
                    default=YOE_ALL, low=YOE_ALL, high=YOE_MAX),
        education=education,
        home_locations=csv_list(env.get("HOME_LOCATIONS")),
        tech_stacks=csv_list(env.get("TECH_STACKS")),
        hope_annual_salary=env.get("HOPE_ANNUAL_SALARY") or None,
    )
