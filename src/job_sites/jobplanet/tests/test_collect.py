"""목록 페이지네이션과 자체 공고 가려내기.

이 모듈이 지키는 것 둘 —

    ① 총계 대조를 **훑은 수**로 한다. 우리가 자체 공고만 남기는 것은 우리 결정이라,
      남긴 수와 견주면 대조가 늘 불일치로 나와 신호로 못 쓴다.
    ② **1만 건 창**에 닿았는지 따로 본다. 창을 넘으면 총계까지 0 으로 와서,
      대조만 보면 "다 모았다" 고 잘못 판정한다.
"""
from __future__ import annotations

from lib.collect import (Listings, OWN_APPLY_TYPES, REQUEST_BUDGET, WINDOW_LIMIT,
                         fetch_listings, is_own_posting)

from .helpers import check, check_equal, listing_data


class FakeClient:
    """페이지마다 정해진 응답을 돌려준다."""

    def __init__(self, pages, total=None, budget_safe=False):
        self.pages = list(pages)
        self.total = total
        self.asked = []

    def get_json(self, path, params=None):
        page = int((params or {}).get("page", 1))
        self.asked.append(page)
        recruits = self.pages[page - 1] if page <= len(self.pages) else []
        if isinstance(recruits, Exception):
            raise recruits
        return {"total_count": self.total if self.total is not None else 0,
                "recruits": recruits}


def _posting(pid, apply_type="jobplanet"):
    return {"id": pid, "posting_apply_type": apply_type, "title": "공고 %s" % pid}


def test_NORMAL_keeps_only_own_postings():
    client = FakeClient([[_posting(1), _posting(2, "jobkorea_inlink"),
                          _posting(3, "outlink"), _posting(4, "jobkorea_outlink")]], total=4)
    result = fetch_listings(client, {}, page_size=10)
    check_equal([p["id"] for p in result.rows], [1, 3], "자체 공고만 남는다")
    check_equal(result.relayed, 2, "걸러낸 중계 수")
    check_equal(result.seen, 4, "훑은 수는 전부")


def test_NORMAL_real_listing_splits_own_and_relayed():
    data = listing_data()
    own = [p for p in data["recruits"] if is_own_posting(p)]
    relayed = [p for p in data["recruits"] if not is_own_posting(p)]
    check(own and relayed, "픽스처에 두 종류가 다 있어야 한다")
    for p in own:
        check(p["posting_apply_type"] in OWN_APPLY_TYPES, p["posting_apply_type"])


def test_NORMAL_paginates_until_total_is_seen():
    client = FakeClient([[_posting(1), _posting(2)], [_posting(3)]], total=3)
    result = fetch_listings(client, {}, page_size=2)
    check_equal(result.seen, 3, "세 건을 훑었다")
    check_equal(client.asked, [1, 2], "두 페이지만 물어본다")
    check(result.matches_reported_total, "총계와 일치")


def test_EXCEPTION_page_failure_keeps_earlier_pages():
    client = FakeClient([[_posting(1)], RuntimeError("2페이지 끊김")], total=99)
    result = fetch_listings(client, {}, page_size=1, budget=999)   # 예산은 여기서 볼 것이 아니다
    check_equal(len(result.rows), 1, "앞 페이지는 잃지 않는다")
    check("2페이지" in result.stop_reason, "왜 멈췄는지 남긴다: %r" % result.stop_reason)


def test_EXCEPTION_missing_total_is_none_not_zero():
    class NoTotal(FakeClient):
        def get_json(self, path, params=None):
            page = int((params or {}).get("page", 1))
            self.asked.append(page)
            return {"recruits": self.pages[page - 1] if page <= len(self.pages) else []}
    result = fetch_listings(NoTotal([[_posting(1)], []]), {}, page_size=1)
    check_equal(result.reported_total, None, "못 읽으면 None")
    check(not result.matches_reported_total, "모르면 일치라고 말하면 안 된다")


