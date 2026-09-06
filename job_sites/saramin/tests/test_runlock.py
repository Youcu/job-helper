"""실행 자물쇠와 그 종료 코드.

**`_common` 의 것을 여기서 시험한다.** 세 사이트가 함께 쓰는 코드라 어느 한 사이트에
붙여 두면, 그 사이트를 지웠을 때 시험도 같이 사라진다.

`ALREADY_RUNNING`(3)은 **오케스트레이터와 맺은 계약**이다. 여러 사이트를 병렬로 돌릴 때
이 값이 사이트마다 어긋나면 "이미 돌고 있다" 를 실패로 잘못 읽는다. 그래서 세 사이트가
각자 쓰던 일곱 줄을 `guarded()` 하나로 모았고, 그 값을 여기서 굳힌다.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from _common.runlock import ALREADY_RUNNING, LockedError, guarded, run_lock

from .helpers import check, check_equal


def _lock() -> Path:
    return Path(tempfile.mkdtemp()) / ".test.lock"


def test_NORMAL_guarded_passes_the_return_value_through():
    lock = _lock()
    check_equal(guarded(lock, lambda: 7), 7, "돌린 결과를 그대로 돌려줘야 한다")


def test_NORMAL_lock_is_released_after_the_run():
    lock = _lock()
    guarded(lock, lambda: 0)
    check_equal(guarded(lock, lambda: 0), 0, "앞 실행이 끝났으면 다시 들어갈 수 있어야 한다")


def test_EXCEPTION_guarded_returns_three_when_locked():
    lock = _lock()
    with run_lock(lock):
        ran = []
        check_equal(guarded(lock, lambda: ran.append(1) or 0), ALREADY_RUNNING,
                    "이미 돌고 있으면 물러난다")
        check_equal(ran, [], "**돌리지도 말아야 한다** — 겹쳐 돌면 한쪽 결과가 사라진다")


def test_EXCEPTION_lock_is_released_even_when_the_run_raises():
    # 터졌다고 자물쇠가 남으면 그 다음부터 영영 못 돈다.
    lock = _lock()

    def boom():
        raise RuntimeError("수집 중 사고")

    try:
        guarded(lock, boom)
    except RuntimeError:
        pass
    check_equal(guarded(lock, lambda: 0), 0, "사고 뒤에도 다시 들어갈 수 있어야 한다")


def test_EXCEPTION_nested_lock_raises_locked_error():
    lock = _lock()
    with run_lock(lock):
        try:
            with run_lock(lock):
                raise AssertionError("두 번째 실행이 들어와 버렸다")
        except LockedError:
            pass


def test_BOUNDARY_zero_is_a_real_exit_code():
    # `0` 이 거짓이라고 다른 값으로 바꾸면 정상 실행이 실패로 보인다.
    check_equal(guarded(_lock(), lambda: 0), 0, "0 은 값이다")


def test_BOUNDARY_already_running_code_is_three():
    # 오케스트레이터가 이 숫자에 기대고 있다. 바꾸면 세 사이트가 한꺼번에 어긋난다.
    check_equal(ALREADY_RUNNING, 3, "세 사이트가 함께 쓰는 값")
