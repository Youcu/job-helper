"""한 번에 한 실행만 돌게 한다.

파이프라인은 주기로 돈다. cron 이 겹쳐 두 실행이 같은 CSV 를 읽고-고치고-쓰면
나중에 끝난 쪽이 앞의 결과를 덮어써서 **한쪽 수집이 조용히 사라진다.**

    with run_lock(Path("csv/.wanted.lock")):
        ...

죽은 실행이 남긴 락은 스스로 걷어낸다 — 안 그러면 한 번 죽고 나서 영영 못 돈다.
락 파일에 pid 를 적어 두고 그 프로세스가 살아 있는지 본다.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path

# 다른 실행이 돌고 있어서 물러났다는 종료 코드. **오케스트레이터와 맺은 계약**이라
# 사이트마다 따로 두면 안 된다 — 한 곳이 어긋나도 알아채기 어렵다.
ALREADY_RUNNING = 3


class LockedError(Exception):
    """다른 실행이 이미 돌고 있다."""


def guarded(lock: Path, run) -> int:
    """자물쇠를 쥐고 `run()` 을 돌린다. 이미 돌고 있으면 `ALREADY_RUNNING`.

    세 사이트가 똑같은 일곱 줄을 각자 쓰고 있었다. 종료 코드가 계약인 이상 한 곳에서
    관리해야 한다 — 한 사이트만 다른 코드를 내면 오케스트레이터가 조용히 잘못 읽는다.
    """
    try:
        with run_lock(lock):
            return run()
    except LockedError as error:
        print("\n%s" % error, file=sys.stderr)
        return ALREADY_RUNNING


@contextmanager
def run_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        owner = _lock_owner(path)
        if owner is not None and _process_alive(owner):
            raise LockedError(
                f"다른 실행이 이미 돌고 있습니다 (pid {owner}, 락 {path}).\n"
                "  끝나기를 기다리거나, 그 실행이 죽은 게 확실하면 락 파일을 지우세요."
            )
        # 주인이 없는 락 — 죽은 실행이 남긴 것이다
        path.unlink(missing_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def _lock_owner(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True      # 남의 프로세스지만 살아 있다
    return True
