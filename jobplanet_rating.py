#!/usr/bin/env python3
"""회사 **평점**으로 거른다. 잡플래닛에서 걷어 오고, 2.9 미만·평점 없음·검색 안 됨을 뺀다.

    python3 jobplanet_rating.py

    csv/merged_filtered.csv  →  csv/merged_rated.csv    남은 공고
                                csv/rating_report.csv   **뺀 공고 전량 + 뺀 이유**
                                csv/same_names.csv      같은 이름이 여럿인 회사의 후보 전부
                                cache/company_rating.json   걷은 평점 (이어받기용)
                                cache/company_rating.log.jsonl  요청 로그 전량

사용자가 정한 선 (2026-09-11)

    검색됐는데 평점이 없거나(0.0) 2.9 미만이면  → 뺀다
    검색되지 않으면                            → 뺀다

## 왜 API 를 쓰나 — 사람용 검색 페이지는 못 쓴다

둘 다 실측했다 (2026-09-11, 각 40곳).

    /search/companies (HTML)   30곳 중 27번째에서 포기 · 403 51% · 111KB · 곳당 31.6초
    /api/v3/search/companies   40곳 전부 완주   · 403  4% ·   2KB · 곳당  6.6초

HTML 쪽은 403 이 나면 30→60→120→240→480→960초로 **악화되다 끝내 안 풀렸다.** API 쪽은
403 이 나도 **30초 한 번이면 늘 풀리고 악화되지 않는다.** 크기도 1/55 이고 값이 구조화돼
있어 사이트가 마크업을 바꿔도 안 깨진다.

## 안전 하한 — 5초. **403 을 0 으로 만들 수는 없다**

간격을 넓히면 403 이 사라질 줄 알았는데 아니었다. 실측:

    2.5초   403 14%   곳당 7.90초   457곳 60분
    5.0초   403  4%   곳당 6.61초   457곳 50분   ← 쓴다
    8.0초   403  6%   곳당 10.4초   457곳 79분

**8초가 5초보다 403 이 많다.** 간격만 보는 리미터가 아니라는 뜻이다 — 우리 요청 말고도
같은 문 앞에 다른 트래픽이 있다. 그러니 "403 이 안 나는 간격" 을 찾는 것은 헛일이다.

그래서 재현성의 근거를 **다른 데 둔다.** 403 이 나느냐가 아니라 **늘 같은 값으로 끝나느냐**다.
프로브 120곳에서 403 은 예외 없이 30초 한 번에 풀렸다. 그래서 이 불변을 코드로 못 박는다.

    한 질의가 BACKOFF_LIMIT 번 넘게 403 이면 **멈춘다.** 실측과 다른 일이 벌어진 것이고,
    거기서 더 두드리면 HTML 경로에서 본 악화가 시작된다.

멈춰도 잃는 것이 없다 — 회사 하나를 끝낼 때마다 캐시에 쓰므로 **다음 실행이 남은 곳부터
이어받는다.**

**작은 표본을 믿지 않기를 잘했다.** 프로브 120곳에서는 연속 실패가 한 번도 없었는데,
전량 457곳(요청 739건)에서는 **9건이 두 번 연속** 403 이었다. 3번 연속은 없었다.
상한을 2 로 뒀다면 그 9곳에서 실행이 멈췄을 것이다.

## 웹검색으로 이름을 찾아 주는 길은 **뒀다가 들어냈다**

변형을 다 써도 0건인 곳을 모델에게 넘겨 정식 상호를 찾게 했었다. 실측 59곳을 넘겨
8곳을 "되찾았는데" **그중 절반이 엉뚱한 회사**였다.

    바카티오(Vacatio) → 바티오(주)      평점 5.0 으로 4행이 통과했다. 이름부터 다르다
    에이아이씨엑스     → 마이리얼트립(주)  평점 3.6. 아무 관계가 없다

구조가 잘못돼 있었다. 코드는 **모델이 준 이름과 검색 결과가 같은지**만 봤고, 그 이름이
원래 회사와 같은 회사인지는 아무도 안 봤다. 모델이 자신 있게 엉뚱한 이름을 주면 그대로
통과한다.

**이 방향의 오류가 더 나쁘다.** 잘못 지운 것은 보고 CSV 에 남아 되짚을 수 있지만,
**잘못 통과한 것은 아무 표시 없이 결과에 섞인다** — 틀린 근거로 살아남은 공고를
사람이 알아볼 방법이 없다.

사용자의 판단으로 들어냈다 (2026-09-11): *"잘못된 데이터가 들어오느니 막는 게 맞고,
어차피 그렇게 해도 검색이 안 되는 곳이면 애초에 갈 곳이 못 된다."* 같은 이유로 끝내
못 찾은 51곳도 그대로 뺀다 — 신생 스타트업이라 아직 리뷰가 없을 뿐일 수도 있지만,
*"최소 1년 이상 근무할 곳인데 가능성에 도박하고 싶지 않다."*

종료 코드
    0  정상
    1  입력이 없다
    2  차단이 실측과 다르게 굴어 중간에 멈췄다 (**걷은 것은 저장됐다. 다시 돌리면 이어간다**)
    3  이미 돌고 있다
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
INPUT = ROOT_DIR / "csv" / "merged_filtered.csv"
OUTPUT = ROOT_DIR / "csv" / "merged_rated.csv"
REPORT = ROOT_DIR / "csv" / "rating_report.csv"
SAME_NAMES = ROOT_DIR / "csv" / "same_names.csv"
CACHE = ROOT_DIR / "cache" / "company_rating.json"
REQUEST_LOG = ROOT_DIR / "cache" / "company_rating.log.jsonl"
LOCK = ROOT_DIR / "csv" / ".jobplanet_rating.lock"

sys.path.insert(0, str(ROOT_DIR / "job_sites"))
sys.path.insert(0, str(ROOT_DIR))

import filter_words                                                # noqa: E402
from _common.runlock import guarded                                # noqa: E402
from _common.store import read_csv, write_csv                      # noqa: E402

# 사용자가 정한 선. **미만이면 뺀다** — 2.9 는 남는다.
MIN_RATING = 2.9

API_PATH = "/api/v3/search/companies"
BASE_URL = "https://www.jobplanet.co.kr"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    # 검색 페이지에서 부르는 것처럼 보여야 한다. `/job` 을 적으면 다른 화면의 호출이 된다.
    "Referer": BASE_URL + "/search/companies",
}

# 위 "안전 하한" 절을 보라. 5초는 실측으로 고른 값이지 짐작이 아니다.
MIN_INTERVAL = 5.0
TIMEOUT = 40
# 403 뒤 이만큼 쉰다. 실측에서 **한 번이면 예외 없이 풀렸다.**
BACKOFF = 30.0
# 한 질의에 이보다 많이 403 이면 멈춘다. 프로브(3회 × 40곳)에서는 연속 실패가 아예
# 없었지만, **전량 457곳에서는 9건이 두 번 연속이었다.** 2 로 뒀다면 거기서 멈췄다.
# 3번 연속은 아직 한 번도 못 봤으므로 그때는 실측과 다른 일이 벌어진 것으로 본다.
BACKOFF_LIMIT = 3

# 한 번에 받아 올 검색 결과 수. 동명 회사를 다 보려면 넉넉해야 한다 —
# `제일산업` 이 9건이었다. 20이면 실측 표본에서 잘린 적이 없다.
PAGE_SIZE = 20

REPORT_COLUMNS = ("기업명", "공고명", "사이트명", "URL", "판정", "평점",
                  "잡플래닛이름", "회사id", "찾은방법")
SAME_NAME_COLUMNS = ("기업명", "질의", "회사id", "잡플래닛이름", "평점",
                     "업종", "사원수", "업력", "공고수", "지역")

_LEGAL = re.compile(r"주식회사|㈜|\(주\)|\(유\)|\(재\)|\(사\)|유한책임회사|유한회사|\(株\)")
_PAREN = re.compile(r"\s*[\(（][^)）]*[\)）]")
_SPACES = re.compile(r"\s+")


# ── 이름 ────────────────────────────────────────────────────────────────

def tight(name: str) -> str:
    """법인 표기와 공백을 지운 형태. **괄호는 남긴다.**"""
    return _SPACES.sub("", _LEGAL.sub("", unicodedata.normalize("NFKC", name or ""))).lower()


def loose(name: str) -> str:
    """괄호 부가설명까지 지운 형태. `더즌(dozn)` 과 `더즌` 을 같게 본다."""
    return _SPACES.sub("", _PAREN.sub("", unicodedata.normalize("NFKC", name or "")
                                     .replace("㈜", ""))).replace("(주)", "").lower()


def variants(name: str) -> list[tuple[str, str]]:
    """(질의, 무슨 변형인지) 사다리. **앞에서 맞으면 뒤는 안 묻는다.**

    사용자가 실제로 겪은 것이라 넣었다 — 회사명을 그대로 넣으면 안 나오는 경우가 있다.
    실측으로도 확인했다: `바카티오(Vacatio)` 는 0건인데 `바카티오` 는 나온다.

    `(주)` 를 **붙이는** 변형도 둔다. 떼는 것만으로는 부족한 경우가 있다 —
    검색어가 너무 짧으면 엉뚱한 회사가 앞에 오고, 법인 표기가 붙으면 정확해진다.
    """
    raw = unicodedata.normalize("NFKC", (name or "").strip())
    bare = _SPACES.sub(" ", _LEGAL.sub("", raw)).strip(" -·,")
    no_paren = _SPACES.sub(" ", _PAREN.sub("", bare)).strip()
    inner = _PAREN.search(bare)
    ladder = [
        (raw, "원문"),
        (bare, "법인표기 제거"),
        (_SPACES.sub("", bare), "공백 제거"),
        (no_paren, "괄호 제거"),
        (_SPACES.sub("", no_paren), "괄호+공백 제거"),
        (inner.group().strip(" ()（）") if inner else "", "괄호 안쪽"),
        (no_paren.split(" ")[0] if " " in no_paren else "", "첫 어절"),
        ("(주)" + _SPACES.sub("", no_paren), "법인표기 추가"),
    ]
    seen, out = set(), []
    for query, how in ladder:
        query = query.strip()
        if len(query) >= 2 and query.lower() not in seen:
            seen.add(query.lower())
            out.append((query, how))
    return out


def matches(items: list[dict], query: str) -> list[dict]:
    """검색 결과에서 **이 회사라고 볼 수 있는 것들.**

    잡플래닛 검색은 부분 일치까지 준다 — `안랩` 을 물으면 `비안랩`·`시안랩`·`두리안랩`
    이 함께 온다. 그래서 **이름이 실제로 같은 것만** 고른다. 먼저 엄격하게(괄호까지
    보고) 맞춰 보고, 없으면 괄호를 뗀 형태로 한 번 더 본다.
    """
    strict = [it for it in items if tight(it.get("name")) == tight(query)]
    if strict:
        return strict
    return [it for it in items if loose(it.get("name")) == loose(query)]


def pick(found: list[dict]) -> dict:
    """같은 이름이 여럿이면 **가장 높은 평점**을 그 회사로 본다.

    공고에는 사업자번호도 주소도 없어서 어느 쪽인지 기계적으로 가릴 재료가 없다
    (`제일산업` 은 이름이 똑같은 곳이 넷이고 평점이 1.6·1.8·2.0·2.6 이었다).

    이 단계는 **행을 지우는 일**이라, 애매하면 남기는 쪽으로 기운다. 잘못 지우면 그
    공고가 있었다는 사실조차 안 남는다. 후보는 전량 `same_names.csv` 에 적어 두므로
    다음 단계가 공고명·자격조건·우대사항·기술스택으로 한 회사를 특정할 수 있다.
    """
    return max(found, key=lambda it: (it.get("rate_total_avg") or 0.0,
                                      it.get("company_headcounts") or 0))


# ── 그물 ────────────────────────────────────────────────────────────────

class Blocked(RuntimeError):
    """실측과 다르게 굴었다. **더 두드리지 않는다.**"""


class Searcher:
    """잡플래닛 회사 검색. 간격을 지키고, 던진 것을 전부 적는다."""

    def __init__(self, log_path: Path, *, min_interval: float = MIN_INTERVAL,
                 sleep=time.sleep, opener=None):
        self.min_interval = min_interval
        self._sleep = sleep
        self._opener = opener or urllib.request.urlopen
        self._last = 0.0
        self._started = time.monotonic()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = log_path.open("a", encoding="utf-8")
        self.requests = 0
        self.blocks = 0

    def close(self) -> None:
        self._log.close()

    def _write(self, entry: dict) -> None:
        entry["경과"] = round(time.monotonic() - self._started, 1)
        self._log.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._log.flush()      # 죽어도 거기까지는 남아야 다음에 읽을 수 있다

    def search(self, query: str, *, how: str = "") -> list[dict]:
        """검색 결과 items. 없으면 빈 목록. 차단이 실측과 다르면 `Blocked`."""
        url = BASE_URL + API_PATH + "?" + urllib.parse.urlencode(
            {"query": query, "page": 1, "page_size": PAGE_SIZE})
        for attempt in range(BACKOFF_LIMIT + 1):
            self._wait_turn()
            begin = time.monotonic()
            try:
                request = urllib.request.Request(url, headers=HEADERS)
                with self._opener(request, timeout=TIMEOUT) as response:
                    body = response.read()
                payload = json.loads(body)
                items = (payload.get("data") or {}).get("items") or []
                self.requests += 1
                self._write({"질의": query, "변형": how, "상태": 200,
                             "ms": int((time.monotonic() - begin) * 1000),
                             "바이트": len(body), "결과수": len(items)})
                return items
            except urllib.error.HTTPError as error:
                if error.code not in (403, 429):
                    self._write({"질의": query, "변형": how, "상태": error.code})
                    raise
                self.blocks += 1
                self._write({"질의": query, "변형": how, "상태": error.code,
                             "시도": attempt + 1, "백오프": BACKOFF})
                if attempt >= BACKOFF_LIMIT:
                    raise Blocked(
                        "한 질의(%r)가 %d번 연속 %d 였습니다.\n"
                        "  실측(2026-09-11, 3회 × 40곳)에서는 403 이 **예외 없이 30초 한 번에**\n"
                        "  풀렸습니다. 지금은 그때와 다른 일이 벌어진 것이라 멈춥니다 —\n"
                        "  더 두드리면 사람용 검색 페이지에서 본 악화(30→960초)가 시작됩니다.\n"
                        "  **걷은 것은 저장됐습니다. 몇 분 뒤 다시 돌리면 남은 곳부터 이어갑니다.**"
                        % (query, attempt + 1, error.code)) from error
                self._sleep(BACKOFF)
        return []

    def _wait_turn(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self.min_interval:
            self._sleep(self.min_interval - gap)
        self._last = time.monotonic()


# ── 한 회사 ──────────────────────────────────────────────────────────────

def look_up(searcher: Searcher, name: str) -> dict:
    """회사 하나의 평점 기록. 변형 사다리를 앞에서부터 써 보고 맞으면 멈춘다."""
    for query, how in variants(name):
        items = searcher.search(query, how=how)
        found = matches(items, query)
        if found:
            best = pick(found)
            return {"기업명": name, "질의": query, "찾은방법": how,
                    "회사id": best.get("company_id"),
                    "잡플래닛이름": best.get("name"),
                    "평점": best.get("rate_total_avg"),
                    "업종": best.get("industry_name"),
                    "사원수": best.get("company_headcounts"),
                    "업력": best.get("company_years"),
                    "공고수": best.get("posting_counts"),
                    "지역": best.get("city_name"),
                    "후보": [_slim(it) for it in found],
                    "확인일": date.today().isoformat()}
    return {"기업명": name, "질의": None, "찾은방법": "못 찾음", "회사id": None,
            "잡플래닛이름": None, "평점": None, "후보": [],
            "확인일": date.today().isoformat()}


def _slim(item: dict) -> dict:
    return {"회사id": item.get("company_id"), "잡플래닛이름": item.get("name"),
            "평점": item.get("rate_total_avg"), "업종": item.get("industry_name"),
            "사원수": item.get("company_headcounts"), "업력": item.get("company_years"),
            "공고수": item.get("posting_counts"), "지역": item.get("city_name")}


# ── 판정 ────────────────────────────────────────────────────────────────

def verdict(record: dict | None) -> str:
    if record is None or record.get("평점") is None:
        return "제외 · 잡플래닛에서 못 찾음"
    rating = record["평점"]
    if not rating:                      # 0.0 — 등록은 됐는데 평점이 없다
        return "제외 · 평점 없음"
    if rating < MIN_RATING:
        return "제외 · 평점 %.1f" % rating
    return "남김 · 평점 %.1f" % rating


def keeps(text: str) -> bool:
    return not text.startswith("제외")


# ── 캐시 ────────────────────────────────────────────────────────────────

def load_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def save_cache(path: Path, book: dict) -> None:
    """**회사 하나 끝날 때마다 부른다.** 원자적으로 쓴다 — 도중에 죽어도 앞것이 남는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".%s.tmp%d" % (path.name, os.getpid()))
    try:
        tmp.write_text(json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    return guarded(LOCK, _run)


def _run(source: Path = INPUT, output: Path = OUTPUT, report: Path = REPORT,
         same_names: Path = SAME_NAMES, cache: Path = CACHE,
         request_log: Path = REQUEST_LOG, searcher: Searcher | None = None) -> int:
    """경로를 인자로 받는 이유는 **테스트가 진짜 `csv/` 와 그물을 안 건드리게** 하려는 것이다."""
    if not source.exists():
        print("%s 가 없습니다. 먼저 거르기까지 돌리세요." % source, file=sys.stderr)
        print("  python3 job_crawling_ochestrator.py", file=sys.stderr)
        return 1

    rows = read_csv(source)
    book = load_cache(cache)
    wanted = _companies(rows)
    todo = [(key, name) for key, name in wanted.items() if key not in book]
    print("공고 %d행 · 회사 %d곳" % (len(rows), len(wanted)), flush=True)
    print("  캐시에 이미 있음 : %d곳" % (len(wanted) - len(todo)))
    print("  물어볼 곳       : %d곳  (간격 %.1f초 · 예상 %d분)"
          % (len(todo), MIN_INTERVAL, round(len(todo) * MIN_INTERVAL * 1.35 / 60)), flush=True)

    net = searcher or Searcher(request_log)
    stopped = False
    try:
        stopped = _collect(net, todo, book, cache)
    finally:
        save_cache(cache, book)
        if searcher is None:
            net.close()

    kept, cut, ambiguous = _judge(rows, book)
    write_csv(output, kept)
    _write_report(report, cut)
    _write_same_names(same_names, ambiguous)
    _print(len(rows), cut, len(kept), len(ambiguous), net, source, output, report, same_names)
    return 2 if stopped else 0


def _companies(rows: list[dict]) -> dict[str, str]:
    """키 → 사람이 읽을 대표 표기. **가장 긴 표기를 고른다** — 정보가 가장 많다."""
    best: dict[str, str] = {}
    for row in rows:
        name = (row.get("기업명") or "").strip()
        if not name:
            continue
        key = filter_words.company_key(name)
        if key and len(name) > len(best.get(key, "")):
            best[key] = name
    return best


def _collect(net: Searcher, todo: list, book: dict, cache: Path) -> bool:
    """**한 곳 끝날 때마다 캐시에 쓴다.** 돌아온 값은 "중간에 멈췄는가"."""
    missing = 0
    for index, (key, name) in enumerate(todo, 1):
        try:
            record = look_up(net, name)
        except Blocked as error:
            print("\n%s" % error, file=sys.stderr)
            print("  %d곳까지 걷었습니다 (%d곳 남음)." % (index - 1, len(todo) - index + 1),
                  file=sys.stderr)
            return True
        book[key] = record
        save_cache(cache, book)
        if record["평점"] is None:
            missing += 1
        if index % 25 == 0 or index == len(todo):
            print("  %d/%d곳 (요청 %d · 차단 %d · 못 찾음 %d)"
                  % (index, len(todo), net.requests, net.blocks, missing), flush=True)
    return False


def _judge(rows: list[dict], book: dict) -> tuple[list, list, list]:
    kept, cut, ambiguous = [], [], []
    seen_ambiguous = set()
    for row in rows:
        key = filter_words.company_key(row.get("기업명"))
        record = book.get(key)
        text = verdict(record)
        if keeps(text):
            kept.append(row)
        else:
            cut.append((row, text, record))
        if record and len(record.get("후보") or []) > 1 and key not in seen_ambiguous:
            seen_ambiguous.add(key)
            ambiguous.append(record)
    return kept, cut, ambiguous


def _write_report(path: Path, cut: list) -> None:
    lines = [{"기업명": row.get("기업명", ""), "공고명": row.get("공고명", ""),
              "사이트명": row.get("사이트명", ""), "URL": row.get("URL", ""),
              "판정": text,
              "평점": "" if not record or record.get("평점") is None else "%.1f" % record["평점"],
              "잡플래닛이름": (record or {}).get("잡플래닛이름") or "",
              "회사id": (record or {}).get("회사id") or "",
              "찾은방법": (record or {}).get("찾은방법") or ""}
             for row, text, record in cut]
    _write(path, REPORT_COLUMNS, lines)


def _write_same_names(path: Path, ambiguous: list) -> None:
    """같은 이름이 여럿인 회사의 **후보 전부.**

    지금은 가장 높은 평점을 그 회사로 보지만, 그것이 맞다는 근거는 없다. 다음 단계가
    공고명·지원자격·우대사항·기술스택으로 한 회사를 특정할 수 있게 재료를 남긴다 —
    업종·사원수·업력·공고수가 그 재료다.
    """
    lines = []
    for record in ambiguous:
        for candidate in record["후보"]:
            lines.append({"기업명": record["기업명"], "질의": record["질의"] or "",
                          "회사id": candidate.get("회사id") or "",
                          "잡플래닛이름": candidate.get("잡플래닛이름") or "",
                          "평점": "" if candidate.get("평점") is None else candidate["평점"],
                          "업종": candidate.get("업종") or "",
                          "사원수": candidate.get("사원수") or "",
                          "업력": candidate.get("업력") or "",
                          "공고수": candidate.get("공고수") or "",
                          "지역": candidate.get("지역") or ""})
    _write(path, SAME_NAME_COLUMNS, lines)


def _write(path: Path, columns: tuple, lines: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".%s.tmp%d" % (path.name, os.getpid()))
    try:
        with tmp.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(lines)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _print(before: int, cut: list, after: int, ambiguous: int, net: Searcher,
           source: Path, output: Path, report: Path, same_names: Path) -> None:
    counts: dict[str, int] = {}
    for _row, text, _record in cut:
        head = text.split(" · ")[0] + " · " + text.split(" · ")[1].split(" ")[0]
        counts[head] = counts.get(head, 0) + 1
    print()
    for head, count in sorted(counts.items(), key=lambda pair: -pair[1]):
        print("  %-22s: %d행" % (head, count))
    print("  요청 %d건 · 차단 %d건" % (net.requests, net.blocks))
    print("\n%s — %d행 (%s %d행에서 %d행 뺌)"
          % (_shown(output), after, _shown(source), before, before - after))
    print("%s — %d행 (뺀 이유 전량)" % (_shown(report), len(cut)))
    print("%s — 같은 이름이 여럿인 회사 %d곳" % (_shown(same_names), ambiguous))


def _shown(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
