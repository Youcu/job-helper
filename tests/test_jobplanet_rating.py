"""회사 평점으로 거르는 일.

**이 단계도 행을 지운다.** 그래서 "잘 지우는가" 보다 **"안 지워야 할 것을 지키는가"** 를
더 많이 굳힌다. 특히 이름 맞추기가 느슨해지면 `안랩` 공고에 `두리안랩` 의 평점이 붙고,
그 평점이 2.9 를 넘으면 **틀린 근거로 살아남는다** — 지워지는 것보다 알아채기 어렵다.

그물은 타지 않는다. 떠 놓은 실제 응답을 돌려주는 가짜 opener 를 넣는다.
"""
from __future__ import annotations

import json
import urllib.error

import jobplanet_rating as jr
from _common.store import COLUMNS

from .helpers import check, check_equal, read_csv, temp_dir, write_csv


def _item(name, rating, cid=1, **extra):
    row = {"company_id": cid, "name": name, "rate_total_avg": rating,
           "industry_name": "IT/웹/통신", "company_headcounts": 10,
           "company_years": "5년차 (2021)", "posting_counts": 1, "city_name": "서울"}
    row.update(extra)
    return row


class _Response:
    def __init__(self, body): self._body = body
    def read(self): return self._body
    def __enter__(self): return self
    def __exit__(self, *_): return False


def _opener(pages: dict, calls: list | None = None, fail: list | None = None):
    """질의 → items 를 돌려주는 가짜 그물. `fail` 에 적은 횟수만큼 먼저 403 을 낸다."""
    state = {"403": list(fail or [])}

    def open_(request, timeout=None):
        import urllib.parse as up
        query = up.parse_qs(up.urlsplit(request.full_url).query)["query"][0]
        if calls is not None:
            calls.append(query)
        if state["403"]:
            state["403"].pop(0)
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)
        items = pages.get(query, [])
        body = json.dumps({"status": "success", "data": {"items": items,
                                                         "total_count": len(items)}})
        return _Response(body.encode())
    return open_


def _searcher(pages, calls=None, fail=None, **kw):
    return jr.Searcher(temp_dir() / "log.jsonl", min_interval=0, sleep=lambda _s: None,
                       opener=_opener(pages, calls, fail), **kw)


def _row(**fields):
    row = {c: "" for c in COLUMNS}
    row.update({"기업명": "회사", "공고명": "백엔드", "사이트명": "wanted",
                "URL": "https://ex/1"})
    row.update(fields)
    return row


# ── 일반 ────────────────────────────────────────────────────────────────

def test_NORMAL_exact_name_is_found_on_the_first_try():
    calls = []
    net = _searcher({"(주)안랩": [_item("(주)안랩", 3.5)]}, calls)
    got = jr.look_up(net, "(주)안랩")
    check_equal(got["평점"], 3.5, "평점")
    check_equal(got["찾은방법"], "원문", "첫 변형에서 맞았다")
    check_equal(calls, ["(주)안랩"], "**맞았으면 뒤 변형은 안 묻는다**: %r" % calls)


def test_NORMAL_paren_variant_saves_a_company():
    # 실측: 사용자가 겪은 경우이고, 첫 100곳에서 13곳이 이 변형으로 살았다.
    calls = []
    net = _searcher({"바카티오": [_item("(주)바카티오", 3.2)]}, calls)
    got = jr.look_up(net, "바카티오(Vacatio)")
    check_equal(got["평점"], 3.2, "괄호를 떼면 나온다")
    check("괄호" in got["찾은방법"], "어느 변형이 살렸는지 남아야 한다: %r" % got["찾은방법"])


def test_NORMAL_gate_keeps_and_cuts_by_the_line():
    home = temp_dir()
    write_csv(home / "in.csv", [_row(기업명="좋은회사", URL="u/1"),
                               _row(기업명="나쁜회사", URL="u/2")], COLUMNS)
    net = _searcher({"좋은회사": [_item("좋은회사", 3.0)],
                     "나쁜회사": [_item("나쁜회사", 2.0)]})
    code = jr._run(home / "in.csv", home / "out.csv", home / "report.csv",
                   home / "same.csv", home / "cache.json", home / "log.jsonl",
                   searcher=net)
    check_equal(code, 0, "정상 종료")
    check_equal([r["기업명"] for r in read_csv(home / "out.csv")], ["좋은회사"], "3.0 만 남는다")
    check_equal(len(read_csv(home / "report.csv")), 1, "뺀 행은 보고에 남는다")


