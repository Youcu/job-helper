#!/usr/bin/env python3
"""**신입이라 적어 놓고 경력을 요구하는 공고**를 뺀다. 파이프라인의 마지막 거르기다.

    python3 career.py

    csv/merged_core.csv  ──▶  csv/merged_career.csv    남은 공고
                         +    csv/career_report.csv    뺀 이유 전량

## 왜 코드만으로 안 되나

낱말만 보면 못 가린다. 실측(2026-09-13, 66행):

    "경험이 있으신 분" · "능숙한 분" 까지 잡으면   42행(64%)이 걸린다
    재직 연수를 요구하는 말만 보면                 10행(15%)

**"경험" 과 "경력 연수" 는 다른 것이다** (2026-09-13 사용자). 신입도 프로젝트·학습으로
경험을 가진다. 모순인 것은 **재직 연수**를 요구할 때다.

그런데 연수로 좁혀도 뚫린다 — `경력직 지원자의 경우, 필요 시 레퍼런스 체크 진행 예정`
은 `경력직` 이 들어 있지만 **경력직도 받는다**는 말이지 요구가 아니다. 규칙을 아무리
더해도 다음 형태에서 또 뚫린다. 그래서 **좁히는 일은 코드가, 판정은 모델이** 한다
(`career_words.candidate`).

## 애매하면 **남긴다**

지우는 판단에 "모르겠으면 지운다" 는 없다 (2026-09-13 사용자). 놓친 공고는 사람이
목록에서 보고 넘기면 그만이지만, **지워진 공고는 있었다는 사실조차 안 남는다.**
그래서 모델에게도 애매하면 `false` 를 내라고 못 박고, 뺀 것은 전량 보고에 남긴다.

종료 코드
    0  정상
    1  `csv/merged_core.csv` 가 없거나 `claude` 명령을 못 찾음
    3  이미 돌고 있다
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SITES_DIR = ROOT_DIR / "job_sites"
INPUT = ROOT_DIR / "csv" / "merged_core.csv"
OUTPUT = ROOT_DIR / "csv" / "merged_career.csv"
REPORT = ROOT_DIR / "csv" / "career_report.csv"
CACHE = ROOT_DIR / "cache" / "career_judge.json"
LOCK = ROOT_DIR / "csv" / ".career.lock"

sys.path.insert(0, str(SITES_DIR))
sys.path.insert(0, str(ROOT_DIR))

from _common.runlock import guarded                                # noqa: E402
from _common.staleness import confirm, yes_given                   # noqa: E402
from _common.store import read_csv, write_csv, write_rows          # noqa: E402

import career_words                                                # noqa: E402

REPORT_COLUMNS = ("기업명", "공고명", "사이트명", "URL", "판정", "경력", "걸린줄", "근거")

MODEL = "sonnet"
TIMEOUT = 120

# **판정 규칙이 바뀌면 옛 판정을 버린다.** 프롬프트를 고쳐도 이미 판정된 공고가
# 캐시에서 그대로 나오면 고침이 영영 안 먹는다 — 실제로 그랬다. `또는`·`혹은` 뒤의
# 대체 경로를 읽으라는 지시를 넣었는데, 캐시에 든 12건은 옛 판정을 계속 냈다.
#
# 규칙(프롬프트)을 손대면 **이 숫자를 올려라.** 그러면 다음 실행이 다시 묻는다.
RULES_VERSION = 2


def build_prompt(row: dict, line: str) -> str:
    """모델에게 물을 말.

    **판정 기준을 프롬프트에 못 박는다.** 안 적으면 "경험이 있으신 분" 을 경력 요구로
    읽는다 — 처음에 제가 그렇게 읽었고, 사용자가 바로잡았다.
    """
    return (
        "채용공고 하나를 본다. 사이트는 이 공고를 **%s** 이라고 분류했다.\n"
        "그런데 지원자격에 이런 줄이 있다:\n"
        "    %s\n\n"
        "[지원자격 전문]\n%s\n\n"
        "물음: **이 공고는 사실상 재직 경력을 요구해서, 신입이 지원할 수 없는가?**\n\n"
        "판정 기준\n"
        "- `경력 3년 이상` · `5~10년 정도` 처럼 **재직 연수**를 요구하면 모순이다.\n"
        "- `개발 경험이 있으신 분` · `Spring 에 능숙한 분` 은 **역량**이지 경력이 아니다.\n"
        "  신입도 프로젝트·학습으로 가진다. 이런 것은 모순이 **아니다**.\n"
        "- **경력을 대신할 길이 함께 있으면 모순이 아니다.** `신입 또는 경력 3년` ·\n"
        "  `경력 3년 또는 이에 준하는 역량` · `석사 이상 또는 경력 3년` 이 그렇다.\n"
        "  `또는`·`혹은` 뒤를 반드시 읽어라 — 학위나 역량으로 대신할 수 있으면\n"
        "  신입도 지원할 수 있다.\n"
        "- `경력직 지원자의 경우 …` 처럼 경력직을 **받는다**는 말은 요구가 아니다.\n"
        "- **애매하면 false 를 내라.** 놓치는 것보다 멀쩡한 공고를 지우는 쪽이 나쁘다.\n\n"
        "아래 JSON 만 출력하고 다른 말은 하지 마라.\n"
        '{"모순": true 또는 false, "근거": "한 문장"}'
        % (row.get("경력") or "?", line, (row.get("지원자격") or "")[:1500])
    )


class JudgeError(RuntimeError):
    """우리가 못 물어봤다. **뺌 판정에 쓰면 안 된다.**"""


def _call(command: list[str], timeout: int) -> str:
    done = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                          stdin=subprocess.DEVNULL)
    if done.returncode != 0:
        raise JudgeError("claude 가 %d 로 끝났습니다: %s"
                         % (done.returncode, (done.stderr or "")[-300:]))
    return done.stdout or ""


def _first_object(text: str) -> dict:
    start = text.find("{")
    if start < 0:
        raise JudgeError("JSON 을 못 찾았습니다: %r" % text[:200])
    try:
        obj, _end = json.JSONDecoder().raw_decode(text, start)
    except ValueError as error:
        raise JudgeError("JSON 을 못 읽었습니다: %s" % error) from error
    return obj


def parse_output(text: str) -> tuple[bool, str]:
    """`claude -p --output-format json` 의 출력 → (모순인가, 근거).

    답은 두 겹이다 — 바깥이 `claude` 의 봉투, 안이 우리가 시킨 JSON.
    """
    answer = _first_object(text).get("result")
    if not isinstance(answer, str):
        raise JudgeError("답이 비었습니다: %r" % text[:200])
    body = _first_object(answer)
    return bool(body.get("모순")), str(body.get("근거") or "")[:200]


def judge(row: dict, line: str, *, model: str = MODEL, timeout: int = TIMEOUT,
          runner=None) -> tuple[bool, str]:
    """한 공고를 판정한다. 못 물어보면 `JudgeError`."""
    command = [shutil.which("claude") or "claude",
               "-p", build_prompt(row, line),
               "--model", model, "--output-format", "json"]
    try:
        return parse_output((runner or _call)(command, timeout))
    except JudgeError:
        raise
    except Exception as error:
        raise JudgeError("%s: %s" % (type(error).__name__, error)) from error


# ── 캐시 ────────────────────────────────────────────────────────────────
#
# **같은 공고를 두 번 물으면 답이 달라질 수 있다.** 재현성이 걸려 있으므로 URL 로
# 캐시한다. 그림 판독·평점이 이미 같은 방식이다.

def load_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}            # 깨져 있으면 버리고 새로 묻는다


def save_cache(path: Path, book: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".%s.tmp%d" % (path.name, os.getpid()))
    try:
        tmp.write_text(json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    assume_yes = yes_given(argv)
    return guarded(LOCK, lambda: _run(assume_yes=assume_yes))


def _run(source: Path | None = None, output: Path | None = None,
         report: Path | None = None, cache_path: Path | None = None, *,
         ask=None, have_claude: bool | None = None, assume_yes: bool = False) -> int:
    """바깥과 닿는 것을 전부 인자로 받는다 — 안 넘기면 진짜를 쓴다."""
    source = source if source is not None else INPUT
    output = output if output is not None else OUTPUT
    report = report if report is not None else REPORT
    cache_path = cache_path if cache_path is not None else CACHE

    if not source.exists():
        print("%s 가 없습니다. 먼저 핵심 기술 거르기까지 돌리세요." % source, file=sys.stderr)
        print("  python3 job_crawling_ochestrator.py", file=sys.stderr)
        return 1
    if not confirm(source, assume_yes=assume_yes):
        print("멈췄습니다 — 아무것도 안 바꿨습니다.", file=sys.stderr)
        return 1
    if not (shutil.which("claude") if have_claude is None else have_claude):
        print("claude 명령을 못 찾았습니다. 이 단계는 그것으로 판정합니다.", file=sys.stderr)
        print("  거르지 않고 통과시키면 **걸렀다고 믿는데 안 걸린 파일**을 받습니다.",
              file=sys.stderr)
        return 1

    rows = read_csv(source)
    book = load_cache(cache_path)
    asked = failed = 0
    kept, cut = [], []

    for row in rows:
        line = career_words.candidate(row)
        if not line:
            kept.append(row)                      # 후보가 아니다
            continue
        url = row.get("URL") or ""
        remembered = book.get(url)
        if remembered is not None and remembered.get("규칙판") == RULES_VERSION:
            bad, why = bool(remembered.get("모순")), remembered.get("근거", "")
        else:
            try:
                bad, why = (ask or judge)(row, line)
            except JudgeError as error:
                # **못 물어본 것을 모순으로 읽으면 안 된다.** 남긴다.
                failed += 1
                print("  %s 판정 실패: %s" % (url, error), file=sys.stderr)
                kept.append(row)
                continue
            asked += 1
            book[url] = {"모순": bad, "근거": why, "걸린줄": line,
                         "규칙판": RULES_VERSION, "판정일": date.today().isoformat()}
            save_cache(cache_path, book)          # 하나 끝날 때마다 — 중간에 죽어도 이어받는다
        (cut if bad else kept).append(row)

    write_csv(output, kept)
    _write_report(report, cut, book)
    _print(len(rows), asked, failed, kept, cut, source, output, report)
    return 0


def _write_report(path: Path, cut: list, book: dict) -> None:
    lines = [{"기업명": row.get("기업명", ""), "공고명": row.get("공고명", ""),
              "사이트명": row.get("사이트명", ""), "URL": row.get("URL", ""),
              "판정": "제외 · 사실상 경력 요구", "경력": row.get("경력", ""),
              "걸린줄": (book.get(row.get("URL", "")) or {}).get("걸린줄", ""),
              "근거": (book.get(row.get("URL", "")) or {}).get("근거", "")}
             for row in cut]
    write_rows(path, REPORT_COLUMNS, lines)


def _print(before: int, asked: int, failed: int, kept: list, cut: list,
           source: Path, output: Path, report: Path) -> None:
    print("\n물어본 공고 %d건 (캐시에서 바로 나온 것은 안 셉니다)" % asked)
    if failed:
        print("  판정 실패 %d건 — **남겼습니다.** 못 물어본 것을 모순으로 읽으면 안 됩니다."
              % failed)
    print("%s — %d행 (%s %d행에서 %d행 뺌)"
          % (_shown(output), len(kept), _shown(source), before, len(cut)))
    print("%s — %d행 (뺀 이유 전량)" % (_shown(report), len(cut)))


def _shown(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
