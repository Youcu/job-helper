""".env 를 읽어 검증된 수집 조건으로 만든다.

읽는 방법 자체(주석 처리·콤마 목록·셸 환경변수 차단)는 사이트가 공유하므로
`_common/env.py` 에 있다. 여기에는 **Wanted 가 무엇을 요구하는가**만 남긴다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from _common.env import ENV_PATH, ConfigError, csv_list, one_int
from _common import roles
from _common.env import int_list as _int_list_common
from _common.env import read_env, strip_comment

SITE = "wanted"
TAGS_DIR = Path(__file__).resolve().parent.parent / "tags"
ROLE_MAP = TAGS_DIR / "wanted_role_map.json"
CATEGORY_FILE = TAGS_DIR / "wanted_category.json"

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
    # 이 사이트에 대응 코드가 없어 못 건 역할. **조용히 빠지지 않게** 화면에 찍는다.
    missing_roles: list[str] = field(default_factory=list)

    @property
    def employment_type_keys(self) -> list[str]:
        return [EMPLOYMENT_TYPE_KEYS[t] for t in self.employment_types]


@lru_cache(maxsize=1)
def _group_of() -> dict[str, int]:
    """직무 코드 → 그 직무가 속한 직군 코드.

    `wanted_category.json` 이 `직군 → 직무들` 로 되어 있어 뒤집어 읽는다.
    """
    data = json.loads(CATEGORY_FILE.read_text(encoding="utf-8"))
    book: dict[str, int] = {}
    for group in data["category"]:
        for tag in group.get("tags", []):
            book[str(tag["id"])] = int(group["id"])
    return book


def group_ids_for(job_ids) -> list[int]:
    """직무들이 속한 직군들. **중복은 없애고 차례는 지킨다.**

    API 가 직군을 하나씩만 받아서(다중 지정하면 마지막 값만 쓴다) 스크래퍼가 직군마다
    따로 훑는데, 그 차례가 실행마다 바뀌면 결과 순서도 바뀐다.
    """
    book = _group_of()
    groups: list[int] = []
    for code in job_ids:
        group = book.get(str(code))
        if group is not None and group not in groups:
            groups.append(group)
    return groups


def load_config(env_path: Path | None = None) -> Config:
    """`.env` 파일 하나만 읽는다.

    `load_dotenv()` 는 값을 `os.environ` 에 심는다. 그러면 `.env` 에 줄이 없는 항목이
    셸 환경변수에서 조용히 새어 들어온다 — 근무지를 안 적었는데 셸에 `HOME_LOCATIONS=부산`
    이 있으면 부산 공고를 긁는다. 그래서 환경을 건드리지 않는 `dotenv_values()` 로 읽는다.
    """
    path = env_path or ENV_PATH
    env = read_env(path)

    employment_types = csv_list(env.get("EMPLOYMENT_TYPES")) or list(DEFAULT_EMPLOYMENT_TYPES)
    unknown = [t for t in employment_types if t not in EMPLOYMENT_TYPE_KEYS]
    if unknown:
        raise ConfigError(
            f"EMPLOYMENT_TYPES 에 모르는 값이 있습니다: {unknown}. "
            f"쓸 수 있는 값: {', '.join(EMPLOYMENT_TYPE_KEYS)}"
        )

    yoe = one_int(env.get("YOE"), "YOE (신입=0, N년차=N, 전체=-1)",
                  default=-1, low=-1, high=10)

    _role_codes = roles.resolve(env, ROLE_MAP)
    # **직군은 직무에서 유도한다.** API 가 `job_group_id` 를 따로 요구하지만, 그것은 직무의
    # 상위 분류일 뿐이라 사람이 또 적을 이유가 없다 — 적게 하면 직무와 어긋날 여지만 생긴다.
    job_group_ids = group_ids_for(_role_codes[0])
    if not job_group_ids:
        raise ConfigError(
            "고른 직무가 어느 직군에도 속하지 않습니다: %s\n"
            "  job_sites/wanted/tags/wanted_category.json 과 wanted_role_map.json 이"
            " 어긋났을 수 있습니다." % _role_codes[0])
    return Config(
        job_group_ids=job_group_ids,
        job_ids=[int(code) for code in _role_codes[0]],
        missing_roles=_role_codes[1],
        employment_types=employment_types,
        yoe=yoe,
        home_locations=csv_list(env.get("HOME_LOCATIONS")),
        tech_stacks=csv_list(env.get("TECH_STACKS")),
        hope_annual_salary=strip_comment(env.get("HOPE_ANNUAL_SALARY")) or None,
    )
