"""목록 페이지네이션과 상세·본문 수집.

## 세 엔드포인트

    POST /Recruit/Home/_GI_List/       목록 HTML 조각 (condition[] + Page)
    POST /Recruit/Home/_SearchCount/   총계. **목록에 안 실려 있다**
    GET  /Recruit/GI_Read/{gno}        상세 (JSON-LD)
    GET  /Recruit/GI_Read_Comt_Ifrm    본문. 상세 안에 iframe 으로 들어간다

사람인은 목록에 총계가 박혀 있어 한 번에 대조할 수 있었는데, 잡코리아는 **따로 물어야
한다.** 그래도 대조는 한다 — 조용히 적게 걷히는 것을 잡는 유일한 수단이다.

## 페이지 번호는 `Page` 다

목록 페이지 URL(`/recruit/joblist`)에 `page` `Page_No` `pageNo` 를 붙여 봐야 **전부
무시되고 1페이지가 온다.** POST 엔드포인트에서 `Page` 로만 넘어간다.
실측 — Page=1 40건 + Page=2 27건 = 67건, 겹침 0, 총계 67과 일치.
"""
from __future__ import annotations

import html as html_module
import re
from dataclasses import dataclass, field

LIST_PATH = "/Recruit/Home/_GI_List/"
COUNT_PATH = "/Recruit/Home/_SearchCount/"
DETAIL_PATH = "/Recruit/GI_Read/%s"
BODY_PATH = "/Recruit/GI_Read_Comt_Ifrm"
LIST_REFERER = "https://www.jobkorea.co.kr/recruit/joblist?menucode=duty"

PAGE_FIELD = "Page"
# 한 페이지에 40건이 온다. 폭주 방지 상한 — 200페이지면 8,000건이다.
MAX_PAGES = 200

# 공고 한 줄. 공고번호가 속성에 박혀 있어 헷갈릴 일이 없다.
ITEM = re.compile(r'<tr class="devloopArea"[^>]*data-gno="(\d+)"')
COMPANY = re.compile(r'<td class="tplCo"[^>]*>.*?<a[^>]*>(.*?)</a>', re.DOTALL)
# `titBx` 와 `<strong>` 사이에 **다른 것이 낀다.** 합격축하금 공고는
# `<div class="celebrate-badge">` 가 먼저 오는데, 붙어 있는 것만 받으면 그 공고의
# 제목이 통째로 빈다 — 57건 중 1건에서 실제로 그랬다.
TITLE = re.compile(r'<div class="titBx">.*?<strong>\s*<a[^>]*>(.*?)</a>', re.DOTALL)
ETC = re.compile(r'<p class="etc">(.*?)</p>', re.DOTALL)
CELL = re.compile(r'<span class="cell">(.*?)</span>', re.DOTALL)
SUMMARY = re.compile(r'<p class="dsc">(.*?)</p>', re.DOTALL)
DEADLINE = re.compile(r'<span class="date[^"]*">(.*?)</span>', re.DOTALL)

# 총계. `_SearchCount` 는 **숫자만** 돌려준다 — 응답 본문이 `57` 두 글자다.
# "N건" 을 기대하면 못 읽고 조용히 총계 대조를 포기하게 된다.
TOTAL = re.compile(r"^\s*([\d,]+)\s*$")

_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


def _text_of(block: str, pattern: re.Pattern[str]) -> str:
    found = pattern.search(block)
    if not found:
        return ""
    return _SPACES.sub(" ", html_module.unescape(_TAG.sub(" ", found.groups()[-1]))).strip()


@dataclass
class Listings:
    rows: list[dict] = field(default_factory=list)
    pages: int = 0
    reported_total: int | None = None
    stop_reason: str = ""

    @property
    def matches_reported_total(self) -> bool:
        """사이트가 밝힌 총계와 걷은 수가 같은가. 다르면 어딘가 흘렸다."""
        return self.reported_total is not None and len(self.rows) == self.reported_total