def test_BOUNDARY_total_is_compared_against_seen_not_kept():
    # 결함이 될 뻔한 곳: 자체 공고만 남긴 수로 견주면 늘 불일치라 신호로 못 쓴다.
    client = FakeClient([[_posting(1), _posting(2, "jobkorea_inlink")]], total=2)
    result = fetch_listings(client, {}, page_size=10)
    check_equal(len(result.rows), 1, "남긴 것은 하나")
    check(result.matches_reported_total, "그래도 총계는 일치여야 한다 (2건 다 훑었다)")


def test_BOUNDARY_window_limit_is_flagged():
    # 1만 건 창을 넘으면 공고도 총계도 0 으로 온다. 그냥 "빈 페이지" 로 보면
    # 다 모았다고 착각한다.
    pages = [[_posting(i)] for i in range(1, 3)]
    client = FakeClient(pages, total=99999)
    result = fetch_listings(client, {}, page_size=WINDOW_LIMIT, max_pages=4)
    check(result.hit_window_limit, "창에 닿았음을 알려야 한다: %r" % result.stop_reason)
    check(str(WINDOW_LIMIT) in result.stop_reason or "1만" in result.stop_reason
          or format(WINDOW_LIMIT, ",") in result.stop_reason, result.stop_reason)


def test_BOUNDARY_max_pages_caps_runaway():
    client = FakeClient([[_posting(n)] for n in range(1, 21)], total=20)
    result = fetch_listings(client, {}, page_size=1, max_pages=3, budget=999)
    check_equal(len(client.asked), 3, "상한을 넘지 않는다")
    check(result.hit_window_limit, "상한에 닿은 것도 창 문제로 알린다")


def test_BOUNDARY_duplicate_ids_across_pages_counted_once():
    client = FakeClient([[_posting(1), _posting(2)], [_posting(2), _posting(3)]], total=3)
    result = fetch_listings(client, {}, page_size=2)
    check_equal([p["id"] for p in result.rows], [1, 2, 3], "겹친 것은 한 번만")
    check_equal(result.seen, 3, "훑은 수도 고유 기준")


def test_BOUNDARY_same_page_repeating_stops():
    client = FakeClient([[_posting(1)]] * 5, total=5, budget_safe=True)
    result = fetch_listings(client, {}, page_size=1, max_pages=5, budget=999)
    check_equal(len(result.rows), 1, "새 공고가 없으면 멈춘다")
    check("새 공고가 없다" in result.stop_reason, result.stop_reason)


def test_BOUNDARY_empty_first_page():
    result = fetch_listings(FakeClient([[]], total=0), {}, page_size=10)
    check_equal(result.rows, [], "조건에 맞는 공고가 없을 수 있다")
    check(not result.hit_window_limit, "1페이지가 비면 창 문제가 아니다")


def test_BOUNDARY_all_relayed_is_not_an_error():
    # 조건에 따라 자체 공고가 하나도 없을 수 있다. 그것은 정상이지 실패가 아니다.
    client = FakeClient([[_posting(1, "jobkorea_inlink"), _posting(2, "jobkorea_inlink")]],
                        total=2)
    result = fetch_listings(client, {}, page_size=10)
    check_equal(result.rows, [], "남길 것이 없다")
    check_equal(result.relayed, 2, "몇 건을 걸렀는지는 남긴다")
    check(result.matches_reported_total, "총계 대조는 여전히 맞는다")


def test_BOUNDARY_matches_reported_total_when_none():
    check(not Listings(seen=0, reported_total=None).matches_reported_total,
          "총계를 모르면 일치라고 하지 않는다")


# ── 예산 게이트 ────────────────────────────────────────────────────────────
# 이 사이트는 한 번에 70~80요청쯤에서 403 을 맞는다. 반쯤 걷느니 아예 안 걷는다 —
# 절반만 든 CSV 는 "이 조건에 공고가 이만큼" 이라는 거짓을 만든다.


def test_NORMAL_narrow_condition_fits_budget():
    listings = Listings(rows=[{}] * 5, pages=2)
    check_equal(listings.planned_requests, 7, "목록 2 + 상세 5")
    check(listings.fits_budget(), "좁은 조건은 통과해야 한다")


