"""`.env` 를 읽는다. 사이트 공통.

사이트마다 읽을 항목은 다르지만 **읽는 방법은 같다.** 주석 처리, 콤마 목록, 정수 목록,
그리고 "셸 환경변수가 새어 들지 않게" 하는 규칙이 같다. 사이트마다 베끼면 같은 함정을
사이트 수만큼 다시 밟는다 — 실제로 `C#` 이 주석 처리에 잘려 나가는 결함을 겪었다.

## 항목 이름 규칙

**뜻이 같으면 이름도 같다.** `YOE` `HOME_LOCATIONS` `TECH_STACKS` `HOPE_ANNUAL_SALARY`
는 사이트가 달라도 같은 것을 뜻하므로 사이트마다 다른 이름을 붙이지 않는다.

**직무도 이름으로 적는다.** `JOB_ROLES=백엔드,웹` 하나를 여섯 사이트가 함께 쓰고,
각 사이트가 자기 `tags/<사이트>_role_map.json` 으로 코드를 찾는다 (`_common/roles.py`).

전에는 사이트마다 코드를 따로 적게 했다 — `WANTED_JOB_IDS=872`, `SARAMIN_JOB_IDS=84`.
코드 체계가 사이트마다 달라 어쩔 수 없다고 봤는데, **사람이 여섯 벌을 맞춰 적는 쪽이
더 위험했다.** 하나를 안 적으면 그 사이트가 남의 코드를 받아 엉뚱한 것을 긁는데
예외도 안 나고 결과도 나온다. 실제로 그렇게 만들었다가 고쳤다.

이름은 그 함정이 없다 — `백엔드` 는 어느 사이트에서도 `백엔드` 다. 모르는 이름이면
멈추고(`RoleError`), 그 사이트에 없는 직무면 **무엇을 못 걸었는지 화면에 찍는다.**
사이트마다 다른 항목을 두던 시절의 `site_key()` 는 쓸 곳이 없어져 지웠다.
"""
from __future__ import annotations

import re
from pathlib import Path

from dotenv import dotenv_values

# `job_sites/_common/env.py` → 저장소 뿌리
ENV_PATH = (Path(__file__).resolve().parent.parent.parent / ".env").resolve()


class ConfigError(Exception):
    """`.env` 가 없거나 값이 말이 안 될 때. 메시지에 **어느 항목이 왜** 인지 적는다."""


# 주석은 `#` 앞에 공백이 있을 때만이다. 그냥 `#` 으로 자르면 `C#` `F#` 이 잘린다.
_INLINE_COMMENT = re.compile(r"(?:^|\s)#")


def read_env(path: Path | None = None) -> dict[str, str]:
    """`.env` **파일만** 읽는다.

    `load_dotenv()` 는 값을 `os.environ` 에 심는다. 그러면 `.env` 에 줄이 없는 항목이
    셸 환경변수에서 조용히 새어 든다 — 근무지를 안 적었는데 셸에 `HOME_LOCATIONS=부산`
    이 있으면 부산 공고를 긁는다. 그래서 환경을 안 건드리는 `dotenv_values()` 를 쓴다.
    """
    target = path or ENV_PATH
    if not target.exists():
        raise ConfigError(
            ".env 를 찾을 수 없습니다: %s\n"
            "  민감 정보를 담는 파일이라 저장소에 넣지 않습니다. 예시 파일도 두지 않습니다.\n"
            "  필요한 항목은 각 사이트의 README.md 에 적혀 있습니다." % target)
    return dict(dotenv_values(target))




def strip_comment(raw: str | None) -> str:
    """값 뒤에 붙은 같은 줄 주석을 걷어낸다.

    값이 비어 있으면 python-dotenv 가 같은 줄 주석을 값으로 읽어 온다.
    `C#,Java` 처럼 값 자체에 `#` 이 든 것을 자르지 않도록, **앞에 공백이 있는 `#`** 만
    주석 시작으로 본다 (dotenv 관례와 같다).
    """
    if not raw:
        return ""
    match = _INLINE_COMMENT.search(raw)
    return (raw[:match.start()] if match else raw).strip()


def csv_list(raw: str | None) -> list[str]:
    """콤마로 나눈 목록. 빈 칸은 버리고 순서와 중복은 그대로 둔다."""
    text = strip_comment(raw)
    return [item.strip() for item in text.split(",") if item.strip()] if text else []


def int_list(raw: str | None, label: str) -> list[int]:
    """정수 목록. 중복은 없앤다 — 같은 코드를 두 번 적어도 두 번 크롤하지 않는다."""
    values: list[int] = []
    for item in csv_list(raw):
        try:
            number = int(item)
        except ValueError:
            raise ConfigError("%s 에 숫자가 아닌 값이 있습니다: %r" % (label, item))
        if number not in values:
            values.append(number)
    return values


def one_int(raw: str | None, label: str, *, default: int,
            low: int, high: int) -> int:
    """범위를 검사한 정수 하나. 범위를 벗어나면 조용히 자르지 않고 알린다."""
    text = strip_comment(raw)
    if not text:
        return default
    try:
        number = int(text)
    except ValueError:
        raise ConfigError("%s 는 정수여야 합니다. 받은 값: %r" % (label, text))
    if not low <= number <= high:
        raise ConfigError("%s 는 %d ~ %d 사이여야 합니다. 받은 값: %d"
                          % (label, low, high, number))
    return number
