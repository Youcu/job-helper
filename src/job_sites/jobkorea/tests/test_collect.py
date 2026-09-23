"""목록 파싱과 페이지 넘기기.

**총계 대조가 이 모듈의 핵심**이다. 조용히 적게 걷히는 것을 잡는 유일한 수단이라
`fetch_total` 이 못 읽었을 때 0 으로 속이지 않는 것까지 확인한다.
"""
from __future__ import annotations

from lib.collect import (Listings, fetch_listings, fetch_total, parse_listings)

from .helpers import check, check_equal, listing_fragment


class FakeClient:
    """페이지마다 정해진 조각을 돌려준다. 총계는 `_SearchCount` 로 따로 답한다."""

    def __init__(self, fragments, total="57"):
        self.fragments = list(fragments)
        self.total = total
        self.pages_asked = []

    def post_html(self, path, conditions, extra=None, *, referer=None):
        if path.endswith("_SearchCount/"):
            if isinstance(self.total, Exception):
                raise self.total
            return self.total
        page = int((extra or {}).get("Page", 1))
        self.pages_asked.append(page)
        return self.fragments[page - 1] if page <= len(self.fragments) else ""


def _item(gno, company="회사", title="제목", cells=("신입", "대졸", "서울"),
          summary="요약", deadline="~09/30", badge=""):
    return (
        '<tr class="devloopArea" data-gno="%s">'
        '<td class="tplCo"><a href="/co/1">%s</a></td>'
        '<td><div class="titBx">%s<strong> <a href="/Recruit/GI_Read/%s">%s</a></strong></div>'
        '<p class="dsc">%s</p>'
        '<p class="etc">%s</p></td>'
        '<td><span class="date">%s</span></td></tr>'
        % (gno, company, badge, gno, title,
           summary, "".join('<span class="cell">%s</span>' % c for c in cells), deadline))


def test_NORMAL_parses_every_field():
    rows = parse_listings(_item("111", "이데아텍㈜", "백엔드 개발자"))
    check_equal(len(rows), 1, "한 건")
    row = rows[0]
    check_equal(row["gno"], "111", "공고번호")
    check_equal(row["기업명"], "이데아텍㈜", "기업명")
    check_equal(row["제목"], "백엔드 개발자", "제목")
    check_equal(row["조건"], ["신입", "대졸", "서울"], "조건 셀")
    check_equal(row["마감일"], "~09/30", "마감일")


def test_NORMAL_real_fragment_yields_rows():
    rows = parse_listings(listing_fragment())
    check(len(rows) >= 3, "실제 조각에서 3건 이상 나와야 한다: %d" % len(rows))
    for row in rows:
        check(row["gno"].isdigit(), "공고번호가 숫자여야 한다: %r" % row["gno"])
        check(bool(row["기업명"]), "기업명이 비면 안 된다: %r" % row)
        check(bool(row["제목"]), "제목이 비면 안 된다: %r" % row)


def test_NORMAL_paginates_until_total_is_met():
    client = FakeClient([_item("1") + _item("2"), _item("3")], total="3")
    result = fetch_listings(client, {"duty": "1"})
    check_equal(len(result.rows), 3, "세 건")
    check_equal(client.pages_asked, [1, 2], "두 페이지만 물어본다")
    check(result.matches_reported_total, "총계와 일치")


def test_EXCEPTION_missing_total_is_none_not_zero():
    # 0 으로 속이면 "다 모았다" 고 판단해 1페이지에서 멈춘다.
    client = FakeClient([_item("1")], total="총 57건입니다")
    result = fetch_listings(client, {"duty": "1"})
    check_equal(result.reported_total, None, "못 읽으면 None")
    check(not result.matches_reported_total, "모르면 일치라고 말하면 안 된다")


def test_EXCEPTION_count_endpoint_failure_does_not_stop_collection():
    client = FakeClient([_item("1"), ""], total=RuntimeError("끊김"))
    result = fetch_listings(client, {"duty": "1"})
    check_equal(result.reported_total, None, "총계는 포기")
    check_equal(len(result.rows), 1, "그래도 목록은 걷는다")


