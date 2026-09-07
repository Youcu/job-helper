"""이미지 판독 단계의 손잡이. **없어도 돈다.**

`.env` 는 여섯 사이트가 함께 쓰는 **검색 조건** 한 벌이고, 모델 이름과 동시 실행 수는
성격이 다르다. 그래서 기본값을 코드에 두고 `.env` 에 적혀 있을 때만 그것을 쓴다 —
검색 조건은 없으면 멈추지만(D-08) 이건 멈출 이유가 없다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from _common.env import ConfigError, one_int, read_env, strip_comment

MODEL = "sonnet"
# 잘라 주면 opus 와 결과가 글자까지 같고 비용은 2.5분의 1이다 (실측).
WORKERS = 4
# 1:1 은 안 한다. 한 건이 87k 토큰을 쓰므로 수십 개를 동시에 던지면 분당 한도에 걸리고,
# 걸리면 **한꺼번에** 실패한다. 하필 이 단계는 "못 뽑으면 버린다" 라서 위험이 크다.
TIMEOUT = 300
WORKERS_MAX = 64


@dataclass(frozen=True)
class Config:
    model: str
    workers: int
    timeout: int


def load_config(env_path: Path | None = None) -> Config:
    try:
        env = read_env(env_path)
    except ConfigError:
        # **`.env` 가 없어도 돈다.** `read_env` 는 없으면 예외를 던지는데, 그건 검색
        # 조건을 위한 규칙이다(D-08). 여기 셋은 운영 손잡이라 기본값으로 돌면 된다.
        env = {}
    return Config(
        model=strip_comment(env.get("IMAGE_MODEL")) or MODEL,
        workers=one_int(env.get("IMAGE_WORKERS"), "IMAGE_WORKERS",
                        default=WORKERS, low=1, high=WORKERS_MAX),
        timeout=one_int(env.get("IMAGE_TIMEOUT"), "IMAGE_TIMEOUT",
                        default=TIMEOUT, low=10, high=3600),
    )
