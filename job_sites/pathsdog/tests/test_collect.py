"""MCP 응답 글에서 공고를 읽어 내고 offset 으로 페이지를 넘긴다.

**응답이 JSON 이 아니라 글이라 개수 대조가 유일한 안전망이다.** 서버가 첫 줄에
`이번 페이지 N개 채용공고:` 라고 말해 주므로, 우리가 `[ID:n]` 으로 읽어 낸 개수를
그것과 매번 견준다 — 서식이 바뀌면 조용히 적게 읽히는데 그때 여기서 드러난다.
"""
from __future__ import annotations

from lib.collect import (Listings, fetch_listings, has_next_page, parse_listing,
                         reported_count)

from .helpers import check, check_equal, detail_text, empty_text, listing_text


class FakeClient:
    """묶음마다 정해진 글을 돌려준다."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.asked = []

    def call_tool(self, name, arguments):
        self.asked.append(arguments.get("offset", 0))
        index = len(self.asked) - 1
        page = self.pages[index] if index < len(self.pages) else "검색 결과가 없습니다."
        if isinstance(page, Exception):
            raise page
        return page


def _page(ids, *, said=None, more=False):
    said = len(ids) if said is None else said
    lines = ["이번 페이지 %d개 채용공고:" % said]
    if more:
        lines.append("다음 페이지: offset=%d 으로 재검색" % (len(ids)))
    for i in ids:
        lines += ["[ID:%d] 회사%d - 공고%d" % (i, i, i),
                  "  기술: Python, Backend",
                  "  경력: 신입 | 근무지: 서울 | 정규직",
                  "  마감: 2026-09-30",
                  "  Pathsdog 상세: https://jobs.pathsdog.com/jobs/%d-x" % i,
                  "기업 원문: https://example.com/%d" % i]
    return "\n".join(lines)


def test_NORMAL_parses_every_field():
    rows = parse_listing(_page([7]))
    check_equal(len(rows), 1, "한 건")
    row = rows[0]
    check_equal(row["id"], "7", "번호")
    check_equal(row["기업명"], "회사7", "기업명")
    check_equal(row["제목"], "공고7", "제목")
    check_equal(row["마감"], "2026-09-30", "마감")
    check("jobs.pathsdog.com" in row["상세주소"], row["상세주소"])
    check("example.com" in row["원문주소"], row["원문주소"])


def test_NORMAL_real_listing_parses():
    rows = parse_listing(listing_text())
    check(rows, "실제 응답에서 공고가 나와야 한다")
    check_equal(len(rows), reported_count(listing_text()),
                "서버가 말한 개수와 같아야 한다")
    for row in rows:
        check(row["id"].isdigit(), "번호가 숫자여야 한다: %r" % row["id"])
        check(bool(row["기업명"]), "기업명이 비면 안 된다: %r" % row)


def test_NORMAL_paginates_until_no_next_line():
    client = FakeClient([_page([1, 2], more=True), _page([3])])
    result = fetch_listings(client, {}, page_size=2)
    check_equal([r["id"] for r in result.rows], ["1", "2", "3"], "세 건")
    check_equal(client.asked, [0, 2], "offset 을 올린다")
    check(result.matches_reported_total, "개수 일치")


def test_EXCEPTION_page_failure_keeps_earlier_pages():
    client = FakeClient([_page([1], more=True), RuntimeError("2묶음 끊김")])
    result = fetch_listings(client, {}, page_size=1)
    check_equal(len(result.rows), 1, "앞 묶음은 잃지 않는다")
    check("2번째 묶음" in result.stop_reason, result.stop_reason)


def test_EXCEPTION_missing_count_is_none_not_zero():
    # 개수를 못 읽으면 대조를 포기한다. 0 으로 속이면 "다 읽었다" 고 잘못 판정한다.
    check_equal(reported_count("공고가 몇 개 있습니다"), None, "못 읽으면 None")
    check(not Listings(reported_total=None).matches_reported_total,
          "모르면 일치라고 말하면 안 된다")


def test_BOUNDARY_real_empty_response_stops():
    # 끝 너머는 `검색 결과가 없습니다.` 안내문이다 — `[ID:]` 도 개수 줄도 없다.
    check_equal(parse_listing(empty_text()), [], "공고가 없다")
    check_equal(reported_count(empty_text()), None, "개수 줄도 없다")
    check(not has_next_page(empty_text()), "다음 페이지도 없다")
    result = fetch_listings(FakeClient([empty_text()]), {})
    check_equal(result.rows, [], "빈 결과")
    check("비었다" in result.stop_reason, result.stop_reason)


def test_BOUNDARY_hyphen_in_company_name():
    # 회사 이름에 하이픈이 들어갈 수 있다. **처음 하나로만** 갈라야 제목이 안 잘린다.
    rows = parse_listing("[ID:1] 에이-비 컴퍼니 - AI 서비스 - 백엔드\n  기술: Python")
    check_equal(rows[0]["기업명"], "에이-비 컴퍼니", "회사 이름")
    check_equal(rows[0]["제목"], "AI 서비스 - 백엔드", "제목에 하이픈이 남아야 한다")


def test_BOUNDARY_head_without_a_hyphen():
    rows = parse_listing("[ID:1] 회사이름만있음\n  기술: Python")
    check_equal(rows[0]["기업명"], "", "가를 수 없으면 기업명은 비운다")
    check_equal(rows[0]["제목"], "회사이름만있음", "통째로 제목으로")


def test_BOUNDARY_duplicate_ids_counted_once():
    client = FakeClient([_page([1, 2], more=True), _page([2, 3])])
    result = fetch_listings(client, {}, page_size=2)
    check_equal([r["id"] for r in result.rows], ["1", "2", "3"], "겹친 것은 한 번만")


def test_BOUNDARY_same_page_repeating_stops():
    client = FakeClient([_page([1], more=True)] * 5)
    result = fetch_listings(client, {}, page_size=1, max_pages=5)
    check_equal(len(result.rows), 1, "새 공고가 없으면 멈춘다")
    check("새 공고가 없다" in result.stop_reason, result.stop_reason)


def test_BOUNDARY_max_pages_caps_runaway():
    client = FakeClient([_page([n], more=True) for n in range(1, 21)])
    result = fetch_listings(client, {}, page_size=1, max_pages=3)
    check_equal(len(client.asked), 3, "상한을 넘지 않는다")
    check("상한" in result.stop_reason, result.stop_reason)


def test_BOUNDARY_count_mismatch_is_visible():
    # 서식이 바뀌어 `[ID:]` 를 못 잡으면 여기서 드러나야 한다.
    client = FakeClient([_page([1], said=5)])
    result = fetch_listings(client, {})
    check_equal(result.reported_total, 5, "서버가 말한 개수")
    check_equal(len(result.rows), 1, "읽어 낸 개수")
    check(not result.matches_reported_total, "**불일치로 드러나야 한다**")


def test_BOUNDARY_detail_asks_for_the_full_description():
    from lib.collect import DETAIL_TOOL, fetch_detail

    class Spy:
        def __init__(self):
            self.args = None

        def call_tool(self, name, arguments):
            self.name, self.args = name, arguments
            return detail_text()

    spy = Spy()
    fetch_detail(spy, "3354")
    check_equal(spy.name, DETAIL_TOOL, "상세 도구")
    check_equal(spy.args["job_id"], 3354, "번호는 숫자로 보낸다")
    check(spy.args["include_full_description"],
          "**원문을 함께 받아야 한다** — 라벨 칸만으로는 전형 절차까지 섞인다")


def test_NORMAL_on_page_reports_progress():
    # 진행 표시가 없으면 오래 도는 동안 멈춘 것과 구별이 안 된다.
    seen = []
    client = FakeClient([_page([1, 2], more=True), _page([3])])
    fetch_listings(client, {}, page_size=2, on_page=seen.append)
    check_equal(seen, [2, 1], "묶음마다 읽어 낸 수: %r" % seen)