def test_EXCEPTION_page_failure_keeps_earlier_pages():
    class Failing(FakeClient):
        def post_html(self, path, conditions, extra=None, *, referer=None):
            if path.endswith("_SearchCount/"):
                return "99"
            if int((extra or {}).get("Page", 1)) == 2:
                raise RuntimeError("2페이지 끊김")
            return _item("1")

    result = fetch_listings(Failing([]), {"duty": "1"})
    check_equal(len(result.rows), 1, "앞 페이지는 잃지 않는다")
    check("2페이지" in result.stop_reason, "왜 멈췄는지 남긴다: %r" % result.stop_reason)


def test_BOUNDARY_title_with_badge_between_titBx_and_strong():
    # 결함이었던 곳: 합격축하금 공고는 `titBx` 와 `<strong>` 사이에 배지가 낀다.
    # 붙어 있는 것만 받으면 그 공고의 제목이 통째로 빈다 — 57건 중 1건에서 실제로 그랬다.
    rows = parse_listings(_item("1", title="신입 개발자",
                               badge='<div class="celebrate-badge">축하금</div>'))
    check_equal(rows[0]["제목"], "신입 개발자", "배지가 껴도 제목을 읽어야 한다")


def test_BOUNDARY_condition_cells_vary_in_count():
    # 연봉이 있는 공고만 한 칸 더 붙는다. 위치로 읽으면 어긋난다.
    five = parse_listings(_item("1", cells=("신입", "대졸", "서울", "정규직", "기술")))
    six = parse_listings(_item("2", cells=("신입", "대졸", "서울", "정규직", "기술", "3,400만원")))
    check_equal(len(five[0]["조건"]), 5, "다섯 칸")
    check_equal(len(six[0]["조건"]), 6, "여섯 칸")


def test_BOUNDARY_duplicate_gno_across_pages_is_counted_once():
    client = FakeClient([_item("1") + _item("2"), _item("2") + _item("3")], total="3")
    result = fetch_listings(client, {"duty": "1"})
    check_equal([row["gno"] for row in result.rows], ["1", "2", "3"], "겹친 것은 한 번만")


def test_BOUNDARY_same_page_repeating_stops():
    # 페이지 번호가 무시되면 같은 조각이 끝없이 온다. 상한까지 돌면 안 된다.
    client = FakeClient([_item("1")] * 5, total="999")
    result = fetch_listings(client, {"duty": "1"}, max_pages=5)
    check_equal(len(result.rows), 1, "새 공고가 없으면 멈춘다")
    check("새 공고가 없다" in result.stop_reason, result.stop_reason)


def test_BOUNDARY_empty_first_page():
    client = FakeClient([""], total="0")
    result = fetch_listings(client, {"duty": "1"})
    check_equal(result.rows, [], "조건에 맞는 공고가 없을 수 있다")


def test_BOUNDARY_max_pages_caps_runaway():
    client = FakeClient([_item(str(n)) for n in range(1, 21)], total="999")
    result = fetch_listings(client, {"duty": "1"}, max_pages=3)
    check_equal(len(client.pages_asked), 3, "상한을 넘지 않는다")
    check("상한" in result.stop_reason, result.stop_reason)


def test_BOUNDARY_total_with_thousands_separator():
    check_equal(fetch_total(FakeClient([], total="1,234"), {}), 1234, "콤마가 든 총계")
    check_equal(fetch_total(FakeClient([], total="  57  "), {}), 57, "앞뒤 공백")
    check_equal(fetch_total(FakeClient([], total="0"), {}), 0, "0건도 값이다")


def test_BOUNDARY_matches_reported_total_when_none():
    check(not Listings(rows=[], reported_total=None).matches_reported_total,
          "총계를 모르면 일치라고 하지 않는다")
