#!/usr/bin/env python3
"""파이프라인이 끝난 뒤 **이력을 쌓고 중간 부산물을 치운다.** 마지막 단계다.

    python3 history.py

    csv/merged_read.csv       ──누적──▶  history/history_read.csv        전처리 이전
    csv/merged_core.csv       ──누적──▶  history/history_core.csv        최종본
    리포트 셋                 ──누적──▶  history/history_dropped.csv     왜 빠졌나
    csv/same_names.csv        ──누적──▶  history/history_same_names.csv  동명 회사 후보
    job_sites/*/csv/*_post.csv  ──삭제──

## 왜 이런 모양인가

**사람이 보고 싶은 것은 지금 돌린 파이프라인의 결과**다. 그래서 `./csv` 에는 **이번 실행의
산출물만** 둔다 — 아홉 개를 지금 모양 그대로 남긴다. 분석용으로 쓸지 점검용으로 쓸지는
쓰는 사람이 정한다 (2026-09-12 사용자).

**이력은 `./history` 한 곳에서만 쌓는다.** 전에는 사이트별 CSV 다섯이 각자 누적 저장소였다
(`_common/store.save()` 가 기존 파일과 병합했다). 그 다섯을 지우면서 누적의 자리를 여기로
옮겼다 — 쌓이는 곳이 다섯이 아니라 하나가 되어 오히려 단순해진다.

## 사이트 CSV 를 지우면 무엇이 달라지나 — 그리고 어떻게 지켰나

사이트 CSV 가 누적 저장소였기 때문에, 그냥 지우면 두 가지를 잃는다.

    최초수집일 이 항상 오늘이 된다      → 칸의 뜻이 없어진다
    내려간 공고가 즉시 사라진다         → 지금은 30일 남는다

그래서 **오케스트레이터가 합칠 때 `history/history_read.csv` 에서 `최초수집일` 을 되살려
넣는다** (`job_crawling_ochestrator.py` 의 `_seed_first_seen`). 그래야 `./csv` 의 날짜 칸이
지금처럼 뜻을 지키고, "오늘 새로 뜬 공고" 를 여전히 가려낼 수 있다.

30일 보존은 `store.merge()` 가 `history_read.csv` 안에서 그대로 해 준다.

## 리포트 셋을 하나로 합치는 이유

세 리포트는 칸이 서로 다르다 — `filter_report` 는 `걸린낱말`, `rating_report` 는 `평점`·
`회사id`, `core_stack_report` 는 `기술스택`. 그런데 **공통 다섯 칸은 같다.**

세 파일로 나눠 쌓으면 "이 공고가 왜 빠졌나" 를 찾을 때 세 군데를 뒤져야 한다. 한 파일이면
URL 하나로 답이 나온다. 칸 구조가 온전한 원본은 `./csv` 에 그대로 있다.

## 안 하는 것

**`./csv` 를 건드리지 않는다.** 중간 산출물(`merged.csv`·`merged_filtered.csv` 등)도
그대로 둔다 — 사용자가 어떻게 쓸지 모르기 때문이다. 지우는 것은 **사이트별 CSV 뿐**이다.

종료 코드
    0  정상
    1  `csv/merged_read.csv` 나 `csv/merged_core.csv` 가 없다 (파이프라인이 안 끝났다)
    3  이미 돌고 있다
"""
from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
CSV_DIR = ROOT_DIR / "csv"
HISTORY_DIR = ROOT_DIR / "history"
SITES_DIR = ROOT_DIR / "job_sites"
LOCK = CSV_DIR / ".history.lock"

sys.path.insert(0, str(SITES_DIR))
sys.path.insert(0, str(ROOT_DIR))

from _common.runlock import guarded                                # noqa: E402
from _common.store import (COLUMNS, FIRST_SEEN, KEY_COLUMN,        # noqa: E402
                           merge, read_csv, write_csv, write_rows)

# 13칸 스키마 그대로 쌓는 둘. `store.merge()` 가 URL 키로 병합하고 30일 보존까지 한다.
SCHEMA_PAIRS = (
    ("merged_read.csv", "history_read.csv", "전처리 이전"),
    ("merged_core.csv", "history_core.csv", "기술 거르기까지"),
    # 경력 거르기가 뒤에 붙으면서 **최종본의 자리가 옮겨졌다.** `history_core.csv` 는
    # 이름이 가리키는 것(기술 거르기 결과)을 계속 쌓는다 — 이미 쌓인 것을 버리지
    # 않으려는 것이고, 두 파일을 견주면 경력 거르기가 무엇을 뺐는지도 보인다.
    ("merged_career.csv", "history_career.csv", "최종본"),
)

# 리포트 셋 → 한 파일. `(파일, 단계 이름, 근거로 쓸 칸들)`
REPORTS = (
    ("filter_report.csv", "거르기", ("걸린낱말", "근거")),
    ("rating_report.csv", "평점", ("평점", "잡플래닛이름", "회사id", "찾은방법")),
    ("core_stack_report.csv", "핵심기술", ("기술스택",)),
)
DROPPED = "history_dropped.csv"
DROPPED_COLUMNS = ("기록일", "단계", "기업명", "공고명", "사이트명", "URL", "판정", "근거")

SAME_NAMES = ("same_names.csv", "history_same_names.csv")
SAME_NAME_KEY = ("기업명", "회사id")


