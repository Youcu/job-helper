"""`_common/staleness.py` — 낡은 입력으로 단계를 혼자 돌릴 때 묻는 일.

**틀리는 방향이 둘이고 값이 다르다.**

- 안 물으면 → 어제 데이터로 오늘 결과를 낸다 (**조용히 틀린 데이터**)
- 너무 자주 물으면 → 사람이 눈감고 `y` 를 친다 (물어도 안 읽는다)

그리고 세 번째가 가장 나쁘다 — **tty 가 아닌 자리에서 물으면 프로세스가 그대로 선다.**
cron 에 걸어 둔 실행이 멎으면 다음 실행과 겹쳐 락까지 물린다.

진짜 stdin 도 진짜 시계도 안 탄다 — `now`·`ask`·`stream`·`env` 를 인자로 넣는다.
"""
from __future__ import annotations

import io
import os
import tempfile
import time
from pathlib import Path

from _common import staleness as st
from tests.helpers import check, check_equal


def temp_dir() -> Path:
    return Path(tempfile.mkdtemp())


def _aged(tmp, seconds: float):
    """`seconds` 초 전에 만들어진 파일."""
    path = tmp / "입력.csv"
    path.write_text("x", encoding="utf-8")
    old = time.time() - seconds
    os.utime(path, (old, old))
    return path


def _ask(answer):
    return lambda _out: answer


# ─────────────────────────────── 일반 ───────────────────────────────

def test_NORMAL_fresh_input_is_not_questioned():
    path = _aged(temp_dir(), 60)
    out = io.StringIO()
    check(st.confirm(path, env={}, ask=_ask("n"), stream=out), "방금 것은 그냥 돈다")
    check_equal(out.getvalue(), "", "화면에 아무것도 안 찍는다")


def test_NORMAL_stale_input_asks_and_yes_proceeds():
    path = _aged(temp_dir(), st.STALE_AFTER + 60)
    out = io.StringIO()
    check(st.confirm(path, env={}, ask=_ask("y"), stream=out), "y 면 돈다")
    check("그때 걷은 데이터" in out.getvalue(), "무엇이 위험한지 말해야 한다")


def test_NORMAL_stale_input_stops_on_no():
    path = _aged(temp_dir(), st.STALE_AFTER + 60)
    check(not st.confirm(path, env={}, ask=_ask("n"), stream=io.StringIO()), "n 이면 멈춘다")


# ─────────────────────────────── 예외 ───────────────────────────────

def test_EXCEPTION_not_a_tty_stops_instead_of_hanging():
    """**가장 나쁜 실패.** tty 가 아닌데 `input()` 을 부르면 프로세스가 그대로 선다.

    cron 에 걸어 둔 실행이 멎으면 다음 실행과 겹쳐 락까지 물린다. 그래서 그 자리에서는
    묻지 않고 멈추고, `--yes` 를 주라고 말한다.
    """
    path = _aged(temp_dir(), st.STALE_AFTER + 60)
    out = io.StringIO()
    check(not st.confirm(path, env={}, ask=lambda _o: None, stream=out),
          "물어볼 수 없으면 멈춘다")
    check("--yes" in out.getvalue(), "어떻게 넘기는지 말해야 한다: %r" % out.getvalue())


def test_EXCEPTION_missing_file_is_not_this_functions_problem():
    # 입력이 아예 없는 것은 단계가 따로 다룬다. 여기서 막으면 메시지가 겹친다.
    check(st.confirm(temp_dir() / "없다.csv", env={}, ask=_ask("n")), "없으면 통과시킨다")


def test_EXCEPTION_empty_answer_is_no():
    # `[y/N]` 이라고 물었으니 그냥 엔터는 **아니오**다.
    path = _aged(temp_dir(), st.STALE_AFTER + 60)
    for answer in ("", "  ", "아니오", "Y다"):
        check(not st.confirm(path, env={}, ask=_ask(answer), stream=io.StringIO()),
              "%r 는 예가 아니다" % answer)


# ─────────────────────────────── 경계 ───────────────────────────────

def test_BOUNDARY_chain_never_asks():
    """오케스트레이터가 부를 때는 **절대** 묻지 않는다.

    방금 앞 단계가 만든 파일이다. 그리고 자식은 tty 를 못 잡으므로, 물으면 파이프라인
    전체가 멎는다.
    """
    path = _aged(temp_dir(), st.STALE_AFTER * 100)
    out = io.StringIO()
    check(st.confirm(path, env={st.CHAIN_ENV: "1"}, ask=_ask("n"), stream=out),
          "사슬 안이면 묻지 않고 통과")
    check_equal(out.getvalue(), "", "화면도 안 더럽힌다")


def test_BOUNDARY_yes_flag_beats_everything():
    path = _aged(temp_dir(), st.STALE_AFTER * 100)
    check(st.confirm(path, assume_yes=True, env={}, ask=_ask("n")), "--yes 가 이긴다")
    check(st.yes_given(["--yes"]), "플래그를 읽는다")
    check(not st.yes_given([]), "없으면 False")
    check(not st.yes_given(["--yes-please"]), "비슷한 이름에 안 속는다")


def test_BOUNDARY_the_line_is_exactly_stale_after():
    tmp = temp_dir()
    check(st.confirm(_aged(tmp, st.STALE_AFTER - 1), env={}, ask=_ask("n")),
          "선 바로 앞은 안 묻는다")
    check(not st.confirm(_aged(tmp, st.STALE_AFTER + 1), env={}, ask=_ask("n"),
                         stream=io.StringIO()),
          "선을 넘으면 묻는다")


def test_BOUNDARY_age_is_spoken_in_korean():
    check_equal(st.spoken(30), "방금", "1분 미만")
    check_equal(st.spoken(5 * 60), "5분 전", "분")
    check_equal(st.spoken(4 * 3600 + 13 * 60), "4시간 13분 전", "시간과 분")
    check_equal(st.spoken(3 * 3600), "3시간 전", "분이 0이면 안 붙인다")
    check_equal(st.spoken(26 * 3600), "1일 2시간 전", "하루를 넘기면")
    check_equal(st.spoken(48 * 3600), "2일 전", "시간이 0이면 안 붙인다")


def test_BOUNDARY_the_threshold_is_longer_than_one_collection():
    # 수집 한 바퀴가 실측 8~10분이다. 선이 그보다 짧으면 정상 흐름마다 물어
    # 사람이 눈감고 y 를 치게 된다.
    check(st.STALE_AFTER > 30 * 60,
          "수집 한 바퀴보다 넉넉해야 한다: %d초" % st.STALE_AFTER)
