"""수집이 온전했는가의 판정. **`_common` 의 것을 여기서 시험한다** — 여섯 사이트가
함께 쓰는 코드라 어느 한 사이트에 붙여 두면 그 사이트를 지웠을 때 시험도 같이 사라진다.

실제로 있었던 일을 굳힌다. Pathsdog 의 상세 도구가 죽어 29건이 **전부** 실패했는데,
공고 하나의 실패를 견디는 코드가 전부의 실패도 똑같이 견뎌 **종료 코드 0** 을 냈다.
화면에는 `정상 · 0행` 이라고 찍혔다 — 사이트에 공고가 29건 있는데도.
"""
from __future__ import annotations

from _common.outcome import INCOMPLETE, incomplete

from .helpers import check, check_equal


def _stats(failed=0, missing_id=0):
    return {"상세실패": failed, "번호없음": missing_id, "기술없음": 0, "차단": False}


def test_NORMAL_rows_collected_is_a_good_run():
    check(not incomplete(_stats(failed=0), [{"URL": "u"}]), "다 걷었다")


def test_NORMAL_some_failed_but_something_was_collected():
    # 공고 하나가 실패했다고 실행 전체를 실패로 세면, 걷어 온 것이 버려진 것처럼 보인다.
    # 잃은 건수는 요약에 찍혀 사람이 본다.
    check(not incomplete(_stats(failed=5), [{"URL": "u"}] * 24), "하나라도 건졌으면 해낸 것이다")


def test_EXCEPTION_nothing_collected_and_details_were_lost():
    check(incomplete(_stats(failed=29), []),
          "남은 것이 없는데 잃은 것이 있으면, 이 실행만 보고는 알 수 없다")


def test_BOUNDARY_zero_rows_with_no_failures_is_normal():
    # 조건에 맞는 공고가 아예 없었거나, 받아 놓고 근무지·고용형태로 다 걸러졌다.
    # **없는 것을 실패로 세면 파이프라인이 멎는다.**
    check(not incomplete(_stats(failed=0), []), "잃은 것이 없으면 0행도 정상이다")


def test_BOUNDARY_one_survivor_among_many_failures_is_still_normal():
    # **비율로 자르지 않는다.** 어디서 자를지 근거가 없어서다.
    check(not incomplete(_stats(failed=28), [{"URL": "u"}]), "28건을 잃어도 하나 건졌다")


def test_BOUNDARY_last_survivor_filtered_out_is_incomplete():
    """결함이 될 뻔한 곳. **처음 규칙은 이걸 놓쳤다.**

    상세 29건 중 28건이 실패하고 남은 하나가 근무지 조건에 걸려 빠지면, `전부 실패`
    가 아니라서 종료 코드 0 이 나왔다 — 실제 실행에서 그렇게 한 번 새어 나갔다.
    저장한 행으로 판정하면 이 경우도 잡힌다.
    """
    check(incomplete(_stats(failed=28), []), "걸러져서 0행이 된 것도 마찬가지다")


def test_BOUNDARY_missing_id_alone_is_not_a_failure():
    # 공고번호가 없어 **아예 안 물어본** 것은 상세를 주는 쪽의 잘못이 아니다.
    check(not incomplete(_stats(failed=0, missing_id=29), []), "안 물어본 것은 잃은 것이 아니다")


def test_BOUNDARY_row_count_may_be_a_number():
    # 사이트마다 넘기는 것이 목록일 수도 개수일 수도 있다.
    check(incomplete(_stats(failed=3), 0), "개수 0")
    check(not incomplete(_stats(failed=3), 2), "개수 2")


def test_BOUNDARY_missing_keys_do_not_explode():
    # 사이트가 세는 항목이 조금씩 다르다. 없는 칸 때문에 실행이 죽으면 안 된다.
    check(not incomplete({}, []), "빈 stats 도 견딘다")
    check(not incomplete({}, None), "행이 None 이어도 견딘다")


def test_BOUNDARY_incomplete_matches_the_blocked_code():
    # 차단과 같은 코드다 — 둘 다 "여기까지밖에 못 걷었다" 이고, 오케스트레이터는
    # `2` 를 실패로 센다. 다른 코드를 내면 계약에 없는 값이 된다.
    check_equal(INCOMPLETE, 2, "차단이 내는 코드와 같아야 한다")