def test_NORMAL_same_name_candidates_go_to_same_names_csv():
    home = temp_dir()
    write_csv(home / "in.csv", [_row(기업명="제일산업", URL="u/1")], COLUMNS)
    net = _searcher({"제일산업": [_item("제일산업(주)", 2.6, 1), _item("제일산업", 1.8, 2),
                               _item("제일산업(주) 안성공장", 2.3, 3)]})
    jr._run(home / "in.csv", home / "out.csv", home / "report.csv", home / "same.csv",
            home / "cache.json", home / "log.jsonl", searcher=net)
    same = read_csv(home / "same.csv")
    check_equal(len(same), 2, "**이름이 같은 둘만** 후보다 (안성공장은 다른 회사): %r"
                % [r["잡플래닛이름"] for r in same])
    check(same[0]["업종"] and same[0]["사원수"],
          "다음 단계가 가릴 재료(업종·사원수)가 있어야 한다: %r" % same[0])


# ── 예외 ────────────────────────────────────────────────────────────────

def test_EXCEPTION_missing_input_stops_with_one():
    home = temp_dir()
    check_equal(jr._run(home / "없다.csv", home / "o.csv", home / "r.csv", home / "s.csv",
                        home / "c.json", home / "l.jsonl", searcher=_searcher({})), 1, "입력이 없으면 1")


def test_EXCEPTION_one_block_clears_and_the_run_goes_on():
    # 실측(3회 × 40곳)에서 403 은 예외 없이 30초 한 번에 풀렸다.
    net = _searcher({"안랩": [_item("안랩", 3.5)]}, fail=[403])
    check_equal(jr.look_up(net, "안랩")["평점"], 3.5, "한 번 막혀도 이어간다")
    check_equal(net.blocks, 1, "막힌 횟수를 센다")


def test_EXCEPTION_repeated_blocks_stop_instead_of_digging_in():
    # 결함이 될 뻔한 곳: 무한 재시도를 두면 사람용 검색 페이지에서 본 악화
    # (30→60→120→240→480→960초, 끝내 안 풀림)가 여기서 그대로 일어난다.
    net = _searcher({"안랩": [_item("안랩", 3.5)]}, fail=[403] * 9)
    try:
        jr.look_up(net, "안랩")
        raise AssertionError("멈췄어야 한다")
    except jr.Blocked as error:
        check("이어갑니다" in str(error), "다시 돌리면 된다고 말해 줘야 한다: %s" % error)


def test_EXCEPTION_blocked_run_saves_what_it_got_and_exits_two():
    home = temp_dir()
    write_csv(home / "in.csv", [_row(기업명="가", URL="u/1"), _row(기업명="나", URL="u/2")],
              COLUMNS)
    net = _searcher({"가": [_item("가", 3.5)]}, fail=[] + [403] * 20)
    code = jr._run(home / "in.csv", home / "out.csv", home / "report.csv", home / "same.csv",
                   home / "cache.json", home / "log.jsonl", searcher=net)
    check_equal(code, 2, "차단으로 멈췄으면 2 — 0 을 내면 자동화가 성공으로 읽는다")
    check((home / "cache.json").exists(), "**걷은 것은 저장돼야 한다**")


def test_EXCEPTION_non_block_http_error_is_not_retried():
    # 500 을 403 처럼 다루면 한 질의에 요청 넷을 쓴다. 다시 물어도 답이 같다.
    def open_(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 500, "Server Error", {}, None)
    net = jr.Searcher(temp_dir() / "l.jsonl", min_interval=0, sleep=lambda _s: None,
                      opener=open_)
    try:
        net.search("안랩")
        raise AssertionError("올라왔어야 한다")
    except urllib.error.HTTPError as error:
        check_equal(error.code, 500, "그대로 올린다")
    check_equal(net.blocks, 0, "차단으로 세면 안 된다")


# ── 경계 ────────────────────────────────────────────────────────────────

