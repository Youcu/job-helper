"""목록 페이지네이션과 상세 수집.

## 진입점

`/zf_user/jobs/list/job-category` 를 쓴다. `/search/recruit` 이 아니다 — 총계가 맞고
끝 판정이 깔끔하다. 세 조건으로 끝까지 돌려 **수집 수 = 페이지 표기 총계**를 확인했다
(131·140·1,841건, 마지막 것은 37페이지).

## 광고를 걷어내야 한다

1페이지 위쪽에 광고 공고가 붙는다 (실측 광고 13 / 진짜 50). **`전체 채용정보` 라는
머리말이 경계다** — 그 뒤부터가 진짜 목록이고, 이 머리말은 2페이지부터는 없다.
그래서 못 찾으면 페이지 전체를 본다.

## 끝 판정

**"이번 페이지에서 새 공고가 0건"** 하나로 충분하다. 다만 그것만 믿지 않는다 —
서버가 `page` 를 무시하고 같은 페이지를 계속 주면 새 공고가 0건이라 멈추긴 하지만,
그 사실을 **이유로 남겨야** 나중에 왜 적게 걷혔는지 알 수 있다.
"""
from __future__ import annotations

import html as html_module
import re
from dataclasses import dataclass, field

LISTING_PATH = "/zf_user/jobs/list/job-category"
DETAIL_PATH = "/zf_user/jobs/view"

# 페이지 번호를 담는 이름. **`recruitPage` 가 아니다** — 그건 조용히 무시되고
# 1페이지가 계속 돌아온다. 총계 389건에 50건만 걷히는 것으로 알아챘다.
PAGE_PARAM = "page"
# 페이지당 공고 수. 사람인이 정한다 — 우리가 늘릴 수 없다.
PAGE_SIZE = 50
# 폭주 방지. 1,841건이 37페이지였으니 200페이지면 1만 건이다.
MAX_PAGES = 200

ADS_END = "전체 채용정보"
TOTAL_COUNT = re.compile(r"전체 채용정보\s+([\d,]+)\s*건")
# `class="list_item"` 뿐 아니라 `class="list_item effect"` 도 온다. 정확히 맞추면
# 그 변종을 통째로 흘린다 — 실제로 131건 중 2건을 조용히 잃었고, 페이지가 밝힌
# 총계와 대조하지 않았으면 못 알아챘을 것이다.
LIST_ITEM = re.compile(r'<div id="rec-(\d+)" class="list_item[^"]*">')

_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


def _text_of(block: str, pattern: re.Pattern[str]) -> str:
    """정규식이 잡은 **마지막 묶음**의 글자만. 태그는 공백으로 바꾼다.

    묶음을 마지막 것으로 잡는 이유 — 여는 태그 이름을 잡아 두고 같은 것으로 닫는
    패턴(`<(a|span)…>(.*?)</\1>`)에서는 값이 두 번째 묶음에 온다.
    """
    found = pattern.search(block)
    if not found:
        return ""
    return _SPACES.sub(" ", html_module.unescape(_TAG.sub(" ", found.groups()[-1]))).strip()


# 목록 카드 안의 자리들. 클래스 이름이 시맨틱하게 나뉘어 있어 그대로 쓴다.
#
# **마감일은 `date` 다.** `deadlines` 는 "2일 전 등록" 이라 마감일이 아니다 —
# 이름만 보고 골랐다가 등록 경과일을 마감일 칸에 넣을 뻔했다.
# **회사명은 `<a>` 일 수도 `<span>` 일 수도 있다.** 회사 정보 페이지가 없는 회사는
# 링크가 아니라 `<span class="str_tit">` 로 온다. `</a>` 만 찾으면 닫는 태그를 못 만나
# **공고 제목의 `</a>` 까지 삼킨다** — 실제로 122건 중 6건의 기업명에
# "관심기업 등록" 과 공고 제목이 붙어 나왔다. 그래서 연 태그와 같은 것으로 닫는다.
COMPANY = re.compile(
    r'class="col company_nm">.*?<(a|span)[^>]*class="str_tit"[^>]*>(.*?)</\1>', re.DOTALL)
TITLE = re.compile(r'<div class="job_tit">.*?<span>(.*?)</span>', re.DOTALL)
SECTOR = re.compile(r'<span class="job_sector">(.*?)</span>\s*(?:외)?\s*</span>', re.DOTALL)
WORKPLACE = re.compile(r'<p class="work_place">(.*?)</p>', re.DOTALL)
CAREER = re.compile(r'<p class="career">(.*?)</p>', re.DOTALL)
EDUCATION = re.compile(r'<p class="education">(.*?)</p>', re.DOTALL)
DEADLINE = re.compile(r'<span class="date">(.*?)</span>', re.DOTALL)


