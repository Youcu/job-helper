"""실행 락."""
from __future__ import annotations

import tempfile
from pathlib import Path

from _common.runlock import ALREADY_RUNNING, LockedError, run_lock
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


def test_BOUNDARY_already_running_code_comes_from_the_contract():
    """**종료 코드는 오케스트레이터와 맺은 계약**이라 한 곳에서만 정한다.

    전에는 `wanted` 만 `run_lock()` 을 펼쳐 쓰고 `return 3` 을 손으로 적었다. 그러면
    `ALREADY_RUNNING` 을 바꿨을 때 **네 사이트는 따라가고 `wanted` 만 옛 값에 남는다** —
    예외도 안 나고 화면에 이상한 뜻만 찍힌다.

    `wanted` 가 맨 먼저 만들어졌고 통합 커밋(`b7e8437`)이 두 사이트만 옮기면서 빠졌다.
    """
    import wanted

    with tempfile.TemporaryDirectory() as d:
        saved, wanted.LOCK = wanted.LOCK, Path(d) / "run.lock"
        ran = []
        try:
            with run_lock(wanted.LOCK):
                wanted._run, saved_run = lambda: ran.append(1) or 0, wanted._run
                try:
                    code = wanted.main()
                finally:
                    wanted._run = saved_run
        finally:
            wanted.LOCK = saved
    assert code == ALREADY_RUNNING, code      # 손으로 적은 숫자가 아니라 계약값
    assert ran == [], "**남이 도는 중에는 일을 시작하면 안 된다**"
