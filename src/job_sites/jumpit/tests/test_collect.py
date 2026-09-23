"""목록 페이지네이션.

이 모듈이 지키는 것 둘 —

    ① 총계를 **받은 항목 수**와 견준다. 한 공고가 여러 직무에 걸치면 총계에 여러 번
      세어지므로, 고유 수와 견주면 직무를 여럿 넣는 순간 늘 불일치라 신호로 못 쓴다.
    ② 총계는 **첫 값만 믿는다.** 끝 너머에서 0 으로 오기 때문이다.
"""
from __future__ import annotations

from lib.collect import Listings, fetch_listings

from .helpers import check, check_equal, empty_listing, listing_data


class FakeClient:
    """페이지마다 정해진 응답을 돌려준다."""

    def __init__(self, pages, total=None, end_total=0):
        self.pages = list(pages)
        self.total = total
        self.end_total = end_total          # 끝 너머에서 오는 총계 (실제로는 0)
        self.asked = []

    def get_json(self, path, params=None):
        page = int((params or {}).get("page", 1))
        self.asked.append(page)
        if page <= len(self.pages):
            body = self.pages[page - 1]
            if isinstance(body, Exception):
                raise body
            return {"totalCount": self.total if self.total is not None else 0,
                    "page": page, "positions": body, "emptyPosition": not body}
        return {"totalCount": self.end_total, "page": page,
                "positions": [], "emptyPosition": True}


def _p(pid):
    return {"id": pid, "title": "공고 %s" % pid}


def test_NORMAL_collects_every_page():
    client = FakeClient([[_p(1), _p(2)], [_p(3)]], total=3)
    result = fetch_listings(client, {}, page_size=2)
    check_equal([p["id"] for p in result.rows], [1, 2, 3], "세 건")
    check(result.matches_reported_total, "총계와 일치")
    check_equal(result.duplicates, 0, "중복 없음")


def test_NORMAL_real_listing_parses():
    data = listing_data()
    check(data["positions"], "픽스처에 공고가 있어야 한다")
    for p in data["positions"]:
        check(isinstance(p.get("id"), int), "id 가 숫자여야 한다: %r" % p.get("id"))
        check(bool(p.get("companyName")), "기업명이 비면 안 된다")


def test_NORMAL_stops_when_the_site_says_empty():
    # 사이트가 직접 "끝" 이라고 말해 준다. 가장 분명한 신호다.
    client = FakeClient([[_p(1)]], total=1)
    result = fetch_listings(client, {}, page_size=10)
    check_equal(len(result.rows), 1, "한 건")
    check("다 모았다" in result.stop_reason or "끝났다" in result.stop_reason,
          result.stop_reason)


def test_EXCEPTION_page_failure_keeps_earlier_pages():
    client = FakeClient([[_p(1)], RuntimeError("2페이지 끊김")], total=99)
    result = fetch_listings(client, {}, page_size=1)
    check_equal(len(result.rows), 1, "앞 페이지는 잃지 않는다")
    check("2페이지" in result.stop_reason, "왜 멈췄는지 남긴다: %r" % result.stop_reason)


def test_EXCEPTION_missing_total_is_none_not_zero():
    class NoTotal(FakeClient):
        def get_json(self, path, params=None):
            page = int((params or {}).get("page", 1))
            self.asked.append(page)
            body = self.pages[page - 1] if page <= len(self.pages) else []
            return {"positions": body, "emptyPosition": not body}
    result = fetch_listings(NoTotal([[_p(1)], []]), {}, page_size=1)
    check_equal(result.reported_total, None, "못 읽으면 None")
    check(not result.matches_reported_total, "모르면 일치라고 말하면 안 된다")


def test_BOUNDARY_total_is_read_only_once():
    # 결함이 될 뻔한 곳: 끝 너머에서 `totalCount` 가 **0** 으로 온다. 매번 덮어쓰면
    # 마지막에 0 이 남아 "다 모았다" 는 판정이 무너진다.
    check_equal(empty_listing()["totalCount"], 0, "픽스처가 그 사실을 담고 있어야 한다")
    check(empty_listing()["emptyPosition"], "끝 표시도 함께 온다")
    client = FakeClient([[_p(1)], [_p(2)]], total=2, end_total=0)
    result = fetch_listings(client, {}, page_size=1)
    check_equal(result.reported_total, 2, "첫 값을 지켜야 한다")


def test_BOUNDARY_total_is_compared_against_received_not_unique():
    # 한 공고가 여러 직무에 걸치면 총계에 여러 번 세어진다 (실측: 직무 21개에서 중복 10건).
    # 고유 수와 견주면 늘 불일치라 진짜 누락을 못 알아챈다.
    client = FakeClient([[_p(1), _p(2)], [_p(2), _p(3)]], total=4)
    result = fetch_listings(client, {}, page_size=2)
    check_equal(result.received, 4, "받은 항목은 넷")
    check_equal(len(result.rows), 3, "고유는 셋")
    check_equal(result.duplicates, 1, "중복 하나")
    check(result.matches_reported_total, "**그래도 총계는 일치여야 한다**")


def test_BOUNDARY_duplicate_is_kept_once():
    client = FakeClient([[_p(1), _p(1), _p(2)]], total=3)
    result = fetch_listings(client, {}, page_size=10)
    check_equal([p["id"] for p in result.rows], [1, 2], "같은 공고는 한 번만")


def test_BOUNDARY_empty_first_page():
    result = fetch_listings(FakeClient([[]], total=0), {}, page_size=10)
    check_equal(result.rows, [], "조건에 맞는 공고가 없을 수 있다")
    check_equal(result.received, 0, "받은 것도 없다")


def test_BOUNDARY_same_page_repeating_stops():
    # 페이지 번호가 무시되면 같은 조각이 끝없이 온다. 상한까지 돌면 안 된다.
    client = FakeClient([[_p(1)]] * 5, total=999)
    result = fetch_listings(client, {}, page_size=1, max_pages=5)
    check_equal(len(result.rows), 1, "새 공고가 없으면 멈춘다")
    check("새 공고가 없다" in result.stop_reason, result.stop_reason)


def test_BOUNDARY_max_pages_caps_runaway():
    client = FakeClient([[_p(n)] for n in range(1, 21)], total=999)
    result = fetch_listings(client, {}, page_size=1, max_pages=3)
    check_equal(len(client.asked), 3, "상한을 넘지 않는다")
    check("상한" in result.stop_reason, result.stop_reason)


def test_BOUNDARY_on_page_reports_arrived_not_unique():
    # 진행 표시는 **받은 수**를 세어야 사람이 보는 속도와 맞는다.
    seen = []
    client = FakeClient([[_p(1), _p(2)], [_p(2), _p(3)]], total=4)
    fetch_listings(client, {}, page_size=2, on_page=seen.append)
    check_equal(seen, [2, 2], "페이지마다 받은 수: %r" % seen)


def test_BOUNDARY_matches_reported_total_when_none():
    check(not Listings(received=0, reported_total=None).matches_reported_total,
          "총계를 모르면 일치라고 하지 않는다")


def test_NORMAL_fetch_detail_asks_the_right_path():
    from lib.collect import DETAIL_PATH, fetch_detail

    class Spy:
        def __init__(self):
            self.path = None

        def get_json(self, path, params=None):
            self.path = path
            return {"companyName": "회사"}

    spy = Spy()
    check_equal(fetch_detail(spy, 54799668), {"companyName": "회사"}, "상세를 그대로")
    check_equal(spy.path, DETAIL_PATH % 54799668, "상세 경로")