@dataclass
class Listings:
    rows: list[dict] = field(default_factory=list)
    pages: int = 0
    reported_total: int | None = None      # 페이지가 스스로 밝힌 총계
    stop_reason: str = ""

    @property
    def matches_reported_total(self) -> bool:
        """페이지가 밝힌 총계와 실제로 걷은 수가 같은가. 다르면 어딘가 흘렸다."""
        return self.reported_total is not None and len(self.rows) == self.reported_total


def real_listing_area(page: str) -> str:
    """광고를 걷어낸 목록 영역. 머리말이 없으면(2페이지부터) 페이지 전체다."""
    index = (page or "").find(ADS_END)
    return page[index:] if index >= 0 else (page or "")


def reported_total(page: str) -> int | None:
    """`전체 채용정보 N 건` 의 N. 다른 숫자를 잡는 정규식을 쓰면 헛값을 믿게 된다."""
    area = real_listing_area(page)
    found = TOTAL_COUNT.search(_SPACES.sub(" ", _TAG.sub(" ", area[:600])))
    return int(found.group(1).replace(",", "")) if found else None


def parse_listings(page: str) -> list[dict]:
    """목록 페이지 하나에서 공고들을 뽑는다. 광고는 뺀다."""
    area = real_listing_area(page)
    starts = [(m.group(1), m.start()) for m in LIST_ITEM.finditer(area)]
    rows = []
    for index, (rec_idx, start) in enumerate(starts):
        end = starts[index + 1][1] if index + 1 < len(starts) else len(area)
        block = area[start:end]
        rows.append({
            "rec_idx": rec_idx,
            "기업명": _text_of(block, COMPANY),
            "제목": _text_of(block, TITLE),
            "직무": _text_of(block, SECTOR),
            "근무지": _text_of(block, WORKPLACE),
            "경력": _text_of(block, CAREER),
            "학력": _text_of(block, EDUCATION),
            "마감일": _text_of(block, DEADLINE),
        })
    return rows


def fetch_listings(client, params: dict, *, max_pages: int = MAX_PAGES,
                   on_page=None) -> Listings:
    """끝까지 페이지를 넘기며 모은다. 중간에 실패해도 **앞서 모은 것은 돌려준다**."""
    result = Listings()
    seen: set[str] = set()
    for page_number in range(1, max_pages + 1):
        query = dict(params, **{PAGE_PARAM: page_number})
        try:
            page = client.get_html(LISTING_PATH, query)
        except Exception as error:                    # 여기서 죽으면 앞 페이지도 잃는다
            result.stop_reason = "%d페이지에서 실패: %s" % (page_number, error)
            return result
        result.pages = page_number
        if result.reported_total is None:
            result.reported_total = reported_total(page)

        rows = parse_listings(page)
        fresh = [row for row in rows if row["rec_idx"] not in seen]
        seen.update(row["rec_idx"] for row in fresh)
        result.rows.extend(fresh)
        if on_page:
            on_page(len(fresh))

        # 페이지가 밝힌 총계를 다 채웠으면 거기서 끝이다. 이게 **가장 분명한 신호**라
        # 먼저 본다 — 안 그러면 1페이지에 다 담기는 조건에서 사람인이 2페이지에도
        # 같은 것을 돌려주는 바람에 정상 종료가 "같은 페이지 반복 의심" 으로 보고된다.
        if result.reported_total and len(result.rows) >= result.reported_total:
            result.stop_reason = ("총계 %d건을 다 모았다 (%d페이지)"
                                  % (result.reported_total, page_number))
            return result
        if not rows:
            result.stop_reason = "%d페이지가 비었다" % page_number
            return result
        if not fresh:
            # 서버가 페이지 번호를 무시하고 같은 것을 다시 줬다는 뜻이기도 하다
            result.stop_reason = ("%d페이지에 새 공고가 없다 (같은 페이지 반복 의심)"
                                  % page_number)
            return result
    result.stop_reason = "상한 %d페이지에 닿았다" % max_pages
    return result


def fetch_detail(client, rec_idx: str) -> str:
    """상세 HTML.

    **`zf_user/jobs/view` 를 쓴다.** `jobs/relay/view` 는 본문 없는 JS 껍데기를 준다 —
    380KB 나 오지만 본문 섹션이 통째로 없어서, 잘 받은 줄 알기 딱 좋다.
    """
    return client.get_html(DETAIL_PATH, {"rec_idx": rec_idx},
                           referer="https://www.saramin.co.kr" + LISTING_PATH)
