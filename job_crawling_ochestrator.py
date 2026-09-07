#!/usr/bin/env python3
"""여섯 채용 사이트를 한꺼번에 돌리고 결과를 합친다.

    python3 job_crawling_ochestrator.py

Wanted · 사람인 · 잡코리아 · 잡플래닛 · 점핏 · Pathsdog 를 **병렬로** 돌리고,
끝나면 각 사이트 CSV 를 그대로 이어 붙여 `csv/merged.csv` 를 만든다.

**사이트별 CSV 는 그대로 둔다.** 합친 파일은 사본이지 대체물이 아니다 — 어느 사이트에서
온 행인지는 `사이트명` 칸에 남아 있고, 한 사이트만 다시 돌리고 싶을 때는 그 사이트
스크래퍼를 따로 부르면 된다.

**전처리는 여기서 하지 않는다.** 중복 제거도, 정규화도, 거르기도 안 한다 — 그건 다음
단계의 일이다. 여기서 손대면 원본이 무엇이었는지 되짚을 수 없게 된다.

## 왜 프로세스를 나누나

각 스크래퍼는 자기 `lib/` 를 `sys.path` 맨 앞에 넣는다. 한 프로세스에서 여섯을 부르면
먼저 불린 사이트의 `lib.config` 가 캐시에 남아 뒤엣것이 그것을 쓴다 — 조용히 남의 조건으로
긁는다. 프로세스를 나누면 그럴 일이 없고, 하나가 죽어도 나머지가 산다.
"""
from __future__ import annotations

import csv
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SITES_DIR = ROOT_DIR / "job_sites"
OUTPUT = ROOT_DIR / "csv" / "merged.csv"

sys.path.insert(0, str(SITES_DIR))

from tqdm import tqdm                                        # noqa: E402

from _common.store import COLUMNS                            # noqa: E402

# 돌릴 사이트. **순서가 곧 화면에 뜨는 순서**이고, 합칠 때도 이 차례를 지킨다 —
# 실행마다 행 순서가 뒤바뀌면 `merged.csv` 를 눈으로 견주기 어렵다.
SITES = ("wanted", "saramin", "jobkorea", "jobplanet", "jumpit", "pathsdog")

# 한 사이트가 이보다 오래 걸리면 끊는다. 사람인이 8분대라 넉넉히 잡았다.
TIMEOUT_SECONDS = 60 * 30

# 실패한 사이트의 마지막 몇 줄을 보여 준다. 설정 오류 메시지가 여러 줄이라 넉넉히 잡았다.
MAX_ERROR_LINES = 8

# 스크래퍼가 약속한 종료 코드. **`4` 는 실패가 아니다** — 잡플래닛이 "조건이 넓어
# 이번엔 건너뛴다" 고 말하는 신호다. 실패로 세면 파이프라인 전체가 멎는다.
EXIT_MEANING = {
    0: ("정상", True),
    1: ("설정 오류", False),
    2: ("온전히 못 걷음 — 차단이거나 상세를 못 받음 (모은 것은 저장됨)", False),
    3: ("이미 돌고 있음", False),
    4: ("조건이 넓어 건너뜀", True),
}
UNKNOWN = ("알 수 없는 종료 코드", False)


@dataclass
class Result:
    site: str
    code: int | None = None
    seconds: float = 0.0
    rows: int = 0
    output: Path | None = None
    log: str = ""
    error: str = ""

    @property
    def meaning(self) -> str:
        return EXIT_MEANING.get(self.code, UNKNOWN)[0] if self.code is not None else self.error

    @property
    def ok(self) -> bool:
        """**실패가 아닌가.** 건너뛴 것(4)은 실패가 아니다."""
        return self.code is not None and EXIT_MEANING.get(self.code, UNKNOWN)[1]

    @property
    def stale(self) -> bool:
        """이번엔 못 걷었는데 CSV 는 남아 있는가.

        **그 행들은 지난 실행이 남긴 것**이다. 합치기는 하되(30일 누적이라 현재 상태의
        일부다) 이번에 걷은 것처럼 보이면 안 된다.
        """
        return not self.ok and self.rows > 0


