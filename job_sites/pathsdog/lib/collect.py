"""MCP 응답 글에서 공고를 읽어 내고, offset 으로 페이지를 넘긴다.

## 응답이 글이라 **개수 대조가 특히 중요하다**

서버가 첫 줄에 `이번 페이지 N개 채용공고:` 라고 말해 준다. 우리가 `[ID:n]` 으로 읽어 낸
개수를 그것과 매번 견준다 — **서식이 바뀌면 조용히 적게 읽히는데, 그때 여기서 드러난다.**
JSON 이었다면 필요 없었을 대조지만, 글을 파싱하는 이상 이게 유일한 안전망이다.

## 끝 판정

    다음 페이지: offset=30 으로 재검색     ← 더 있다
    (그 줄이 없다)                        ← 끝

`limit` 보다 적게 왔는지도 함께 본다. 신호 하나에만 기대면 서식이 바뀔 때 무한히 돈다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SEARCH_TOOL = "search_jobs"
DETAIL_TOOL = "get_job_detail"

# 한 번에 100개까지 받는다 (도구 스키마의 최대값).
PAGE_SIZE = 100
# 폭주 방지 상한. 100개씩 50번이면 5,000건이라 실제 규모보다 한참 넉넉하다.
MAX_PAGES = 50

# 목록 글에서 공고 한 덩이. `[ID:2565] ㈜네비웍스 - AI 서비스 백엔드 개발자(신입)`
ITEM = re.compile(r"^\[ID:(\d+)\]\s*(.*)$", re.MULTILINE)
# 서버가 말하는 개수. `이번 페이지 29개 채용공고:`
REPORTED = re.compile(r"이번 페이지\s*([\d,]+)\s*개")
# 다음 페이지가 있다는 신호. `다음 페이지: offset=30 으로 재검색`
HAS_NEXT = re.compile(r"다음 페이지:\s*offset=(\d+)")

_FIELD = "  %s: "


@dataclass
class Listings:
    rows: list[dict] = field(default_factory=list)
    pages: int = 0
    reported_total: int | None = None       # 서버가 말한 개수의 합
    stop_reason: str = ""

    @property
    def matches_reported_total(self) -> bool:
        """서버가 말한 개수만큼 읽어 냈는가.

        **글을 파싱하는 이상 이게 유일한 안전망이다.** 서식이 바뀌어 `[ID:n]` 을 못 잡으면
        조용히 적게 걷히는데, 그때 여기서 드러난다.
        """
        return self.reported_total is not None and len(self.rows) == self.reported_total


def parse_listing(text: str) -> list[dict]:
    """목록 글 → 공고 목록.

    한 덩이는 이렇게 생겼다 —

        [ID:2565] ㈜네비웍스 - AI 서비스 백엔드 개발자(신입)
          기술: Backend, AI/ML, Python
          경력: 신입 | 근무지: 경기도 안양시 … | 정규직 · 백엔드 개발
          마감: 2026-09-28
          Pathsdog 상세: https://…
        기업 원문: https://…

    회사와 제목은 ` - ` 로 갈린다. **회사 이름에 하이픈이 들어갈 수 있으므로 처음 하나만**
    쓴다 — `㈜네비웍스 - AI 서비스` 에서 뒤쪽 하이픈까지 나누면 제목이 잘린다.
    """
    marks = list(ITEM.finditer(text or ""))
    rows = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        block = text[mark.start():end]
        head = mark.group(2).strip()
        company, _, title = head.partition(" - ")
        rows.append({
            "id": mark.group(1),
            "기업명": company.strip() if title else "",
            "제목": (title or head).strip(),
            "기술": _line(block, "기술"),
            "조건": _line(block, "경력"),
            "마감": _line(block, "마감"),
            "상세주소": _link(block, "Pathsdog 상세"),
            "원문주소": _link(block, "기업 원문"),
        })
    return rows


def reported_count(text: str) -> int | None:
    """서버가 밝힌 이번 페이지 개수. 못 읽으면 None — 0 으로 속이지 않는다."""
    found = REPORTED.search(text or "")
    return int(found.group(1).replace(",", "")) if found else None


def has_next_page(text: str) -> bool:
    return bool(HAS_NEXT.search(text or ""))


def fetch_listings(client, arguments: dict, *, page_size: int = PAGE_SIZE,
                   max_pages: int = MAX_PAGES, on_page=None) -> Listings:
    """offset 을 올리며 끝까지 모은다. 중간에 실패해도 **앞서 모은 것은 돌려준다.**"""
    result = Listings()
    seen: set[str] = set()
    for page in range(max_pages):
        query = dict(arguments, limit=page_size, offset=page * page_size)
        try:
            text = client.call_tool(SEARCH_TOOL, query)
        except Exception as error:           # 여기서 죽으면 앞 페이지도 잃는다
            result.stop_reason = "%d번째 묶음에서 실패: %s" % (page + 1, error)
            return result
        result.pages = page + 1

        said = reported_count(text)
        if said is not None:
            result.reported_total = (result.reported_total or 0) + said
        arrived = [row for row in parse_listing(text) if row["id"] not in seen]
        seen.update(row["id"] for row in arrived)
        result.rows.extend(arrived)
        if on_page:
            on_page(len(arrived))

        if said == 0 or not parse_listing(text):
            result.stop_reason = "%d번째 묶음이 비었다" % (page + 1)
            return result
        if not has_next_page(text):
            result.stop_reason = ("서버가 다음 페이지를 안 알렸다 (%d묶음, %d건)"
                                  % (page + 1, len(result.rows)))
            return result
        if not arrived:
            result.stop_reason = "%d번째 묶음에 새 공고가 없다 (같은 묶음 반복 의심)" % (page + 1)
            return result
    result.stop_reason = "상한 %d묶음에 닿았다" % max_pages
    return result


def fetch_detail(client, job_id) -> str:
    """공고 상세 글. **원문 전체를 함께 받는다.**

    기본으로는 `[상세 내용]` 절이 빠지는데, 거기에 지원자격·우대사항의 원문이 있다.
    라벨 칸(`- 필수 기술:`)만으로는 전형 절차·제출 서류까지 섞여 들어온다.
    """
    return client.call_tool(DETAIL_TOOL,
                            {"job_id": int(job_id), "include_full_description": True})


def _line(block: str, label: str) -> str:
    """`  라벨: 값` 한 줄에서 값만."""
    for line in block.split("\n"):
        stripped = line.strip()
        if stripped.startswith(label + ":"):
            return stripped[len(label) + 1:].strip()
    return ""


def _link(block: str, label: str) -> str:
    found = re.search(re.escape(label) + r":\s*(\S+)", block)
    return found.group(1) if found else ""
