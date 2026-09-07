"""상세 수집 고리. 모듈을 이어 붙였을 때 무엇이 나가는가.

여기서 확인할 것은 **잃지 않는 것**이다 — 상세 하나가 터져도 나머지가 살아남는가,
차단되면 앞서 모은 것을 돌려주는가. 네트워크를 타지 않는다.
"""
from __future__ import annotations

import jumpit
from lib.client import BlockedError

from .helpers import check, check_equal, detail, position


class FakeClient:
    pass


def _pos(pid=1, **fields):
    row = {"id": pid, "companyName": "회사%s" % pid, "techStacks": ["java"],
           "closedAt": "2026-09-30T23:59:59", "newcomer": True}
    row.update(fields)
    return row


def _det(**fields):
    row = {"companyName": "회사", "qualifications": "Java 3년",
           "preferredRequirements": "Kotlin 우대", "location": "서울 강남구",
           "techStacks": [{"stack": "java"}], "newcomer": True}
    row.update(fields)
    return row


def _collect(positions, details):
    original = jumpit.fetch_detail

    def fake(_client, pid):
        value = details.get(pid)
        if isinstance(value, Exception):
            raise value
        return value if value is not None else {}

    jumpit.fetch_detail = fake
    try:
        return jumpit._collect_details(FakeClient(), positions)
    finally:
        jumpit.fetch_detail = original


def test_NORMAL_builds_rows():
    rows, stats = _collect([_pos(1), _pos(2)], {1: _det(), 2: _det()})
    check_equal(len(rows), 2, "두 행")
    check(not stats["차단"], "차단 없음")
    check("Java" in rows[0]["기술스택"], rows[0]["기술스택"])


def test_NORMAL_real_response_becomes_a_row():
    pos = position()
    rows, _stats = _collect([pos], {pos["id"]: detail()})
    check_equal(len(rows), 1, "실제 응답으로도 행이 나와야 한다")
    check(rows[0]["지원자격"].strip(), "본문이 차야 한다")


def test_EXCEPTION_one_broken_detail_does_not_kill_the_run():
    rows, stats = _collect([_pos(1), _pos(2), _pos(3)],
                                {1: _det(), 2: RuntimeError("끊김"), 3: _det()})
    check_equal(len(rows), 2, "터진 하나만 빠지고 나머지는 남는다")
    check_equal(stats["상세실패"], 1, "몇 건 실패했는지 세어야 한다")


def test_EXCEPTION_blocked_stops_but_keeps_earlier_rows():
    rows, stats = _collect([_pos(1), _pos(2), _pos(3)],
                                {1: _det(), 2: BlockedError("403"), 3: _det()})
    check_equal(len(rows), 1, "차단 전까지 모은 것은 살린다")
    check(stats["차단"], "차단을 알려야 한다")


def test_EXCEPTION_position_without_id_is_counted_not_crashed():
    rows, stats = _collect([_pos(1), _pos(""), _pos(3)], {1: _det(), 3: _det()})
    check_equal(len(rows), 2, "번호 없는 것만 빠진다")
    check_equal(stats["번호없음"], 1, "몇 건 빠졌는지 세어야 한다")


def test_BOUNDARY_posting_without_skills_is_dropped():
    # 기술도 없고 본문에서도 못 찾으면 판단할 재료가 없다.
    rows, stats = _collect([_pos(1, techStacks=[])],
                                {1: _det(techStacks=[], qualifications="열정 있는 분",
                                         preferredRequirements="", responsibility="")})
    check_equal(rows, [], "빈 행을 만들지 않는다")
    check_equal(stats["기술없음"], 1, "몇 건 빠졌는지 세어야 한다")


def test_BOUNDARY_listing_stacks_alone_are_enough():
    # 상세가 비어도 목록의 techStacks 가 있으면 행이 된다.
    rows, _stats = _collect([_pos(1, techStacks=["python"])], {1: {}})
    check_equal(len(rows), 1, "목록만으로도 행이 나온다")
    check("Python" in rows[0]["기술스택"], rows[0]["기술스택"])


def test_BOUNDARY_empty_position_list():
    rows, stats = _collect([], {})
    check_equal(rows, [], "빈 목록")
    check(not stats["차단"], "차단 아님")


def test_BOUNDARY_output_path_is_under_this_site():
    check_equal(jumpit.OUTPUT.name, "jumpit_post.csv", "산출물 이름")
    check("jumpit" in str(jumpit.OUTPUT.parent.parent), "다른 사이트 폴더에 쓰면 안 된다")
    check_equal(jumpit.LOCK.parent, jumpit.OUTPUT.parent, "자물쇠는 산출물 옆에 둔다")
