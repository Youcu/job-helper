"""엔트리포인트. 모듈을 다 이어 붙였을 때 무엇이 나가는가.

여기서 확인할 것은 **잃지 않는 것**이다 — 상세 하나가 터져도 나머지가 살아남는가,
차단되면 앞서 모은 것을 저장하고 나가는가, 겹쳐 돌지 않는가.
네트워크를 타지 않는다 — 수집 함수를 가짜로 바꿔 넣는다.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import jobplanet
from lib.client import BlockedError
from lib.config import Config

from .helpers import check, check_equal, own_detail


class FakeClient:
    pass


def _posting(pid=1, **fields):
    row = {"id": pid, "posting_apply_type": "jobplanet",
           "company": {"name": "회사%s" % pid}, "end_at": "2026-09-30"}
    row.update(fields)
    return row


def _detail(**fields):
    row = {"name": "회사", "end_at": "2026.09.30", "location": "서울 강남구 테헤란로",
           "required_qualification": "Java 3년", "skills": ["java"],
           "recruitment_text": ["신입"]}
    row.update(fields)
    return row


def _collect(postings, details, config=None):
    original = jobplanet.fetch_detail

    def fake(_client, pid):
        value = details.get(pid)
        if isinstance(value, Exception):
            raise value
        return value if value is not None else {}

    jobplanet.fetch_detail = fake
    try:
        return jobplanet._collect_details(FakeClient(), postings,
                                          config or Config(job_ids=[11904]))
    finally:
        jobplanet.fetch_detail = original


def test_NORMAL_builds_rows():
    rows, stats = _collect([_posting(1), _posting(2)],
                                {1: _detail(), 2: _detail(skills=["python"])})
    check_equal(len(rows), 2, "두 행")
    check(not stats["차단"], "차단 없음")
    check("Java" in rows[0]["기술스택"], rows[0]["기술스택"])


def test_NORMAL_real_detail_becomes_a_row():
    rows, _stats = _collect([_posting(1404269)], {1404269: own_detail()})
    check_equal(len(rows), 1, "실제 응답으로도 행이 나와야 한다")
    check(rows[0]["지원자격"].strip(), "본문이 차야 한다")


def test_EXCEPTION_one_broken_detail_does_not_kill_the_run():
    rows, _stats = _collect(
        [_posting(1), _posting(2), _posting(3)],
        {1: _detail(), 2: RuntimeError("끊김"), 3: _detail()})
    check_equal(len(rows), 2, "터진 하나만 빠지고 나머지는 남는다")


def test_EXCEPTION_blocked_stops_but_keeps_earlier_rows():
    rows, stats = _collect(
        [_posting(1), _posting(2), _posting(3)],
        {1: _detail(), 2: BlockedError("403"), 3: _detail()})
    check_equal(len(rows), 1, "차단 전까지 모은 것은 살린다")
    check(stats["차단"], "차단을 알려야 한다")


def test_EXCEPTION_posting_without_id_is_counted_not_crashed():
    rows, stats = _collect([_posting(1), _posting(""), _posting(3)],
                                {1: _detail(), 3: _detail()})
    check_equal(len(rows), 2, "번호 없는 것만 빠진다")
    check_equal(stats["번호없음"], 1, "몇 건 빠졌는지 세어야 한다")


def test_BOUNDARY_posting_without_skills_is_dropped():
    rows, stats = _collect([_posting(1)],
                                {1: _detail(skills=[], required_qualification="열정 있는 분")})
    check_equal(rows, [], "판단할 재료가 없으면 행을 만들지 않는다")
    check_equal(stats["기술없음"], 1, "몇 건 빠졌는지 세어야 한다")


def test_BOUNDARY_location_filter_runs_after_fetch():
    # 지역 코드가 시도까지라 서버에서 못 거른 것을 여기서 거른다.
    config = Config(job_ids=[11904], home_locations=["성남시"])
    rows, stats = _collect(
        [_posting(1), _posting(2)],
        {1: _detail(location="경기 성남시 분당구 판교로"),
         2: _detail(location="경기 수원시 영통구")}, config)
    check_equal(len(rows), 1, "성남만 남는다")
    check_equal(stats["근무지밖"], 1, "몇 건 뺐는지 세어야 한다")


def test_BOUNDARY_no_location_condition_keeps_everything():
    config = Config(job_ids=[11904], home_locations=[])
    rows, stats = _collect([_posting(1), _posting(2)],
                                {1: _detail(location="부산 해운대구"),
                                 2: _detail(location="제주 제주시")}, config)
    check_equal(len(rows), 2, "조건이 없으면 전부 남는다")
    check_equal(stats["근무지밖"], 0, "거른 것 없음")


def test_BOUNDARY_body_missing_is_noted_but_kept():
    # 자체 공고인데 본문이 빈 경우. 기술이 있으면 행은 만들되 세어는 둔다.
    rows, stats = _collect([_posting(1)],
                                {1: _detail(required_qualification=None,
                                            preferred_skill=None)})
    check_equal(len(rows), 1, "기술이 있으면 남긴다")
    check_equal(stats["본문없음"], 1, "본문이 빈 것을 세어야 한다")


def test_BOUNDARY_empty_posting_list():
    rows, stats = _collect([], {})
    check_equal(rows, [], "빈 목록")
    check(not stats["차단"], "차단 아님")


def test_BOUNDARY_run_lock_blocks_a_second_run():
    from _common.runlock import LockedError, run_lock
    lock = Path(tempfile.mkdtemp()) / ".test.lock"
    with run_lock(lock):
        try:
            with run_lock(lock):
                raise AssertionError("두 번째 실행이 들어와 버렸다")
        except LockedError:
            pass
    with run_lock(lock):        # 앞 실행이 끝났으면 다시 들어갈 수 있어야 한다
        pass


def test_BOUNDARY_output_path_is_under_this_site():
    check_equal(jobplanet.OUTPUT.name, "jobplanet_post.csv", "산출물 이름")
    check("jobplanet" in str(jobplanet.OUTPUT.parent.parent), "다른 사이트 폴더에 쓰면 안 된다")
    check_equal(jobplanet.LOCK.parent, jobplanet.OUTPUT.parent, "자물쇠는 산출물 옆에 둔다")
