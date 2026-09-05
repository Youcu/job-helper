"""`lib/collect.py` — 목록 파싱과 페이지네이션.

**여기서 틀리면 조용히 적게 걷힌다.** 예외가 안 나고 CSV 도 그럴듯해서, 총계와 대조하지
않으면 아무도 모른다. 실제로 `class="list_item effect"` 라는 변종을 못 받아 131건 중
2건을 잃었고, 페이지가 밝힌 총계와 맞춰 보고서야 알았다.

그래서 이 파일이 노리는 것은 셋이다.

1. **변종 마크업을 흘리는 것** — 클래스 이름에 뭐가 붙어도 받아야 한다
2. **광고를 진짜 공고로 세는 것** — 1페이지 위쪽에 광고가 붙는다
3. **끝을 잘못 판정하는 것** — 너무 일찍 멈추거나 영영 안 멈추거나
"""
from __future__ import annotations

from lib import collect
from tests.helpers import check, check_equal


def card(rec_idx: str, *, extra_class: str = "", company: str = "회사",
         title: str = "제목", place: str = "서울전체", career: str = "신입 · 정규직",
         education: str = "대졸↑", deadline: str = "~09.14(월)") -> str:
    return (
        '<div id="rec-%s" class="list_item%s"><div class="box_item">'
        '<div class="col company_nm"><a href="#" class="str_tit">%s</a>'
        '<button class="interested_corp"><span>관심기업 등록</span></button></div>'
        '<div class="job_tit"><a class="str_tit"><span>%s</span></a>'
        '<button class="btn_scrap"><span class="blind">스크랩</span></button></div>'
        '<span class="job_sector"><span>백엔드</span></span>'
        '<p class="work_place">%s</p><p class="career">%s</p>'
        '<p class="education">%s</p>'
        '<p class="support_detail"><span class="date">%s</span>'
        '<span class="deadlines">2일 전 등록</span></p>'
        "</div></div>" % (rec_idx, extra_class, company, title, place, career,
                          education, deadline))


def page(*cards: str, total: int | None = None, ads: str = "") -> str:
    heading = ('<div class="common_recruilt_list">전체 채용정보 %d 건</div>' % total
               if total is not None else "")
    return "<html>" + ads + heading + "".join(cards) + "</html>"


class FakeClient:
    """페이지를 미리 정해 두고 돌려준다. 네트워크를 안 탄다."""

    def __init__(self, pages: list[str], fail_at: int | None = None):
        self.pages = pages
        self.fail_at = fail_at
        self.asked: list[int] = []

    def get_html(self, path, params=None, referer=None):
        number = (params or {}).get(collect.PAGE_PARAM, 1)
        self.asked.append(number)
        if self.fail_at is not None and number == self.fail_at:
            raise ConnectionError("끊김")
        return self.pages[number - 1] if number <= len(self.pages) else page(total=0)


# ─────────────────────────────── 일반 ───────────────────────────────

def test_NORMAL_all_eight_fields_are_read():
    rows = collect.parse_listings(page(card("1"), total=1))
    check_equal(len(rows), 1, "공고 하나")
    row = rows[0]
    check_equal(row["rec_idx"], "1", "공고번호")
    check_equal(row["기업명"], "회사", "기업명 — 관심기업 버튼 글자가 섞이면 안 된다")
    check_equal(row["제목"], "제목", "제목 — 스크랩 버튼 글자가 섞이면 안 된다")
    check_equal(row["근무지"], "서울전체", "근무지")
    check_equal(row["경력"], "신입 · 정규직", "경력 원문")
    check_equal(row["마감일"], "~09.14(월)", "마감일")


def test_NORMAL_deadline_comes_from_date_not_deadlines():
    # `deadlines` 는 "2일 전 등록" 이다. 이름만 보고 고르면 등록 경과일이 마감일이 된다.
    row = collect.parse_listings(page(card("1"), total=1))[0]
    check("등록" not in row["마감일"], "등록 경과일을 마감일로 넣으면 안 된다: %r" % row["마감일"])


def test_NORMAL_reported_total_is_read():
    check_equal(collect.reported_total(page(card("1"), total=131)), 131, "총계")


def test_NORMAL_pagination_walks_to_the_end():
    client = FakeClient([page(card("1"), card("2"), total=3),
                         page(card("3")),
                         page(total=0)])
    result = collect.fetch_listings(client, {})
    check_equal(len(result.rows), 3, "세 건을 다 모아야 한다")
    check_equal(result.reported_total, 3, "1페이지에서 읽은 총계를 간직한다")
    check(result.matches_reported_total, "총계와 맞아야 한다")


# ─────────────────────────────── 예외 ───────────────────────────────

