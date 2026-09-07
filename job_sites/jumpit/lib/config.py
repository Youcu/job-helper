""".env 를 읽어 점핏 수집 조건으로 만든다.

읽는 방법(주석 처리·콤마 목록·셸 환경변수 차단)은 `_common/env.py` 에 있다.
여기에는 **점핏이 무엇을 요구하는가**만 둔다.

## 기술스택으로 거르지 않는다

이 사이트는 기술 필터가 촘촘한데, **촘촘한 것이 오히려 독이다.** `Spring Boot` 를 고르면
아무것도 안 나오는데, 그 필터를 풀고 공고를 열면 본문이 `Spring Framework` 를 요구한다 —
사이트가 붙인 딱지와 공고가 실제로 쓰는 말이 어긋난다. 그래서 **지역·경력·직무만** 걸고,
기술은 받은 뒤 우리가 본문에서 읽는다.

## 학력도 안 건다

`education` 코드가 응답에 있지만 필터 파라미터로는 확인되지 않았고, 잡플래닛에서 학력을
걸었다가 자체 공고 84%를 잃은 일이 있다. 여기서도 걸지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from _common import roles
from _common.env import (ENV_PATH, ConfigError, csv_list, int_list, one_int,
                         read_env, strip_comment)

SITE = "jumpit"
ROLE_MAP = Path(__file__).resolve().parent.parent / "tags" / "jumpit_role_map.json"

# `.env` 의 짧은 이름 → 점핏에 있는지. **점핏은 고용형태를 안 거른다** —
# 필터 파라미터가 없다. 적어도 무시하되, 무시했다는 사실은 화면에 남긴다.
SUPPORTED_EMPLOYMENT_TYPES: frozenset[str] = frozenset()
KNOWN_ELSEWHERE = frozenset({"regular", "contract", "intern", "dispatch",
                             "outsourced", "freelance", "parttime"})

# 학력 이름. 필터로 안 쓰지만 상세의 `educationName` 을 읽을 때 쓰고 README 에도 싣는다.
EDUCATION_NAMES = ("고졸", "대졸2", "대졸4", "석사", "박사", "무관")

YOE_ALL = -1
YOE_MAX = 20


@dataclass
class Config:
    job_ids: list[int] = field(default_factory=list)          # jobCategory
    employment_types: list[str] = field(default_factory=list)
    yoe: int = YOE_ALL
    education: str = ""
    home_locations: list[str] = field(default_factory=list)
    tech_stacks: list[str] = field(default_factory=list)
    hope_annual_salary: str | None = None
    # 이 사이트에 대응 코드가 없어 못 건 역할. **조용히 빠지지 않게** 화면에 찍는다.
    missing_roles: list[str] = field(default_factory=list)

    @property
    def unsupported_employment_types(self) -> list[str]:
        """이 사이트가 못 거는 고용형태. **점핏은 전부 못 건다** — 필터 자체가 없다.

        실행할 때 화면에 찍는다. 조용히 무시하면 다른 사이트와 결과가 어긋난 이유를
        나중에 못 찾는다.
        """
        return [name for name in self.employment_types
                if name not in SUPPORTED_EMPLOYMENT_TYPES]


def load_config(env_path: Path | None = None) -> Config:
    env = read_env(env_path or ENV_PATH)

    job_ids, missing_roles = roles.resolve(env, ROLE_MAP)
    employment_types = csv_list(env.get("EMPLOYMENT_TYPES"))
    unknown = [name for name in employment_types if name not in KNOWN_ELSEWHERE]
    if unknown:
        raise ConfigError(
            "EMPLOYMENT_TYPES 에 모르는 값이 있습니다: %s\n"
            "  다른 사이트에서 쓰는 값: %s\n"
            "  점핏은 고용형태를 거르지 못합니다 — 적어도 무시하지만, 오타는 멈춥니다."
            % (unknown, ", ".join(sorted(KNOWN_ELSEWHERE))))

    education = strip_comment(env.get("EDUCATION"))
    if education and education not in EDUCATION_NAMES:
        raise ConfigError("EDUCATION 에 모르는 값이 있습니다: %r. 쓸 수 있는 값: %s"
                          % (education, ", ".join(EDUCATION_NAMES)))

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