def test_BOUNDARY_wide_condition_does_not_fit():
    # 실측 조건: 직무 6개 · 경력 전체 → 목록 13페이지 + 자체 공고 108건 = 121요청.
    # 실제로 64번째 상세에서 403 을 맞아 58/108 만 걷혔다.
    listings = Listings(rows=[{}] * 108, pages=13)
    check_equal(listings.planned_requests, 121, "목록 13 + 상세 108")
    check(not listings.fits_budget(), "넓은 조건은 걸러야 한다")


def test_BOUNDARY_budget_edge():
    check(Listings(rows=[{}] * (REQUEST_BUDGET - 1), pages=1).fits_budget(),
          "딱 예산이면 통과")
    check(not Listings(rows=[{}] * REQUEST_BUDGET, pages=1).fits_budget(),
          "하나만 넘어도 안 된다")


def test_BOUNDARY_list_alone_over_budget_stops_early():
    # 총계가 크면 목록만으로 예산을 넘긴다. 다 훑어 봐야 어차피 상세를 못 받으므로,
    # **못 쓸 목록을 긁느라 한도를 태우지 않는다.**
    client = FakeClient([[_posting(i) for i in range(100)]] * 200, total=100000)
    result = fetch_listings(client, {}, page_size=100, budget=10)
    check(result.over_budget, "예산 초과를 알려야 한다")
    check(not result.fits_budget(), "통과하면 안 된다")
    check_equal(len(client.asked), 1, "1페이지만 물어보고 멈춘다: %r" % client.asked)
    check("넓다" in result.stop_reason, result.stop_reason)


def test_BOUNDARY_over_budget_keeps_rows_empty_enough_to_be_safe():
    # 물러날 때 남은 행이 있어도 엔트리포인트가 쓰지 않는다. 그래도 여기서 확인해 둔다 —
    # `fits_budget` 이 False 면 그 행들은 **불완전한 절반**이다.
    client = FakeClient([[_posting(1)]] * 5, total=100000)
    result = fetch_listings(client, {}, page_size=1, budget=3)
    check(not result.fits_budget(), "불완전하면 통과시키지 않는다")


def test_BOUNDARY_budget_is_checked_before_the_window():
    # 예산(60요청)이 창(1만 건 = 100페이지)보다 **좁은** 제약이라 늘 먼저 걸린다.
    # 창 처리는 죽은 코드가 아니라, 예산을 넓혔을 때 남는 안전망이다.
    pages = [[_posting(page * 100 + n) for n in range(100)] for page in range(200)]
    tight = fetch_listings(FakeClient(pages, total=100000), {}, page_size=100)
    check(tight.over_budget, "기본 예산에서는 예산이 먼저 걸린다")
    check(not tight.hit_window_limit, "창까지 가지도 않는다")

    client = FakeClient(pages, total=100000)
    loose = fetch_listings(client, {}, page_size=100, budget=99999, max_pages=3)
    check(not loose.over_budget, "예산을 넓히면 안 걸린다")
    check_equal(len(client.asked), 3, "그때는 창·상한 쪽이 일한다")


def test_NORMAL_on_page_callback_reports_progress():
    # 진행 표시가 없으면 오래 도는 동안 멈춘 것과 구별이 안 된다.
    seen = []
    client = FakeClient([[_posting(1), _posting(2)], [_posting(3)]], total=3)
    fetch_listings(client, {}, page_size=2, on_page=seen.append)
    check_equal(seen, [2, 1], "페이지마다 걷은 수를 알려야 한다: %r" % seen)


def test_NORMAL_fetch_detail_asks_the_right_path():
    from lib.collect import DETAIL_PATH, fetch_detail

    class Spy:
        def __init__(self):
            self.path = None

        def get_json(self, path, params=None):
            self.path = path
            return {"name": "회사"}

    spy = Spy()
    check_equal(fetch_detail(spy, 1404269), {"name": "회사"}, "상세를 그대로 돌려준다")
    check_equal(spy.path, DETAIL_PATH % 1404269, "상세 경로")