def test_EXCEPTION_class_variant_is_not_dropped():
    # 결함: `class="list_item"` 만 받아 `list_item effect` 2건을 조용히 잃었다.
    rows = collect.parse_listings(page(card("1"), card("2", extra_class=" effect"), total=2))
    check_equal([r["rec_idx"] for r in rows], ["1", "2"],
                "클래스에 뭐가 붙어도 공고는 공고다")


def test_EXCEPTION_ads_before_the_heading_are_not_counted():
    ads = card("999") + card("998")
    rows = collect.parse_listings(page(card("1"), total=1, ads=ads))
    check_equal([r["rec_idx"] for r in rows], ["1"],
                "머리말 앞의 광고는 진짜 공고가 아니다")


def test_EXCEPTION_page_without_heading_is_read_whole():
    # 2페이지부터는 `전체 채용정보` 머리말이 없다. 머리말을 못 찾았다고 빈 목록을
    # 돌려주면 2페이지 이후가 통째로 사라진다.
    rows = collect.parse_listings("<html>" + card("1") + card("2") + "</html>")
    check_equal(len(rows), 2, "머리말이 없어도 목록은 읽어야 한다")


def test_EXCEPTION_empty_page_is_empty_not_error():
    check_equal(collect.parse_listings(""), [], "빈 문자열")
    check_equal(collect.parse_listings("<html></html>"), [], "공고 없는 페이지")
    check_equal(collect.reported_total("<html></html>"), None, "총계가 없으면 None")


def test_EXCEPTION_missing_field_is_blank_not_crash():
    broken = '<div id="rec-1" class="list_item"><div class="box_item"></div></div>'
    row = collect.parse_listings("<html>" + broken + "</html>")[0]
    check_equal(row["rec_idx"], "1", "공고번호는 있다")
    check_equal(row["기업명"], "", "없는 칸은 빈칸이지 오류가 아니다")


def test_EXCEPTION_failure_midway_keeps_what_was_collected():
    # 결함이 될 뻔한 곳: 여기서 예외를 올리면 앞서 모은 페이지도 같이 잃는다.
    client = FakeClient([page(card("1"), card("2"), total=9), page(card("3"))], fail_at=2)
    result = collect.fetch_listings(client, {})
    check_equal(len(result.rows), 2, "1페이지에서 모은 것은 살아야 한다")
    check("2페이지에서 실패" in result.stop_reason, "왜 멈췄는지 남아야 한다: %r"
          % result.stop_reason)


# ─────────────────────────────── 경계 ───────────────────────────────

def test_BOUNDARY_repeated_page_stops_the_walk():
    # 서버가 page 를 무시하고 같은 페이지를 계속 주면 영원히 돈다.
    # 총계를 못 읽는 상황에서도 멈춰야 하므로 total 을 주지 않는다.
    same = page(card("1"))
    client = FakeClient([same] * 10)
    result = collect.fetch_listings(client, {}, max_pages=10)
    check_equal(len(result.rows), 1, "중복은 한 번만 센다")
    check("새 공고가 없다" in result.stop_reason, "반복을 사유로 남긴다: %r" % result.stop_reason)
    check(len(client.asked) < 10, "끝까지 돌지 않고 멈춰야 한다: %d페이지" % len(client.asked))


def test_BOUNDARY_max_pages_is_a_hard_stop():
    client = FakeClient([page(card(str(n)), total=999) for n in range(1, 21)])
    result = collect.fetch_listings(client, {}, max_pages=3)
    check_equal(len(client.asked), 3, "상한에서 멈춰야 한다")
    check("상한" in result.stop_reason, "사유: %r" % result.stop_reason)


def test_BOUNDARY_single_page_shorter_than_page_size():
    client = FakeClient([page(card("1"), total=1), page(total=0)])
    result = collect.fetch_listings(client, {})
    check_equal(len(result.rows), 1, "한 페이지보다 적어도 정상이다")
    check(result.matches_reported_total, "총계와 맞는다")


def test_BOUNDARY_count_mismatch_is_visible():
    # 총계 대조가 없으면 조용히 적게 걷힌 것을 못 잡는다. 그게 실제로 일어났다.
    client = FakeClient([page(card("1"), total=131), page(total=0)])
    result = collect.fetch_listings(client, {})
    check(not result.matches_reported_total, "1건인데 총계 131이면 어긋난 것이다")


def test_BOUNDARY_zero_results_stops_immediately():
    client = FakeClient([page(total=0)])
    result = collect.fetch_listings(client, {})
    check_equal(result.rows, [], "결과 없음")
    check("비었다" in result.stop_reason, "사유: %r" % result.stop_reason)


def test_BOUNDARY_same_job_on_two_pages_counts_once():
    client = FakeClient([page(card("1"), card("2"), total=3),
                         page(card("2"), card("3")),
                         page(total=0)])
    result = collect.fetch_listings(client, {})
    check_equal([r["rec_idx"] for r in result.rows], ["1", "2", "3"],
                "페이지가 겹쳐도 한 번만")


