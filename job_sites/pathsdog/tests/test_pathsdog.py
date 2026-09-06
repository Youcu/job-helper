"""상세 수집 고리. 모듈을 이어 붙였을 때 무엇이 나가는가.

여기서 확인할 것은 **잃지 않는 것**이다 — 상세 하나가 터져도 나머지가 살아남는가,
차단되면 앞서 모은 것을 돌려주는가, 서버가 못 거른 둘(근무지·고용형태)을 우리가 거르는가.
"""
from __future__ import annotations

import pathsdog
from lib.client import BlockedError, ToolError

from .helpers import check, check_equal, detail_text


class FakeClient:
    pass


def _listing(job_id="1", **fields):
    row = {"id": job_id, "기업명": "회사%s" % job_id, "기술": "Python",
           "조건": "신입 | 근무지: 서울 | 정규직", "마감": "2026-09-30",
           "상세주소": "https://jobs.pathsdog.com/jobs/%s-x" % job_id}
    row.update(fields)
    return row


def _detail(place="서울 강남구", jobtype="정규직", stacks="java"):
    return ("📋 회사 - 공고\n[기본 정보]\n- 기술스택: %s\n- 경력: 신입\n"
            "- 근무지: %s\n- 고용형태: %s\n[일정]\n- 서류 마감: 2026-09-30\n"
            "[상세 내용]\n자격요건\nJava 3년\n" % (stacks, place, jobtype))


def _collect(listings, details, places=(), jobtypes=()):
    original = pathsdog.fetch_detail

    def fake(_client, job_id):
        value = details.get(job_id)
        if isinstance(value, Exception):
            raise value
        return value if value is not None else ""

    pathsdog.fetch_detail = fake
    try:
        return pathsdog._collect_details(FakeClient(), listings, list(places), list(jobtypes))
    finally:
        pathsdog.fetch_detail = original


def test_NORMAL_builds_rows():
    rows, _ai, stats = _collect([_listing("1"), _listing("2")],
                                {"1": _detail(), "2": _detail()})
    check_equal(len(rows), 2, "두 행")
    check(not stats["차단"], "차단 없음")
    check("Java" in rows[0]["기술스택"], rows[0]["기술스택"])


def test_NORMAL_real_detail_becomes_a_row():
    rows, _ai, _stats = _collect([_listing("3354")], {"3354": detail_text()})
    check_equal(len(rows), 1, "실제 응답으로도 행이 나와야 한다")
    check(rows[0]["지원자격"].strip(), "본문이 차야 한다")


def test_EXCEPTION_one_broken_detail_does_not_kill_the_run():
    rows, _ai, stats = _collect([_listing("1"), _listing("2"), _listing("3")],
                                {"1": _detail(), "2": ToolError("그런 공고 없음"),
                                 "3": _detail()})
    check_equal(len(rows), 2, "터진 하나만 빠진다")
    check_equal(stats["상세실패"], 1, "몇 건 실패했는지 세어야 한다")


def test_EXCEPTION_blocked_stops_but_keeps_earlier_rows():
    rows, _ai, stats = _collect([_listing("1"), _listing("2"), _listing("3")],
                                {"1": _detail(), "2": BlockedError("403"), "3": _detail()})
    check_equal(len(rows), 1, "차단 전까지 모은 것은 살린다")
    check(stats["차단"], "차단을 알려야 한다")


def test_EXCEPTION_listing_without_id_is_counted():
    rows, _ai, stats = _collect([_listing("1"), _listing(""), _listing("3")],
                                {"1": _detail(), "3": _detail()})
    check_equal(len(rows), 2, "번호 없는 것만 빠진다")
    check_equal(stats["번호없음"], 1, "몇 건 빠졌는지 세어야 한다")


def test_BOUNDARY_location_filter_runs_after_fetch():
    # MCP search_jobs 에 지역 파라미터가 없어서 여기서 거른다.
    rows, _ai, stats = _collect(
        [_listing("1"), _listing("2")],
        {"1": _detail(place="서울 강남구"), "2": _detail(place="부산 해운대구")},
        places=["서울"])
    check_equal(len(rows), 1, "서울만 남는다")
    check_equal(stats["근무지밖"], 1, "몇 건 뺐는지 세어야 한다")


def test_BOUNDARY_employment_filter_runs_after_fetch():
    # 서버가 값 하나만 받아서 `정규직,인턴` 중 하나를 잃는다. 그래서 여기서 거른다.
    rows, _ai, stats = _collect(
        [_listing("1"), _listing("2"), _listing("3")],
        {"1": _detail(jobtype="정규직"), "2": _detail(jobtype="계약직"),
         "3": _detail(jobtype="인턴")},
        jobtypes=["정규직", "인턴"])
    check_equal(len(rows), 2, "정규직과 인턴이 남는다")
    check_equal(stats["고용형태밖"], 1, "계약직만 빠진다")


def test_BOUNDARY_posting_without_skills_is_dropped():
    rows, _ai, stats = _collect([_listing("1", 기술="")],
                                {"1": _detail(stacks="").replace("자격요건\nJava 3년", "열정")})
    check_equal(rows, [], "판단할 재료가 없으면 행을 만들지 않는다")
    check_equal(stats["기술없음"], 1, "몇 건 빠졌는지 세어야 한다")


def test_BOUNDARY_empty_listing_list():
    rows, _ai, stats = _collect([], {})
    check_equal(rows, [], "빈 목록")
    check(not stats["차단"], "차단 아님")


def test_BOUNDARY_output_path_is_under_this_site():
    check_equal(pathsdog.OUTPUT.name, "pathsdog_post.csv", "산출물 이름")
    check("pathsdog" in str(pathsdog.OUTPUT.parent.parent), "다른 사이트 폴더에 쓰면 안 된다")
    check_equal(pathsdog.LOCK.parent, pathsdog.OUTPUT.parent, "자물쇠는 산출물 옆에 둔다")