def test_BOUNDARY_the_line_is_exactly_2_9():
    check(jr.keeps(jr.verdict({"평점": 2.9})), "2.9 는 **남는다** (미만이 아니다)")
    check(not jr.keeps(jr.verdict({"평점": 2.89})), "2.89 는 빠진다")
    check(not jr.keeps(jr.verdict({"평점": 0.0})), "0.0 은 평점이 없는 것이다")
    check(not jr.keeps(jr.verdict({"평점": None})), "검색 안 됨")
    check(not jr.keeps(jr.verdict(None)), "캐시에 아예 없는 것도 빠진다")


def test_BOUNDARY_zero_and_missing_say_different_things():
    check("평점 없음" in jr.verdict({"평점": 0.0}), "등록은 됐는데 평점이 없다")
    check("못 찾음" in jr.verdict({"평점": None}), "검색 자체가 안 됐다")


def test_BOUNDARY_partial_name_matches_are_not_the_company():
    # 잡플래닛 검색은 부분 일치를 준다. 이걸 안 막으면 `안랩` 공고에 `두리안랩`(4.0)
    # 의 평점이 붙어 **틀린 근거로 살아남는다.**
    items = [_item("(주)안랩", 3.5), _item("(주)비안랩", 1.7), _item("(주)두리안랩", 4.0),
             _item("(주)안랩클라우드메이트", 0.0)]
    got = jr.matches(items, "안랩")
    check_equal([i["name"] for i in got], ["(주)안랩"], "이름이 실제로 같은 것만: %r" % got)


def test_BOUNDARY_legal_form_differences_are_the_same_company():
    for listed in ("(주)안랩", "㈜안랩", "주식회사 안랩", "안랩"):
        got = jr.matches([_item(listed, 3.5)], "안랩")
        check_equal(len(got), 1, "%r 은 안랩이다" % listed)


def test_BOUNDARY_paren_suffix_matches_only_on_the_loose_pass():
    # 엄격하게 먼저 보고, 없을 때만 괄호를 뗀다 — 괄호까지 같은 쪽이 있으면 그쪽이 맞다.
    items = [_item("더즌(dozn)", 2.0, 1), _item("더즌", 4.0, 2)]
    check_equal([i["company_id"] for i in jr.matches(items, "더즌(dozn)")], [1],
                "괄호까지 같은 것이 있으면 그것만")
    # **엄격한 쪽이 이기면 느슨한 쪽은 안 본다.** `더즌` 을 물었을 때 이름이 정확히
    # `더즌` 인 회사가 있으면 그것이 답이지, 괄호를 떼야 같아지는 `더즌(dozn)` 까지
    # 후보로 끌어들일 이유가 없다. 느슨한 맞춤은 **엄격한 맞춤이 하나도 없을 때만** 쓴다.
    check_equal([i["company_id"] for i in jr.matches(items, "더즌")], [2],
                "정확히 같은 이름이 있으면 그것만 — 괄호본은 안 끌어온다")
    check_equal(sorted(i["company_id"] for i in jr.matches([items[0]], "더즌")), [1],
                "정확히 같은 것이 없을 때에야 괄호를 뗀다")


def test_BOUNDARY_highest_rating_wins_among_identical_names():
    picked = jr.pick([_item("제일산업", 1.6, 1), _item("제일산업", 2.6, 2),
                      _item("제일산업", 2.0, 3)])
    check_equal(picked["company_id"], 2, "**애매하면 남기는 쪽** — 잘못 지우면 흔적도 안 남는다")


def test_BOUNDARY_ladder_stops_at_the_first_hit_not_the_best():
    # 뒤 변형이 더 높은 평점을 줘도 앞에서 맞았으면 거기서 멈춘다. 요청을 아끼는 것이
    # 곧 차단을 피하는 것이다.
    calls = []
    net = _searcher({"더즌(dozn)": [_item("더즌(dozn)", 2.0)],
                     "더즌": [_item("더즌", 4.9)]}, calls)
    check_equal(jr.look_up(net, "더즌(dozn)")["평점"], 2.0, "앞 변형이 이긴다")
    check_equal(calls, ["더즌(dozn)"], "한 번만 물었다: %r" % calls)