def test_NORMAL_progress_callback_reports_fresh_count():
    seen = []
    client = FakeClient([page(card("1"), card("2"), total=3), page(card("3")),
                         page(total=0)])
    collect.fetch_listings(client, {}, on_page=seen.append)
    check_equal(seen, [2, 1], "페이지마다 새로 얻은 건수를 알려야 한다")


def test_NORMAL_detail_is_fetched_from_jobs_view():
    # `jobs/relay/view` 는 본문 없는 JS 껍데기를 준다 — 380KB 나 오지만 본문 섹션이
    # 통째로 없어서 잘 받은 줄 알기 딱 좋다. 실제로 131건을 그렇게 헛받았다.
    class Recorder:
        def __init__(self):
            self.path = None
            self.params = None

        def get_html(self, path, params=None, referer=None):
            self.path, self.params = path, params
            return "<html>ok</html>"

    recorder = Recorder()
    collect.fetch_detail(recorder, "123")
    check_equal(recorder.path, "/zf_user/jobs/view", "relay 가 아니라 view 다")
    check_equal(recorder.params, {"rec_idx": "123"}, "공고번호")


def test_BOUNDARY_reaching_the_reported_total_is_a_clean_stop():
    # 1페이지에 다 담기는 조건에서 사람인은 2페이지에도 같은 것을 돌려준다.
    # 총계를 먼저 보지 않으면 정상 종료가 "같은 페이지 반복 의심" 으로 보고된다.
    same = page(card("1"), card("2"), total=2)
    client = FakeClient([same] * 5)
    result = collect.fetch_listings(client, {})
    check_equal(len(result.rows), 2, "총계만큼 모았다")
    check("다 모았다" in result.stop_reason, "정상 종료로 보고해야 한다: %r" % result.stop_reason)
    check_equal(len(client.asked), 1, "총계를 채웠으면 다음 페이지를 안 부른다")


def test_BOUNDARY_repeat_detection_still_works_without_a_total():
    # 총계를 못 읽는 페이지에서도 무한 반복은 막아야 한다.
    same = page(card("1"))
    client = FakeClient([same] * 10)
    result = collect.fetch_listings(client, {}, max_pages=10)
    check("새 공고가 없다" in result.stop_reason, "반복 감지: %r" % result.stop_reason)


def test_NORMAL_page_number_uses_the_right_parameter_name():
    # `recruitPage` 는 **조용히 무시된다** — 1페이지가 계속 돌아온다.
    # 총계 389건에 50건만 걷히는 것으로 알아챘다. 이름 하나가 수집량을 8분의 1로 만든다.
    class Recorder:
        def __init__(self):
            self.asked = []

        def get_html(self, path, params=None, referer=None):
            self.asked.append(dict(params or {}))
            return page(total=0)

    recorder = Recorder()
    collect.fetch_listings(recorder, {"cat_kewd": "84"})
    check_equal(collect.PAGE_PARAM, "page", "사람인이 읽는 이름은 page 다")
    check(collect.PAGE_PARAM in recorder.asked[0],
          "페이지 번호를 보내야 한다: %r" % recorder.asked[0])


def test_EXCEPTION_company_name_may_be_a_span_not_a_link():
    # **회사 정보 페이지가 없는 회사는 `<span class="str_tit">` 로 온다.**
    # `</a>` 만 찾으면 닫는 태그를 못 만나 공고 제목의 `</a>` 까지 삼킨다 —
    # 실제로 122건 중 6건의 기업명에 "관심기업 등록" 과 제목이 붙어 나왔다.
    card = (
        '<div id="rec-1" class="list_item"><div class="box_item">'
        '<div class="col company_nm"><span class="str_tit">회사</span>'
        '<button class="interested_corp"><span>관심기업 등록</span></button>'
        '<span class="info_stock">대기업</span></div>'
        '<div class="job_tit"><a class="str_tit"><span>공고 제목</span></a></div>'
        '<p class="work_place">서울</p><p class="career">신입</p>'
        '<p class="education">대졸↑</p>'
        '<p class="support_detail"><span class="date">~09.14(월)</span></p>'
        "</div></div>")
    row = collect.parse_listings("<html>" + card + "</html>")[0]
    check_equal(row["기업명"], "회사", "버튼 글자도 제목도 섞이면 안 된다")
    check_equal(row["제목"], "공고 제목", "제목은 제목대로")


def test_BOUNDARY_both_company_markups_give_the_same_name():
    link = card("1", company="회사")
    span = card("2").replace('<a href="#" class="str_tit">회사</a>',
                             '<span class="str_tit">회사</span>')
    rows = collect.parse_listings("<html>" + link + span + "</html>")
    check_equal([r["기업명"] for r in rows], ["회사", "회사"],
                "링크든 아니든 같은 이름이 나와야 한다")
