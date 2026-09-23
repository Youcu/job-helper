"""목록 페이지네이션과 상세 수집.

    GET /api/v3/job/postings         목록. page + page_size, data.total_count
    GET /api/v1/job/postings/{id}    상세

총계가 **목록 응답 안에** 들어 있다 — 잡코리아처럼 따로 물어보지 않아도 된다.

## 페이지 기반인데 **1만 건 창**이 있다

`page` 와 `page_size` 는 정상 작동하고 겹침도 없다(300건 전부 고유, `page_size` 를
100→1000 으로 바꿔도 앞 100건이 같다). 다만 이분 탐색으로 찾은 경계가 있다 —

    page=100 & page_size=100 → 100건       page=101 → 0건
                                           page=125 → 0건 (total_count 까지 0)

**`page × page_size ≤ 10,000`.** 넘으면 공고가 0건으로 오고 총계까지 0 이 되므로,
총계 대조가 "다 모았다" 고 잘못 판정하지 않도록 창에 닿았는지를 따로 본다.

## 자체 공고만 걷는다

잡플래닛 개발 공고의 97%는 잡코리아 공고를 그대로 걸어 둔 것이고, 그 97%에는
**본문이 아예 없다** (지원자격·우대사항·담당업무·기술스택 전부 빈 값. 표본 24건에서 0%).
우리는 이미 잡코리아를 긁으므로 중복이기도 하다. 그래서 `posting_apply_type` 으로 가른다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

LIST_PATH = "/api/v3/job/postings"
DETAIL_PATH = "/api/v1/job/postings/%s"

PAGE_SIZE = 100
# 서버가 한 번에 주는 최대 개수와 무관하게, `page × page_size` 가 이 값을 넘으면 0건이 온다.
WINDOW_LIMIT = 10000
MAX_PAGES = WINDOW_LIMIT // PAGE_SIZE

# 잡플래닛이 직접 받는 공고. 나머지(`jobkorea_inlink`/`jobkorea_outlink`)는 껍데기다.
OWN_APPLY_TYPES = frozenset({"jobplanet", "outlink"})

# 한 번에 던질 수 있는 요청 수. **이 사이트는 규모를 못 키운다** — 실측:
#
#     목록만 40요청 (2.5초 간격, 109초)          안 막힘
#     목록 13 + 상세 63 = 76요청 (214초)         64번째 상세에서 403
#     목록 11 + 상세 24 = 37요청 (조사 직후)      두 번 막힘
#
# 쉬는 시간이 한도를 늘려 주기는 해도 없애지는 못한다. 잡코리아가 120요청을 아무 문제
# 없이 던지는 것과 다르다.
#
# **반쯤 걷느니 아예 안 걷는다.** 절반만 든 CSV 는 "이 조건에 공고가 이만큼" 이라는
# 거짓을 만들고, 다음 실행에서 나머지가 채워진다는 보장도 없다. 그래서 조건이 넓으면
# 상세를 **한 건도 받지 않고** 물러난다 — 그 판단이 `fits_budget` 이다.
REQUEST_BUDGET = 60


@dataclass
class Listings:
    rows: list[dict] = field(default_factory=list)     # 자체 공고만
    relayed: int = 0                                   # 걸러낸 중계 공고 수
    seen: int = 0                                      # 훑어본 공고 수 (자체 + 중계)
    pages: int = 0
    reported_total: int | None = None
    stop_reason: str = ""
    hit_window_limit: bool = False
    over_budget: bool = False          # 목록만으로 예산을 넘겼다 — 상세는 시작도 안 한다

    @property
    def planned_requests(self) -> int:
        """이 조건을 끝까지 수집하는 데 드는 요청 수. 목록 페이지 + 자체 공고 하나당 상세 하나."""
        return self.pages + len(self.rows)

    def fits_budget(self, budget: int = REQUEST_BUDGET) -> bool:
        """예산 안에서 **전부** 걷을 수 있는가. 아니면 한 건도 걷지 않는다."""
        return not self.over_budget and self.planned_requests <= budget

    @property
    def matches_reported_total(self) -> bool:
        """사이트가 밝힌 총계만큼 훑었는가.

        **`rows` 가 아니라 `seen` 과 견준다** — 우리가 자체 공고만 남기는 것은 우리 결정이고,
        총계 대조는 "빠뜨리지 않고 다 훑었는가" 를 보는 것이다. 둘을 섞으면 대조가
        늘 불일치로 나와 신호로 못 쓴다.
        """
        return self.reported_total is not None and self.seen == self.reported_total


def is_own_posting(posting: dict) -> bool:
    """잡플래닛이 직접 받은 공고인가. 아니면 잡코리아 공고의 껍데기다."""
    return posting.get("posting_apply_type") in OWN_APPLY_TYPES


def fetch_listings(client, params: dict, *, page_size: int = PAGE_SIZE,
                   max_pages: int = MAX_PAGES, budget: int = REQUEST_BUDGET,
                   on_page=None) -> Listings:
    """끝까지 페이지를 넘기며 자체 공고만 모은다.

    중간에 실패해도 **앞서 모은 것은 돌려준다.**

    첫 페이지에서 총계를 보고 **목록 페이지 수만으로 예산을 넘기면 거기서 멈춘다** —
    다 훑어 봐야 어차피 상세를 못 받으므로, 못 쓸 목록을 긁느라 한도를 태울 이유가 없다.
    """
    result = Listings()
    ids: set[int] = set()
    for page in range(1, max_pages + 1):
        query = dict(params, page=page, page_size=page_size)
        try:
            data = client.get_json(LIST_PATH, query)
        except Exception as error:               # 여기서 죽으면 앞 페이지도 잃는다
            result.stop_reason = "%d페이지에서 실패: %s" % (page, error)
            return result
        result.pages = page

        # 총계는 매 페이지에 실려 온다. **창을 넘으면 0 이 오므로** 첫 값만 믿는다.
        if result.reported_total is None and data.get("total_count") is not None:
            result.reported_total = int(data["total_count"])
            needed = -(-result.reported_total // page_size)      # 올림 나눗셈
            if needed > budget:
                result.over_budget = True
                result.stop_reason = (
                    "조건이 너무 넓다 — 목록만 %d페이지(요청 %d개)라 예산 %d개를 넘는다"
                    % (needed, needed, budget))
                return result

        postings = [p for p in (data.get("recruits") or []) if p.get("id") not in ids]
        ids.update(p["id"] for p in postings if p.get("id") is not None)
        own = [p for p in postings if is_own_posting(p)]
        result.rows.extend(own)
        result.relayed += len(postings) - len(own)
        result.seen += len(postings)
        if on_page:
            on_page(len(postings))

        if not data.get("recruits"):
            if page * page_size > WINDOW_LIMIT:
                result.hit_window_limit = True
                result.stop_reason = (
                    "**%d건 창에 닿았다** — 잡플래닛은 %s번째 너머를 안 준다 (%d페이지)"
                    % (WINDOW_LIMIT, format(WINDOW_LIMIT, ","), page))
            else:
                result.stop_reason = "%d페이지가 비었다" % page
            return result
        if result.reported_total is not None and result.seen >= result.reported_total:
            result.stop_reason = ("총계 %d건을 다 훑었다 (%d페이지)"
                                  % (result.reported_total, page))
            return result
        if not postings:
            result.stop_reason = "%d페이지에 새 공고가 없다 (같은 페이지 반복 의심)" % page
            return result
    result.hit_window_limit = True
    result.stop_reason = "상한 %d페이지에 닿았다 (%d건 창)" % (max_pages, WINDOW_LIMIT)
    return result


def fetch_detail(client, posting_id) -> dict:
    """공고 상세. 본문 네 칸과 기술스택이 여기 있다."""
    return client.get_json(DETAIL_PATH % posting_id)