def _sift(rows: list[dict], columns: tuple, key) -> list[dict]:
    """키가 같으면 **나중 것을 남긴다.** 판정이 바뀌었으면 최신이 맞다."""
    seen: dict[tuple, dict] = {}
    for row in rows:
        seen[key(row)] = {column: row.get(column, "") for column in columns}
    return list(seen.values())


def _keep_earliest(rows: list[dict], fresh: list[dict]) -> None:
    """`최초수집일` 을 **둘 중 이른 쪽**으로 맞춘다.

    `store.merge()` 는 처음 보는 행의 `최초수집일` 을 **오늘로 덮는다.** 스크래퍼가
    날짜 없이 행을 주기 때문이고, 그 쪽에서는 맞다.

    그런데 이력에 들어오는 행은 `./csv` 에서 오므로 **이미 진짜 날짜를 갖고 있다.**
    그대로 두면 이력을 처음 만드는 날 **전부 오늘로 뭉개진다** — 실제로 그랬다.
    """
    origin = {row.get(KEY_COLUMN): (row.get(FIRST_SEEN) or "").strip()
              for row in fresh if row.get(KEY_COLUMN)}
    for row in rows:
        came = origin.get(row.get(KEY_COLUMN))
        mine = (row.get(FIRST_SEEN) or "").strip()
        if came and (not mine or came < mine):
            row[FIRST_SEEN] = came


def _read_any(path: Path) -> list[dict]:
    """칸 이름을 모르는 CSV 를 그대로 읽는다. `store.read_csv` 는 13칸에 묶여 있다."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def dropped_rows(csv_dir: Path, today: str) -> list[dict]:
    """리포트 셋을 한 모양으로 편다. 칸이 다른 나머지는 `근거` 한 칸에 글로 넣는다."""
    out = []
    for name, stage, extras in REPORTS:
        for row in _read_any(csv_dir / name):
            reason = " · ".join("%s=%s" % (column, row[column])
                                for column in extras
                                if (row.get(column) or "").strip())
            out.append({"기록일": today, "단계": stage,
                        "기업명": row.get("기업명", ""), "공고명": row.get("공고명", ""),
                        "사이트명": row.get("사이트명", ""), "URL": row.get("URL", ""),
                        "판정": row.get("판정", ""), "근거": reason})
    return out


def site_csvs(sites_dir: Path) -> list[Path]:
    """사이트별 수집본. **이것만 지운다.**"""
    return sorted(sites_dir.glob("*/csv/*_post.csv"))


def main() -> int:
    """**`argv` 를 안 받는다.** 다른 단계는 `--yes` 를 받지만 이 단계는 안 묻는다 —
    낡은 입력인지 물을 일이 없고(앞 단계가 방금 만든 파일이다), 받아 놓고 안 쓰면
    "무언가 줄 수 있다" 는 없는 사실을 말하게 된다.
    """
    return guarded(LOCK, _run)


def _run(csv_dir: Path = CSV_DIR, history_dir: Path = HISTORY_DIR,
         sites_dir: Path = SITES_DIR, today: str | None = None,
         sweep: bool = True) -> int:
    """경로를 인자로 받는 이유는 **테스트가 진짜 파일을 안 지우게** 하려는 것이다."""
    today = today or date.today().isoformat()
    missing = [name for name, _to, _why in SCHEMA_PAIRS if not (csv_dir / name).exists()]
    if missing:
        print("%s 가 없습니다. 파이프라인이 끝나지 않았습니다."
              % " · ".join(missing), file=sys.stderr)
        print("  python3 job_crawling_ochestrator.py", file=sys.stderr)
        return 1

    history_dir.mkdir(parents=True, exist_ok=True)
    lines = []

    for source, target, why in SCHEMA_PAIRS:
        path = history_dir / target
        fresh = read_csv(csv_dir / source)
        result = merge(read_csv(path), fresh, today=today)
        _keep_earliest(result.rows, fresh)
        write_csv(path, result.rows)
        lines.append("  %-26s %5d행 (새로 %d · %d일 넘어 뺌 %d) — %s"
                     % (target, len(result.rows), result.added,
                        30, result.expired, why))

    path = history_dir / DROPPED
    kept = _sift(_read_any(path) + dropped_rows(csv_dir, today),
                 DROPPED_COLUMNS, lambda r: (r.get("URL", ""), r.get("단계", "")))
    write_rows(path, DROPPED_COLUMNS, kept)
    lines.append("  %-26s %5d행 — 왜 빠졌나 (세 리포트를 합침)" % (DROPPED, len(kept)))

    source, target = SAME_NAMES
    fresh = _read_any(csv_dir / source)
    path = history_dir / target
    columns = tuple(fresh[0]) if fresh else tuple(_read_any(path)[0]) if _read_any(path) else ()
    if columns:
        kept = _sift(_read_any(path) + fresh, columns,
                     lambda r: tuple(r.get(c, "") for c in SAME_NAME_KEY))
        write_rows(path, columns, kept)
        lines.append("  %-26s %5d행 — 동명 회사 후보" % (target, len(kept)))

    swept = site_csvs(sites_dir)
    if sweep:
        for path in swept:
            path.unlink()

    print("history/ 에 쌓았습니다")
    for line in lines:
        print(line)
    print("\n사이트별 수집본 %d개를 지웠습니다 — 이력은 위에 쌓였습니다." % len(swept))
    print("%s 는 이번 실행 산출물 그대로 둡니다." % csv_dir.relative_to(ROOT_DIR)
          if csv_dir.is_relative_to(ROOT_DIR) else str(csv_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
