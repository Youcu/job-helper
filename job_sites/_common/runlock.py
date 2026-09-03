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
from contextlib import contextmanager
from pathlib import Path


class LockedError(Exception):
    """다른 실행이 이미 돌고 있다."""


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