def main() -> int:
    scrapers = _find_scrapers()
    missing = [site for site in SITES if site not in scrapers]
    if missing:
        print("스크래퍼를 못 찾았습니다: %s" % ", ".join(missing), file=sys.stderr)
        print("  job_sites/<사이트>/<사이트>.py 가 있어야 합니다.", file=sys.stderr)
        return 1

    print("여섯 사이트를 병렬로 돌립니다 — %s\n" % " · ".join(SITES))
    started = time.monotonic()
    results = _run_all(scrapers)
    elapsed = time.monotonic() - started

    merged = merge_csvs([r.output for r in results if r.output], OUTPUT)
    _print_report(results, merged, elapsed)

    failed = [r for r in results if not r.ok]
    if failed:
        _print_failures(failed)
        return 1
    return 0


def _print_failures(failed: list[Result]) -> None:
    """왜 실패했는지 **스크래퍼가 한 말을 그대로** 보여준다.

    "설정 오류" 라고만 하면 사람이 여섯 폴더를 뒤져야 한다. 스크래퍼는 어느 `.env` 항목을
    채워야 하는지까지 말해 주므로, 그 말을 여기로 끌어올린다.
    """
    print("\n%s" % ("=" * 62), file=sys.stderr)
    print("실패한 사이트 %d곳" % len(failed), file=sys.stderr)
    for result in failed:
        print("\n── %s (%s)" % (result.site, result.meaning), file=sys.stderr)
        for line in _last_lines(result.log, MAX_ERROR_LINES):
            print("   %s" % line, file=sys.stderr)


def _last_lines(text: str, count: int) -> list[str]:
    """진행 막대와 빈 줄을 빼고 **끝에서** 몇 줄. 오류는 대개 끝에 있다."""
    lines = []
    for raw in (text or "").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        if line.strip() and "|" not in line[:20]:      # tqdm 막대는 건너뛴다
            lines.append(line)
    return lines[-count:]


def _find_scrapers() -> dict[str, Path]:
    return {site: SITES_DIR / site / ("%s.py" % site)
            for site in SITES if (SITES_DIR / site / ("%s.py" % site)).exists()}


def _run_all(scrapers: dict[str, Path]) -> list[Result]:
    """여섯을 동시에 돌린다. **각자 다른 프로세스**라 서로를 못 건드린다.

    자식의 출력은 붙잡아 둔다 — 여섯이 동시에 tqdm 을 그리면 화면이 엉킨다. 대신 여기서
    막대 하나로 진행을 보이고, 끝난 사이트부터 한 줄씩 알린다.
    """
    results: dict[str, Result] = {}
    with ThreadPoolExecutor(max_workers=len(scrapers)) as pool:
        pending = {pool.submit(_run_one, site, path): site
                   for site, path in scrapers.items()}
        with tqdm(total=len(pending), desc="사이트", unit="곳") as bar:
            for future in as_completed(pending):
                result = future.result()
                results[result.site] = result
                bar.update(1)
                tqdm.write("  %s %-10s %6.1f초 · %s"
                           % ("✓" if result.ok else "✗", result.site,
                              result.seconds, _tail(result)))
    return [results[site] for site in SITES if site in results]


