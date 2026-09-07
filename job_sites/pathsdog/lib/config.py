""".env 를 읽어 Pathsdog 수집 조건으로 만든다.

읽는 방법(주석 처리·콤마 목록·셸 환경변수 차단)은 `_common/env.py` 에 있다.
여기에는 **Pathsdog 가 무엇을 요구하는가**만 둔다.

## 직무를 `skills` 로 넣는다

이 사이트는 **직무와 기술을 한 칸에 섞어 쓴다.** MCP 문서가 그렇게 쓰라고 명시한다 —
`"신입 백엔드" → experience_filter: "신입" + skills: ["Backend"]`. 그래서 이 사이트의
`tags/pathsdog_role_map.json` 만 값이 숫자가 아니라 **이름**이다 — `백엔드` → `Backend`.

`.env` 에 적는 것은 다른 사이트와 똑같이 `JOB_ROLES=백엔드` 다. 이 사이트에는 직무
코드라는 것이 없어서 대응표의 오른쪽이 이름일 뿐이다.

## 근무지는 서버가 못 거른다

MCP `search_jobs` 에 지역 파라미터가 없다 (화면에는 있는데 도구에는 없다). 받은 뒤
`record.matches_locations` 가 근무지 글로 거른다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from _common import roles
from _common.env import (ENV_PATH, ConfigError, csv_list, one_int, read_env,
                         strip_comment)

SITE = "pathsdog"
ROLE_MAP = Path(__file__).resolve().parent.parent / "tags" / "pathsdog_role_map.json"
# `.env` 의 짧은 이름 → 이 사이트의 고용형태 이름.
EMPLOYMENT_TYPE_NAMES = {
    "regular": "정규직", "contract": "계약직",
    "intern": "인턴", "freelance": "프리랜서",
}
KNOWN_ELSEWHERE = frozenset({"dispatch", "outsourced", "parttime"})

# 년차 → `experience_filter`. **서버가 정한 뜻을 그대로 따른다** —
# 주니어는 "1~3년 + 신입" 이라 신입을 포함한다.
EXPERIENCE_BANDS = [(0, 0, "신입"), (1, 3, "주니어"), (4, 5, "미들")]
EXPERIENCE_SENIOR = "시니어"

YOE_ALL = -1
YOE_MAX = 30


@dataclass
class Config:
    job_ids: list[str] = field(default_factory=list)      # 역할 이름 (`Backend` 등)
    employment_types: list[str] = field(default_factory=list)
    yoe: int = YOE_ALL
    education: str = ""
    home_locations: list[str] = field(default_factory=list)
    tech_stacks: list[str] = field(default_factory=list)
    hope_annual_salary: str | None = None
    # 이 사이트에 대응 코드가 없어 못 건 역할. **조용히 빠지지 않게** 화면에 찍는다.
    missing_roles: list[str] = field(default_factory=list)

    @property
    def employment_names(self) -> list[str]:
        return [EMPLOYMENT_TYPE_NAMES[name] for name in self.employment_types
                if name in EMPLOYMENT_TYPE_NAMES]

    @property
    def unsupported_employment_types(self) -> list[str]:
        """이 사이트에 없는 고용형태. 실행할 때 화면에 찍는다."""
        return [name for name in self.employment_types
                if name not in EMPLOYMENT_TYPE_NAMES]

    @property
    def experience_filter(self) -> str:
        """년차 → 서버가 아는 경력 이름. 전체면 빈 문자열."""
        if self.yoe < 0:
            return ""
        for low, high, name in EXPERIENCE_BANDS:
            if low <= self.yoe <= high:
                return name
        return EXPERIENCE_SENIOR


def load_config(env_path: Path | None = None) -> Config:
    env = read_env(env_path or ENV_PATH)

    job_ids, missing_roles = roles.resolve(env, ROLE_MAP)
    employment_types = csv_list(env.get("EMPLOYMENT_TYPES"))
    unknown = [name for name in employment_types
               if name not in EMPLOYMENT_TYPE_NAMES and name not in KNOWN_ELSEWHERE]
    if unknown:
        raise ConfigError(
            "EMPLOYMENT_TYPES 에 모르는 값이 있습니다: %s\n"
            "  다른 사이트에서 쓰는 값: %s\n"
            "  이 중 Pathsdog 가 거를 수 있는 것: %s"
            % (unknown, ", ".join(sorted(KNOWN_ELSEWHERE | set(EMPLOYMENT_TYPE_NAMES))),
               ", ".join(EMPLOYMENT_TYPE_NAMES)))

    return Config(
        job_ids=[code for code in job_ids],
        missing_roles=missing_roles,
        employment_types=employment_types,
        yoe=one_int(env.get("YOE"), "YOE (신입=0, N년차=N, 전체=-1)",
                    default=YOE_ALL, low=YOE_ALL, high=YOE_MAX),
        education=strip_comment(env.get("EDUCATION")),
        home_locations=csv_list(env.get("HOME_LOCATIONS")),
        tech_stacks=csv_list(env.get("TECH_STACKS")),
        hope_annual_salary=env.get("HOPE_ANNUAL_SALARY") or None,
    )