def test_BOUNDARY_ladder_has_no_duplicate_queries():
    # 같은 질의를 두 번 던지면 답은 같은데 차단에는 두 배로 가까워진다.
    for name in ("안랩", "(주)안랩", "더즌(dozn)", "(주)투모로 로보틱스", "IPEA(정보처리기사협회)"):
        queries = [q for q, _how in jr.variants(name)]
        check_equal(len(queries), len({q.lower() for q in queries}),
                    "%r 의 사다리에 같은 질의가 둘: %r" % (name, queries))


def test_BOUNDARY_ladder_skips_one_letter_queries():
    # 한 글자로 검색하면 아무 회사나 쏟아진다. 그걸 후보로 삼으면 엉뚱한 평점이 붙는다.
    for _query, _how in jr.variants("가 (나)"):
        check(len(_query) >= 2, "한 글자 질의가 사다리에 있다: %r" % _query)


def test_BOUNDARY_cache_makes_the_second_run_ask_nothing():
    home = temp_dir()
    write_csv(home / "in.csv", [_row(기업명="가나", URL="u/1")], COLUMNS)
    args = (home / "in.csv", home / "out.csv", home / "report.csv", home / "same.csv",
            home / "cache.json", home / "log.jsonl")
    first = []
    jr._run(*args, searcher=_searcher({"가나": [_item("가나", 3.5)]}, first))
    second = []
    jr._run(*args, searcher=_searcher({"가나": [_item("가나", 3.5)]}, second))
    check_equal(first, ["가나"], "처음엔 묻는다")
    check_equal(second, [], "**이어받기** — 이미 있는 곳은 다시 안 묻는다: %r" % second)


def test_BOUNDARY_cache_survives_a_broken_file():
    home = temp_dir()
    (home / "cache.json").write_text("{망가진", encoding="utf-8")
    check_equal(jr.load_cache(home / "cache.json"), {},
                "깨진 캐시에 터지지 않고 처음부터 간다")


def test_BOUNDARY_longest_spelling_represents_the_company():
    rows = [_row(기업명="안랩", URL="u/1"), _row(기업명="(주)안랩", URL="u/2")]
    got = jr._companies(rows)
    check_equal(list(got.values()), ["(주)안랩"],
                "한 키에 표기가 여럿이면 **정보가 가장 많은 것**으로 묻는다")


def test_BOUNDARY_blank_company_name_is_skipped_not_searched():
    check_equal(jr._companies([_row(기업명="", URL="u/1")]), {},
                "기업명이 비면 물어볼 것이 없다 — 빈 질의를 던지면 아무 회사나 온다")


def test_BOUNDARY_one_letter_company_name_only_gets_the_legal_form_variant():
    """한 글자짜리 기업명은 **법인표기를 붙인 것 하나만** 묻는다.

    `가` 로 검색하면 이름에 `가` 가 든 회사가 쏟아지고, 그중 하나에 평점이 붙으면
    엉뚱한 근거로 공고가 살거나 죽는다. 사다리의 두 글자 하한이 그것을 막는데,
    그러면 남는 질의가 `(주)가` 하나뿐이다 — 안 묻는 것보다는 낫다.
    """
    check_equal([q for q, _ in jr.variants("가")], ["(주)가"], "남는 질의 하나")


def test_BOUNDARY_there_is_no_web_search_fallback():
    """**웹검색으로 이름을 찾아 주는 길은 없다.** 있었다가 들어냈다.

    실측 59곳을 모델에 넘겨 8곳을 "되찾았는데" 절반이 엉뚱한 회사였다 —
    `바카티오(Vacatio)` 에 `바티오(주)`(5.0)가 붙어 4행이 통과했다. 코드가 **모델이 준
    이름과 결과가 같은지**만 보고 그 이름이 원래 회사와 같은 회사인지는 안 봤기 때문이다.

    **잘못 지운 것은 보고 CSV 에 남지만 잘못 통과한 것은 표시 없이 결과에 섞인다.**
    다시 들여놓으려는 사람이 이 테스트를 먼저 보게 한다.
    """
    for gone in ("web_names", "look_up_on_web", "WEB_PROMPT"):
        check(not hasattr(jr, gone), "%s 가 되살아났다 — 위 docstring 을 읽어라" % gone)
    source = (jr.__file__ or "")
    check(source.endswith(".py"), "모듈 경로")
    text = open(source, encoding="utf-8").read()
    check("WebSearch" not in text, "모델에게 웹을 뒤지게 하는 길이 다시 생겼다")