def _run_one(site: str, script: Path) -> Result:
    """스크래퍼 하나를 별도 프로세스로 돌린다."""
    result = Result(site=site)
    started = time.monotonic()
    try:
        done = subprocess.run(
            [sys.executable, script.name],
            cwd=script.parent, capture_output=True, text=True,
            timeout=TIMEOUT_SECONDS,
        )
        result.code = done.returncode
        result.log = (done.stdout or "") + (done.stderr or "")
    except subprocess.TimeoutExpired:
        result.error = "%d분을 넘겨 끊었습니다" % (TIMEOUT_SECONDS // 60)
    except Exception as error:                     # 여기서 죽으면 나머지 사이트도 잃는다
        result.error = "%s: %s" % (type(error).__name__, error)
    result.seconds = time.monotonic() - started

    # **이번에 걷은 수가 아니라 지금 CSV 에 있는 수**다. 사이트 CSV 는 30일 누적이라,
    # 이번 실행이 실패해도 앞서 걷어 둔 것이 남아 있다 — 그것도 "현재 상태" 의 일부라
    # 합치기는 하되, 이번에 걷은 것처럼 보이지 않게 화면에서 갈라 적는다.
    output = script.parent / "csv" / ("%s_post.csv" % site)
    if output.exists():
        result.output = output
        result.rows = count_rows(output)
    return result


def count_rows(path: Path) -> int:
    """CSV 의 **데이터 행** 수. 본문에 줄바꿈이 들어 있어 줄 수로 세면 안 된다."""
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return max(0, sum(1 for _ in csv.reader(handle)) - 1)
    except OSError:
        return 0


def merge_csvs(paths: list[Path], output: Path) -> int:
    """사이트별 CSV 를 **그대로** 이어 붙인다. 몇 행을 썼는지 돌려준다.

    **손대지 않는다** — 중복 제거도, 정규화도, 거르기도 안 한다. 그건 다음 단계의 일이고,
    여기서 손대면 원본이 무엇이었는지 되짚을 수 없게 된다.

    칸은 `_common/store.py` 의 `COLUMNS` 로 맞춘다. 여섯 사이트가 같은 스키마를 쓰지만,
    한 곳이 칸을 더하거나 빼도 합친 파일이 어긋나지 않게 여기서 한 번 더 맞춘다.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with output.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(COLUMNS))
        writer.writeheader()
        for path in paths:
            for row in _read_rows(path):
                writer.writerow({column: row.get(column, "") for column in COLUMNS})
                written += 1
    return written


def _read_rows(path: Path) -> list[dict]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError:
        return []


def _tail(result: Result) -> str:
    """한 줄 요약. 실패면 왜인지, 정상이면 몇 행인지.

    **이번에 못 걷었는데 CSV 가 남아 있으면 그렇게 밝힌다** — 안 그러면 실패한 사이트가
    행을 걷어 온 것처럼 보인다.
    """
    if result.code is None:
        return result.error or "알 수 없는 실패"
    if result.ok:
        return "%s · %d행" % (result.meaning, result.rows)
    if result.stale:
        return "%s (이번엔 못 걷음 · 지난 CSV %d행은 그대로 있음)" % (result.meaning, result.rows)
    return result.meaning


def _print_report(results: list[Result], merged: int, elapsed: float) -> None:
    print("\n%s" % ("=" * 62))
    print("%-10s %6s %8s %7s  %s" % ("사이트", "종료", "소요", "CSV행", "뜻"))
    for result in results:
        print("%-10s %6s %7.1f초 %6d  %s"
              % (result.site,
                 "-" if result.code is None else result.code,
                 result.seconds, result.rows, _tail(result)))
    print("%s" % ("-" * 62))
    print("%-10s %6s %7.1f초 %6d  %s"
          % ("합계", "", elapsed, sum(r.rows for r in results),
             "가장 오래 걸린 곳: %s (병렬이라 합이 아니다)"
             % max(results, key=lambda r: r.seconds).site))

    print("\n%s — %d행" % (OUTPUT.relative_to(ROOT_DIR), merged))
    print("  사이트별 CSV 는 그대로 두었습니다. 어느 사이트에서 왔는지는 `사이트명` 칸에 있습니다.")
    print("  **손대지 않고 그대로 이어 붙였습니다** — 중복 제거·정규화는 다음 단계의 일입니다.")

    stale = [r for r in results if r.stale]
    if stale:
        print("\n  이번에 못 걷은 사이트의 지난 CSV 도 합쳤습니다: %s"
              % ", ".join("%s %d행" % (r.site, r.rows) for r in stale))
        print("  사이트 CSV 는 30일 누적이라 그 행들도 현재 상태의 일부입니다.")
        print("  언제 걷힌 것인지는 `최종확인일` 칸을 보세요.")

    skipped = [r for r in results if r.code == 4]
    if skipped:
        print("\n  건너뛴 사이트: %s" % ", ".join(r.site for r in skipped))
        print("  실패가 아닙니다 — 조건이 넓어 절반만 걷힐 상황이라 아예 안 걷은 것입니다.")
        print("  조건을 좁히면 걷힙니다. 그 사이트의 README.md 를 보세요.")


if __name__ == "__main__":
    raise SystemExit(main())
