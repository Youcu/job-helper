"""단계를 **혼자 돌릴 때** 입력이 낡았으면 물어본다. 파이프라인 공통.

파이프라인을 단계로 쪼갠 이유 중 하나가 "특정 단계만 따로 돌릴 수 있다" 인데, 그 편의가
그대로 함정이기도 하다.

    python3 filter.py

입력인 `csv/merged_read.csv` 가 **어제 것이어도 그냥 돈다.** 그러면 어제 걷은 공고로 오늘
결과를 내는데, **터지지 않아서 알아채기 어렵다.** 실제로 이 저장소에서 그랬다 —
`merged_core.csv` 가 4시간 13분 전 수집 결과에서 나왔는데 파일 시각만 최신이었다.

    csv/merged_read.csv 는 4시간 13분 전 것입니다 (2026-09-11 16:33).
    지금 돌리면 **그때 걷은 데이터**로 결과를 냅니다.
    계속할까요? [y/N]

## 막지 않고 묻는다

중간 단계를 일부러 다시 돌리는 것은 **정상 용법**이다 — 낱말표를 고쳐 몇 건이 빠지는지
볼 때, 캐시를 지우고 다시 읽을 때. 그래서 오래됐다고 멈추지 않는다. **모르고 돌리는 일만**
없게 한다.

## 세 가지 경우를 가른다

    오케스트레이터가 부를 때   묻지 않는다. 방금 앞 단계가 만든 파일이다 (CHAIN_ENV)
    사람이 터미널에서 부를 때   묻는다
    tty 가 아닐 때 (cron·CI)   **묻지 않고 멈춘다.** 물으면 영영 매달린다

마지막이 중요하다. `stdin` 이 없는 자리에서 `input()` 을 부르면 프로세스가 그대로 선다.
cron 에 걸어 둔 실행이 그렇게 멎으면 다음 실행과 겹쳐 락까지 물린다. 그래서 그 자리에서는
**`--yes` 를 주라고 말하고 멈춘다** — 사람이 의도를 밝힌 것만 돈다.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# 오케스트레이터가 자식에게 "내가 방금 만든 파일이다" 를 알리는 환경변수.
# **값은 보지 않는다** — 있으면 사슬 안이다.
CHAIN_ENV = "PIPELINE_CHAIN"

# 이보다 오래된 입력이면 묻는다.
#
# 수집 한 바퀴가 실측 8~10분이다. 그러니 "방금 앞 단계를 돌리고 이어서 부르는" 정상 흐름은
# 길어야 몇십 분 안에 들어온다. 여섯 시간이 지났다면 **앞 단계를 안 돌린 것**이 거의 확실하다.
# 너무 짧게 잡으면 정상 용법(낱말표를 고쳐 다시 돌리기)마다 물어 사람이 눈감고 y 를 치게 된다.
STALE_AFTER = 6 * 60 * 60


def age_seconds(path: Path, now: float | None = None) -> float:
    """파일이 만들어진 지 몇 초 됐나. 파일이 없으면 `-1`."""
    if not path.exists():
        return -1.0
    return (now if now is not None else time.time()) - path.stat().st_mtime


def spoken(seconds: float) -> str:
    """사람이 읽을 나이. `4시간 13분 전` 처럼."""
    if seconds < 60:
        return "방금"
    minutes = int(seconds // 60)
    if minutes < 60:
        return "%d분 전" % minutes
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return "%d시간 %d분 전" % (hours, minutes) if minutes else "%d시간 전" % hours
    days, hours = divmod(hours, 24)
    return "%d일 %d시간 전" % (days, hours) if hours else "%d일 전" % days


def in_chain(env: dict | None = None) -> bool:
    """오케스트레이터가 부른 것인가."""
    return bool((env if env is not None else os.environ).get(CHAIN_ENV))


def confirm(path: Path, *, assume_yes: bool = False, now: float | None = None,
            env: dict | None = None, ask=None, stream=None) -> bool:
    """이 입력으로 계속해도 되는가.

    `ask` 와 `stream` 을 인자로 받는 이유는 **테스트가 진짜 stdin 을 안 건드리게** 하려는
    것이다. 기본은 `input` 과 `sys.stderr`.
    """
    out = stream if stream is not None else sys.stderr
    if assume_yes or in_chain(env):
        return True
    age = age_seconds(path, now)
    if age < 0 or age < STALE_AFTER:
        return True

    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime))
    print("\n%s 는 %s 것입니다 (%s)." % (path.name, spoken(age), when), file=out)
    print("  지금 돌리면 **그때 걷은 데이터**로 결과를 냅니다.", file=out)
    print("  최신 데이터로 하려면 먼저 수집을 돌리세요:", file=out)
    print("    python3 job_crawling_ochestrator.py", file=out)

    reader = ask if ask is not None else _tty_ask
    answer = reader(out)
    if answer is None:
        # 물어볼 수 없었다 — tty 가 아니거나, EOF·Ctrl-C 로 끊겼거나.
        # **이유가 무엇이든 넘어가는 길은 같으므로** 안내를 여기서 한 번만 찍는다.
        print("  그래도 이 데이터로 돌리려면 `--yes` 를 주세요.", file=out)
        return False
    return answer.strip().lower() in ("y", "yes")


def _tty_ask(out) -> str | None:
    """터미널이면 묻고, 아니면 `None`. **cron·CI 에서 매달리지 않게 한다.**"""
    if not sys.stdin or not sys.stdin.isatty():
        print("  터미널이 아니라 물어볼 수 없습니다 — 멈춥니다.", file=out)
        return None
    try:
        return input("  계속할까요? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print("", file=out)
        return None


def yes_given(argv: list[str] | None = None) -> bool:
    """명령줄에 `--yes` 가 있는가. 단계들이 같은 이름을 쓰도록 여기 둔다.

    `wanted` 같은 흔한 이름을 안 쓴다 — `core_stack.py` 에는 이미 그 이름의 지역 변수가
    있어서(원하는 기술 목록) 조용히 가려진다.
    """
    return "--yes" in (argv if argv is not None else sys.argv[1:])
