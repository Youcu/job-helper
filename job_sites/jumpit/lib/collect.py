"""목록 페이지네이션과 상세 수집.

    GET /api/positions?jobCategory=N&career=N&locationTag=N&sort=popular&page=N&size=N
    GET /api/position/{id}

총계가 목록 응답 안에 있고(`result.totalCount`), 끝을 알려 주는 값도 따로 있다
(`result.emptyPosition`). 네 사이트 중 페이지네이션이 가장 친절하다.

## 다만 끝 너머에서 총계가 0 으로 온다

    page=46  11건  totalCount 731  emptyPosition=false     ← 마지막 페이지
    page=47   0건  totalCount **0**  emptyPosition=true
    page=100  0건  totalCount **0**  emptyPosition=true

총계를 매번 덮어쓰면 마지막에 0 이 남아 "다 모았다" 는 판정이 무너진다. 잡플래닛에서도
같은 모양이었다 — **첫 값만 믿는다.**

실측 — 731건이 16건씩 46페이지(16×45+11=731). `size` 도 먹는다.

## `totalCount` 는 **중복을 포함한 수**다

한 공고가 여러 직무에 걸쳐 있으면(상세의 `jobCategories` 가 배열이다) 직무를 여럿 보낼 때
**같은 공고가 여러 번 실려 온다.** 실측:

    직무 1개          총계 139 · 받음 139 · 고유 139 · 중복 0
    직무 2개(1,3)     총계 153 · 받음 153 · 고유 152 · 중복 1
    직무 21개(전체)    총계 698 · 받음 698 · 고유 688 · 중복 10

그래서 총계는 **받은 항목 수**(`received`)와 견준다. 고유 수와 견주면 직무를 여럿 넣는
순간 늘 불일치가 나와 신호로 못 쓴다 — 진짜로 흘렸을 때를 못 알아챈다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

LIST_PATH = "/api/positions"
DETAIL_PATH = "/api/position/%s"

PAGE_SIZE = 50
# 폭주 방지 상한. 50건씩 200페이지면 1만 건이라 실제 규모(731건)보다 한참 넉넉하다.
MAX_PAGES = 200


@dataclass
class Listings:
    rows: list[dict] = field(default_factory=list)     # 고유 공고
    received: int = 0                                  # 받은 항목 수 (중복 포함)
    pages: int = 0
    reported_total: int | None = None
    stop_reason: str = ""

    @property
    def duplicates(self) -> int:
        """여러 직무에 걸쳐 두 번 이상 실려 온 공고 수."""
        return self.received - len(self.rows)

    @property
    def matches_reported_total(self) -> bool:
        """사이트가 밝힌 총계만큼 받았는가. 다르면 어딘가 흘렸다.

        **`rows` 가 아니라 `received` 와 견준다** — 한 공고가 여러 직무에 걸치면 총계에
        여러 번 세어지므로, 고유 수와 견주면 직무를 여럿 넣는 순간 늘 불일치가 나와
        신호로 못 쓴다. **조용히 적게 걷히는 것을 잡는 유일한 수단**이라 매번 본다.
        """
        return self.reported_total is not None and self.received == self.reported_total


def fetch_listings(client, params: dict, *, page_size: int = PAGE_SIZE,
                   max_pages: int = MAX_PAGES, on_page=None) -> Listings:
    """끝까지 페이지를 넘기며 모은다. 중간에 실패해도 **앞서 모은 것은 돌려준다.**"""
    result = Listings()
    seen: set[int] = set()
    for page in range(1, max_pages + 1):
        query = dict(params, page=page, size=page_size)
        try:
            data = client.get_json(LIST_PATH, query)
        except Exception as error:               # 여기서 죽으면 앞 페이지도 잃는다
            result.stop_reason = "%d페이지에서 실패: %s" % (page, error)
            return result
        result.pages = page

        # **첫 값만 믿는다** — 끝 너머에서 0 이 온다.
        if result.reported_total is None and data.get("totalCount") is not None:
            result.reported_total = int(data["totalCount"])

        arrived = data.get("positions") or []
        result.received += len(arrived)
        # **한 항목씩 본다.** 페이지 단위로 걸러 내면 같은 페이지 안에 같은 공고가 두 번
        # 들어 있을 때 둘 다 통과한다 — 직무를 여럿 보내면 실제로 겹쳐 온다.
        positions = []
        for item in arrived:
            key = item.get("id")
            if key is None or key in seen:
                continue
            seen.add(key)
            positions.append(item)
        result.rows.extend(positions)
        if on_page:
            on_page(len(arrived))

        # 사이트가 직접 "끝" 이라고 말해 준다. 가장 분명한 신호라 먼저 본다.
        if data.get("emptyPosition") or not data.get("positions"):
            result.stop_reason = "%d페이지에서 끝났다 (사이트가 비었다고 알림)" % page
            return result
        if result.reported_total and result.received >= result.reported_total:
            result.stop_reason = ("총계 %d건을 다 모았다 (%d페이지)"
                                  % (result.reported_total, page))
            return result
        if not positions:
            # 받기는 받았는데 전부 앞서 본 것이다. 페이지 번호가 무시되고 있을 수 있다.
            result.stop_reason = "%d페이지에 새 공고가 없다 (같은 페이지 반복 의심)" % page
            return result
    result.stop_reason = "상한 %d페이지에 닿았다" % max_pages
    return result


def fetch_detail(client, position_id) -> dict:
    """공고 상세. 지원자격·우대사항·담당업무가 여기 있다."""
    return client.get_json(DETAIL_PATH % position_id)
