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
# 한 건마다 `claude -p` 가 뜬다 — 얇은 HTTP 호출이 아니라 **Claude Code 프로세스가 통째로**
# 뜨는 것이라, 수십 개를 동시에 띄우면 이 기계가 먼저 힘들어진다. 그리고 무엇이 됐든 막히면
# 동시에 던진 만큼이 한꺼번에 실패하는데, 이 단계는 "못 뽑으면 버린다" 라서 그 폭이 곧 위험이다.
#
# **처음에는 "분당 토큰 한도" 를 근거로 들었는데 그건 API 이야기였다.** `claude -p` 는
# 구독 계정으로 붙는다(OAuth). 실측에서 동시 4개로 103건을 돌려 최종 실패가 0건이었으므로,
# 4 는 안전한 기본값일 뿐 지켜야 할 상한이 아니다. `.env` 의 `CLAUDE_WORKER` 로 올려 잰다.
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
        workers=one_int(env.get("CLAUDE_WORKER"), "CLAUDE_WORKER",
                        default=WORKERS, low=1, high=WORKERS_MAX),
        timeout=one_int(env.get("IMAGE_TIMEOUT"), "IMAGE_TIMEOUT",
                        default=TIMEOUT, low=10, high=3600),
    )
