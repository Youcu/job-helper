""".env 를 읽어 검증된 수집 조건으로 만든다.

읽는 방법 자체(주석 처리·콤마 목록·셸 환경변수 차단)는 사이트가 공유하므로
`_common/env.py` 에 있다. 여기에는 **Wanted 가 무엇을 요구하는가**만 남긴다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from _common.env import ENV_PATH, ConfigError, csv_list, one_int
from _common.env import int_list as _int_list_common
from _common.env import read_env, site_key, strip_comment

SITE = "wanted"

# `.env` 는 짧은 이름으로 적고, API 에는 긴 키로 보낸다.
EMPLOYMENT_TYPE_KEYS = {
    "regular": "job.employment_type.regular",
    "contract": "job.employment_type.contract",
    "intern": "job.employment_type.intern",
}
DEFAULT_EMPLOYMENT_TYPES = ["regular", "intern"]












@dataclass
class Config:
    job_group_ids: list[int]
    job_ids: list[int] = field(default_factory=list)
    employment_types: list[str] = field(default_factory=lambda: list(DEFAULT_EMPLOYMENT_TYPES))
    yoe: int = -1
    home_locations: list[str] = field(default_factory=list)
    tech_stacks: list[str] = field(default_factory=list)
    hope_annual_salary: str | None = None

    @property
    def employment_type_keys(self) -> list[str]:
        return [EMPLOYMENT_TYPE_KEYS[t] for t in self.employment_types]


def load_config(env_path: Path | None = None) -> Config:
    """`.env` 파일 하나만 읽는다.

    `load_dotenv()` 는 값을 `os.environ` 에 심는다. 그러면 `.env` 에 줄이 없는 항목이
    셸 환경변수에서 조용히 새어 들어온다 — 근무지를 안 적었는데 셸에 `HOME_LOCATIONS=부산`
    이 있으면 부산 공고를 긁는다. 그래서 환경을 건드리지 않는 `dotenv_values()` 로 읽는다.
    """
    path = env_path or ENV_PATH
    env = read_env(path)

    job_group_ids = _int_list_common(site_key(env, SITE, "JOB_GROUP_IDS"), "WANTED_JOB_GROUP_IDS")
    if not job_group_ids:
        raise ConfigError(
            f"WANTED_JOB_GROUP_IDS 가 비어 있습니다. 직군 코드를 comma 로 적어 주세요 ({path}).\n"
            "  코드표는 job_sites/wanted/README.md 의 '직군 코드' 표에 있습니다.\n"
            "  예: WANTED_JOB_GROUP_IDS=518   (개발)"
        )

    employment_types = csv_list(env.get("EMPLOYMENT_TYPES")) or list(DEFAULT_EMPLOYMENT_TYPES)
    unknown = [t for t in employment_types if t not in EMPLOYMENT_TYPE_KEYS]
    if unknown:
        raise ConfigError(
            f"EMPLOYMENT_TYPES 에 모르는 값이 있습니다: {unknown}. "
            f"쓸 수 있는 값: {', '.join(EMPLOYMENT_TYPE_KEYS)}"
        )

    yoe = one_int(env.get("YOE"), "YOE (신입=0, N년차=N, 전체=-1)",
                  default=-1, low=-1, high=10)

    return Config(
        job_group_ids=job_group_ids,
        job_ids=_int_list_common(site_key(env, SITE, "JOB_IDS"), "WANTED_JOB_IDS"),
        employment_types=employment_types,
        yoe=yoe,
        home_locations=csv_list(env.get("HOME_LOCATIONS")),
        tech_stacks=csv_list(env.get("TECH_STACKS")),
        hope_annual_salary=strip_comment(env.get("HOPE_ANNUAL_SALARY")) or None,
    )
