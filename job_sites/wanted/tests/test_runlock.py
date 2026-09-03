"""실행 락."""
from __future__ import annotations

import tempfile
from pathlib import Path

from _common.runlock import LockedError, run_lock
from tests.helpers import assert_raises


def test_BOUNDARY_lock_owner_judgement():
    """락을 뺏어도 되는지 가리는 규칙. 틀리면 남이 도는 중에 끼어들거나, 영영 못 돈다."""
    import os

    from _common.runlock import _process_alive

    assert _process_alive(os.getpid()) is True        # 나는 살아 있다
    assert _process_alive(999999) is False            # 없는 프로세스 — 죽은 락이다
    assert _process_alive(0) is False                 # 0 은 프로세스 id 가 아니다
    assert _process_alive(-1) is False
    # 남의 프로세스(권한 없음)는 살아 있는 것으로 본다 — 뺏으면 안 된다.
    # pid 1 은 launchd/init 이라 늘 살아 있고 보통 권한이 없다.
    assert _process_alive(1) is True


def test_EXCEPTION_second_run_is_refused_while_one_is_running():
    """cron 이 겹쳐 두 실행이 읽고-고치고-쓰면 한쪽 결과가 조용히 사라진다."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        lock = Path(d) / "run.lock"
        with run_lock(lock):
            assert lock.exists()

            def second():
                with run_lock(lock):
                    pass

            assert_raises(LockedError, second)
        assert not lock.exists(), "끝나면 락을 놓아야 한다"


def test_EXCEPTION_stale_lock_from_a_dead_run_is_reclaimed():
    """죽은 실행이 남긴 락을 안 걷어내면 한 번 죽고 나서 영영 못 돈다."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        lock = Path(d) / "run.lock"
        lock.write_text("999999", encoding="utf-8")     # 없는 pid
        with run_lock(lock):
            pass
        assert not lock.exists()
        # 내용이 망가진 락도 마찬가지
        lock.write_text("pid 아님", encoding="utf-8")
        with run_lock(lock):
            pass
