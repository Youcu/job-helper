"""`.env` 를 읽어 검증된 수집 조건으로 만든다."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
# docs/api-notes.md 의 "../../../.env" 는 그 메모가 api/ 에 있을 때 기준이었다.
# wanted/ 기준으로는 두 단계 위다.
ENV_PATH = (ROOT / ".." / ".." / ".env").resolve()

# `.env` 는 짧은 이름으로 적고, API 에는 긴 키로 보낸다.
EMPLOYMENT_TYPE_KEYS = {
    "regular": "job.employment_type.regular",
    "contract": "job.employment_type.contract",
    "intern": "job.employment_type.intern",
}
DEFAULT_EMPLOYMENT_TYPES = ["regular", "intern"]


class ConfigError(Exception):
    pass


# 주석은 `#` 앞에 공백이 있을 때만이다. 그냥 `#` 으로 자르면 `C#` `F#` 이 잘린다.
_INLINE_COMMENT = re.compile(r"(?:^|\s)#")


def _strip_comment(raw: str | None) -> str:
    """값이 비어 있으면 python-dotenv 가 같은 줄 주석을 값으로 읽어 온다. 걷어낸다.

    `C#,Java` 처럼 값 자체에 `#` 이 든 경우를 자르지 않도록, 앞에 공백이 있는
    `#` 만 주석 시작으로 본다 (dotenv 관례와 같다).
    """
    if not raw:
        return ""
    match = _INLINE_COMMENT.search(raw)
    return (raw[: match.start()] if match else raw).strip()


def _csv_list(raw: str | None) -> list[str]:
    raw = _strip_comment(raw)
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _int_list(raw: str | None, label: str) -> list[int]:
    """정수 목록. 중복은 없앤다 — 같은 직군을 두 번 적어도 두 번 크롤하지 않는다."""
    values: list[int] = []
    for item in _csv_list(raw):
        try:
            number = int(item)
        except ValueError:
            raise ConfigError(f"{label} 에 숫자가 아닌 값이 있습니다: {item!r}")
        if number not in values:
            values.append(number)
    return values


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
    if not path.exists():
        raise ConfigError(f".env 를 찾을 수 없습니다: {path}")
    env = dotenv_values(path)

    job_group_ids = _int_list(env.get("JOB_GROUP_IDS"), "JOB_GROUP_IDS")
    if not job_group_ids:
        raise ConfigError(
            f"JOB_GROUP_IDS 가 비어 있습니다. 직군 코드를 comma 로 적어 주세요 ({path}). "
            "코드표는 README.md 의 '직군 코드' 표에 있습니다."
        )

    employment_types = _csv_list(env.get("EMPLOYMENT_TYPES")) or list(DEFAULT_EMPLOYMENT_TYPES)
    unknown = [t for t in employment_types if t not in EMPLOYMENT_TYPE_KEYS]
    if unknown:
        raise ConfigError(
            f"EMPLOYMENT_TYPES 에 모르는 값이 있습니다: {unknown}. "
            f"쓸 수 있는 값: {', '.join(EMPLOYMENT_TYPE_KEYS)}"
        )

    raw_yoe = _strip_comment(env.get("YOE")) or "-1"
    try:
        yoe = int(raw_yoe)
    except ValueError:
        raise ConfigError(f"YOE 는 정수여야 합니다 (신입=0, N년차=N, 전체=-1). 받은 값: {raw_yoe!r}")
    if yoe < -1 or yoe > 10:
        raise ConfigError(f"YOE 는 -1 ~ 10 사이여야 합니다. 받은 값: {yoe}")

    return Config(
        job_group_ids=job_group_ids,
        job_ids=_int_list(env.get("JOB_IDS"), "JOB_IDS"),
        employment_types=employment_types,
        yoe=yoe,
        home_locations=_csv_list(env.get("HOME_LOCATIONS")),
        tech_stacks=_csv_list(env.get("TECH_STACKS")),
        hope_annual_salary=_strip_comment(env.get("HOPE_ANNUAL_SALARY")) or None,
    )
