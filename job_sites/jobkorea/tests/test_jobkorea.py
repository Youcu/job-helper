"""엔트리포인트. 모듈을 다 이어 붙였을 때 무엇이 나가는가.

여기서 확인할 것은 **잃지 않는 것**이다 — 상세 하나가 터져도 나머지가 살아남는가,
차단되면 앞서 모은 것을 저장하고 나가는가, 겹쳐 돌지 않는가.
네트워크를 타지 않는다 — 클라이언트와 수집 함수를 가짜로 바꿔 넣는다.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import jobkorea
from lib.client import BlockedError
from lib.collect import Listings

from .helpers import body_html, check, check_equal, detail, img


class FakeClient:
    pass


def _listing(gno="49911986", **fields):
    row = {"gno": gno, "기업명": "회사%s" % gno, "제목": "백엔드 개발자",
           "조건": ["신입", "대졸", "서울"], "마감일": "~09/30"}
    row.update(fields)
    return row


def _patch(monkey: dict):
    """`jobkorea` 모듈의 이름들을 바꿔 끼우고, 되돌릴 함수를 준다."""
    original = {name: getattr(jobkorea, name) for name in monkey}
    for name, value in monkey.items():
        setattr(jobkorea, name, value)
    return lambda: [setattr(jobkorea, name, value) for name, value in original.items()]


def _collect(listings, details, bodies):
    restore = _patch({
        "fetch_detail": lambda _client, gno: _raise_or(details.get(gno, "")),
        "fetch_body": lambda _client, gno: _raise_or(bodies.get(gno, "")),
    })
    try:
        return jobkorea._collect_details(FakeClient(), listings)
    finally:
        restore()


def _raise_or(value):
    if isinstance(value, Exception):
        raise value
    return value


def test_NORMAL_builds_rows_from_listings():
    rows, stats = _collect(
        [_listing("1"), _listing("2")],
        {"1": detail("49911986"), "2": detail("49911986")},
        {"1": "<p>Python Django AWS</p>", "2": "<p>Java Spring</p>"})
    check_equal(len(rows), 2, "두 행")
    check(not stats["차단"], "차단 없음")
    check("Python" in rows[0]["기술스택"], rows[0]["기술스택"])


def test_NORMAL_image_body_leaves_urls_not_skills():
    rows, stats = _collect(
        [_listing("1")], {"1": ""},
        {"1": img("https://file1.jobkorea.co.kr/Mng/2026/9/a.png")})
    check_equal(stats["그림본문"], 1, "그림 본문으로 세어야 한다")
    check_equal(stats["그림대기"], 1, "주소를 남겼다고 세어야 한다")
    check(rows[0]["기술스택"].startswith("http"), rows[0]["기술스택"])


def test_NORMAL_short_text_with_image_still_leaves_urls():
    # 글이 조금 있지만 기술 이름이 하나도 안 잡히는 공고. 그림 주소가 유일한 단서다.
    rows, _stats = _collect(
        [_listing("1")], {"1": ""},
        {"1": "<p>함께 성장할 분을 찾습니다</p>" + img("https://a.co/1.png")})
    check_equal(len(rows), 1, "버리면 안 된다")
    check(rows[0]["기술스택"].startswith("http"), rows[0]["기술스택"])


def test_EXCEPTION_one_broken_detail_does_not_kill_the_run():
    rows, _stats = _collect(
        [_listing("1"), _listing("2"), _listing("3")],
        {"1": "", "2": RuntimeError("끊김"), "3": ""},
        {"1": "<p>Python</p>", "3": "<p>Java</p>"})
    check_equal(len(rows), 2, "터진 하나만 빠지고 나머지는 남는다")


def test_EXCEPTION_blocked_stops_but_keeps_earlier_rows():
    # 결함이었던 곳(사람인): 차단되면 앞서 모은 것을 통째로 버렸다.
    rows, stats = _collect(
        [_listing("1"), _listing("2"), _listing("3")],
        {"1": "", "2": BlockedError("403"), "3": ""},
        {"1": "<p>Python</p>", "3": "<p>Java</p>"})
    check_equal(len(rows), 1, "차단 전까지 모은 것은 살린다")
    check(stats["차단"], "차단을 알려야 한다")


def test_EXCEPTION_listing_without_gno_is_counted_not_crashed():
    rows, stats = _collect(
        [_listing("1"), _listing(""), _listing("3")],
        {"1": "", "3": ""}, {"1": "<p>Python</p>", "3": "<p>Java</p>"})
    check_equal(len(rows), 2, "번호 없는 것만 빠진다")
    check_equal(stats["번호없음"], 1, "몇 건 빠졌는지 세어야 한다")


def test_BOUNDARY_posting_with_neither_skills_nor_images_is_dropped():
    # 기술도 그림도 없으면 판단할 재료가 아무것도 없다.
    rows, stats = _collect(
        [_listing("1")], {"1": ""}, {"1": "<p>%s</p>" % ("경영 지원 인재풀 등록 " * 40)})
    check_equal(rows, [], "빈 행을 만들지 않는다")
    check_equal(stats["기술없음"], 1, "몇 건 빠졌는지 세어야 한다")


def test_BOUNDARY_decoration_only_body_is_not_a_pending_image():
    # 편집기 장식뿐이면 나중 단계가 읽어 봐야 아무것도 없다.
    rows, stats = _collect(
        [_listing("1")], {"1": ""},
        {"1": img("http://i.jobkorea.kr/content/images/yocruit/gen/hd_req.png")})
    check_equal(rows, [], "장식만 있는 공고는 남길 것이 없다")
    check_equal(stats["그림대기"], 0, "장식을 대기로 세면 안 된다")


def test_BOUNDARY_empty_listing_list():
    rows, stats = _collect([], {}, {})
    check_equal(rows, [], "빈 목록")
    check(not stats["차단"], "차단 아님")


def test_BOUNDARY_run_lock_blocks_a_second_run():
    # 겹쳐 돌면 두 실행이 같은 CSV 를 읽고-고치고-써서 한쪽 결과가 조용히 사라진다.
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
    check_equal(jobkorea.OUTPUT.name, "jobkorea_post.csv", "산출물 이름")
    check("jobkorea" in str(jobkorea.OUTPUT.parent.parent), "다른 사이트 폴더에 쓰면 안 된다")
    check_equal(jobkorea.LOCK.parent, jobkorea.OUTPUT.parent, "자물쇠는 산출물 옆에 둔다")