def parse_listings(fragment: str) -> list[dict]:
    """목록 조각에서 공고들을 뽑는다.

    조건 셀(`p.etc > span.cell`)은 **개수가 5~6개로 들쭉날쭉하다** — 연봉이 있는 공고만
    한 칸 더 붙는다. 그래서 위치로 읽지 않고 통째로 넘긴 뒤 `record` 가 뜻을 가린다.
    """
    starts = [(m.group(1), m.start()) for m in ITEM.finditer(fragment or "")]
    rows = []
    for index, (gno, start) in enumerate(starts):
        end = starts[index + 1][1] if index + 1 < len(starts) else len(fragment)
        block = fragment[start:end]
        cells = ETC.search(block)
        rows.append({
            "gno": gno,
            "기업명": _text_of(block, COMPANY),
            "제목": _text_of(block, TITLE),
            "조건": [_SPACES.sub(" ", html_module.unescape(_TAG.sub(" ", c))).strip()
                    for c in (CELL.findall(cells.group(1)) if cells else [])],
            "직무요약": _text_of(block, SUMMARY),
            "마감일": _text_of(block, DEADLINE),
        })
    return rows


def fetch_total(client, conditions: dict) -> int | None:
    """사이트가 밝히는 총계. 못 읽으면 None — 0 으로 속이지 않는다."""
    try:
        answer = client.post_html(COUNT_PATH, conditions, referer=LIST_REFERER)
    except Exception:
        return None
    found = TOTAL.match(_TAG.sub("", answer or ""))
    return int(found.group(1).replace(",", "")) if found else None


def fetch_listings(client, conditions: dict, *, max_pages: int = MAX_PAGES,
                   on_page=None) -> Listings:
    """끝까지 페이지를 넘기며 모은다. 중간에 실패해도 **앞서 모은 것은 돌려준다**."""
    result = Listings(reported_total=fetch_total(client, conditions))
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        try:
            fragment = client.post_html(LIST_PATH, conditions,
                                        {PAGE_FIELD: page}, referer=LIST_REFERER)
        except Exception as error:                 # 여기서 죽으면 앞 페이지도 잃는다
            result.stop_reason = "%d페이지에서 실패: %s" % (page, error)
            return result
        result.pages = page

        rows = parse_listings(fragment)
        fresh = [row for row in rows if row["gno"] not in seen]
        seen.update(row["gno"] for row in fresh)
        result.rows.extend(fresh)
        if on_page:
            on_page(len(fresh))

        # 총계를 다 채웠으면 거기서 끝이다. 가장 분명한 신호라 먼저 본다.
        if result.reported_total and len(result.rows) >= result.reported_total:
            result.stop_reason = ("총계 %d건을 다 모았다 (%d페이지)"
                                  % (result.reported_total, page))
            return result
        if not rows:
            result.stop_reason = "%d페이지가 비었다" % page
            return result
        if not fresh:
            result.stop_reason = ("%d페이지에 새 공고가 없다 (같은 페이지 반복 의심)" % page)
            return result
    result.stop_reason = "상한 %d페이지에 닿았다" % max_pages
    return result


def fetch_detail(client, gno: str) -> str:
    """상세 HTML. 여기에 JSON-LD 가 들어 있다."""
    return client.get_html(DETAIL_PATH % gno, referer=LIST_REFERER)


def fetch_body(client, gno: str) -> str:
    """공고 본문 HTML.

    **상세 페이지에는 본문이 없다.** iframe 으로 따로 불러온다 — 상세 HTML 에는
    `iframe` 이라는 글자조차 없어서(JS 가 나중에 꽂는다) 없는 줄 알기 쉽다.
    """
    return client.get_html(BODY_PATH,
                           {"Gno": gno, "isHiringCenter": "false", "hideMapView": "false"},
                           referer="https://www.jobkorea.co.kr" + DETAIL_PATH % gno)
