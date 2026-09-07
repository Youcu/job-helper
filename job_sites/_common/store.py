"""수집 결과를 CSV 에 쌓는다. 사이트 공통.

파이프라인은 주기로 돈다. 그래서 매 실행이 파일을 갈아엎으면 안 된다.

  · 이번에 본 공고 → 내용을 최신으로 갱신하고 `최종확인일` 을 오늘로
  · 처음 본 공고   → 추가하고 `최초수집일` `최종확인일` 을 오늘로
  · 이번에 안 보인 공고 → 남겨 둔다. `최종확인일` 이 멈춰서 내려갔음이 드러난다.
    다만 **30일 넘게 안 보이면 뺀다** — 안 그러면 지난 공고가 끝없이 쌓인다

실제로 몇 시간 만에 공고 하나가 `status=close` 로 내려가는 것을 봤다. 덮어쓰기였다면
지원을 준비하던 공고가 흔적 없이 사라졌을 것이다.

쌓는 구조가 되면 쓰기 사고의 대가가 커진다. 덮어쓰기 시절에는 다시 돌리면 그만이었지만,
이제 파일 하나에 이력이 전부 들어 있다. 그래서 **원자적 쓰기**를 쓴다 — 임시 파일에 다 쓰고
나서 바꿔치기하므로, 도중에 죽어도 이전 파일이 남는다.

겹쳐 도는 실행을 막는 일은 `runlock.py` 가 맡는다.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

# 모든 채용 사이트가 이 순서로 쓴다. 사이트에 없는 값도 칸은 남기고 비운다.
COLUMNS = [
    "기업명",
    "마감일",
    "지원자격",
    "우대사항",
    "경력",
    "URL",
    "연봉",
    "기술스택",
    "근무지",
    "사이트명",
    "최초수집일",
    "최종확인일",
]

# 공고를 가리는 키 컬럼. 사이트가 달라도 URL 은 겹치지 않는다.
KEY_COLUMN = "URL"

FIRST_SEEN = "최초수집일"
LAST_SEEN = "최종확인일"

# 이만큼 안 보이면 뺀다. 내려간 공고를 영영 쌓아 두면 CSV 가 계속 불어나고,
# 지원할 수도 없는 공고가 지금 열려 있는 것과 섞인다.
RETENTION_DAYS = 30

@dataclass
class MergeResult:
    rows: list[dict]
    added: int          # 처음 본 공고
    updated: int        # 이번에도 보인 기존 공고
    unseen: int         # 이번에 안 보였지만 아직 보존 기간 안이라 남겨 둔 공고
    expired: int = 0    # 보존 기간이 지나 뺀 공고
    undated: int = 0    # 최종확인일을 알 수 없어 판단을 미룬 공고


def read_csv(path: Path) -> list[dict]:
    """쌓아 둔 CSV 를 읽는다. 없으면 빈 목록.

    컬럼이 늘어나기 전에 만든 파일도 읽는다 — 없는 칸은 빈 문자열로 채운다.
    """
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{column: (row.get(column) or "") for column in COLUMNS} for row in csv.DictReader(f)]


def _parse_day(value: str) -> date | None:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (AttributeError, ValueError):
        return None


def merge(
    existing: list[dict],
    fresh: list[dict],
    *,
    today: str | None = None,
    retention_days: int = RETENTION_DAYS,
) -> MergeResult:
    """쌓아 둔 것과 이번 수집을 공고 URL 기준으로 합친다.

    `retention_days` 넘게 안 보인 공고는 뺀다. 날짜를 알 수 없는 행(이력 컬럼이 없던
    시절 파일에서 올라온 것)은 **지우지 않는다** — 모르는 것을 오래됐다고 단정하면
    지울 이유가 없는 공고를 지운다. 다음 수집에서 그 공고가 보이면 날짜가 붙고,
    그때부터 정상적으로 세어진다.
    """
    today = today or date.today().isoformat()
    merged: dict[str, dict] = {}
    for row in existing:
        key = row.get(KEY_COLUMN)
        if key:
            merged[key] = dict(row)

    added = updated = 0
    for row in fresh:
        key = row.get(KEY_COLUMN)
        if not key:
            continue
        row = dict(row)
        previous = merged.get(key)
        if previous:
            updated += 1
            # 처음 본 날은 지키고, 내용은 최신으로 갈아 끼운다.
            row[FIRST_SEEN] = previous.get(FIRST_SEEN) or today
        else:
            added += 1
            row[FIRST_SEEN] = today
        row[LAST_SEEN] = today
        merged[key] = row

    kept, expired, undated = [], 0, 0
    cutoff = _parse_day(today)
    if cutoff is not None:
        cutoff = cutoff - timedelta(days=retention_days)
    for row in merged.values():
        last_seen = _parse_day(row.get(LAST_SEEN, ""))
        if last_seen is None:
            undated += 1            # 언제 마지막으로 봤는지 모른다 — 판단을 미룬다
            kept.append(row)
        elif cutoff is not None and last_seen < cutoff:
            expired += 1
        else:
            kept.append(row)

    # 최근에 확인된 것부터. 같은 날이면 새로 뜬 것이 위로.
    rows = sorted(
        kept,
        key=lambda r: (r.get(LAST_SEEN, ""), r.get(FIRST_SEEN, ""), r.get(KEY_COLUMN, "")),
        reverse=True,
    )
    return MergeResult(
        rows=rows,
        added=added,
        updated=updated,
        unseen=len(kept) - added - updated,
        expired=expired,
        undated=undated,
    )


def save(rows: list[dict], output: Path):
    """걷은 행을 기존 CSV 와 병합해 쓴다. 덮어쓰지 않고 쌓는다 (D-07)."""
    result = merge(read_csv(output), rows)
    write_csv(output, result.rows)
    return result


def write_csv(path: Path, rows: list[dict]) -> None:
    """원자적으로 쓴다. 도중에 죽어도 이전 파일은 그대로 남는다.

    임시 파일을 같은 디렉터리에 만든다 — 다른 파일시스템이면 `os.replace` 가 원자적이지 않다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    try:
        with tmp.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row.get(column, "") for column in COLUMNS})
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def merge_lines(result, retention_days: int = RETENTION_DAYS) -> list[str]:
    """병합 결과를 사람이 읽을 줄들로. **세 사이트가 똑같이 찍던 것**이다.

    `save()` 가 돌려주는 값의 짝이라 여기 둔다 — 세는 규칙이 바뀌면 찍는 말도 같이
    바뀌어야 하는데, 사이트마다 사본을 두면 한 곳만 고치고 지나가기 쉽다.

    0 인 항목은 줄을 만들지 않는다. 늘 찍으면 정상인 실행이 0 으로 가득 차 보인다.
    """
    lines = ["  새로 뜬 공고        : %d건" % result.added,
             "  이번에도 보인 공고  : %d건" % result.updated]
    if result.unseen:
        lines.append("  이번에 안 보인 공고 : %d건 (최종확인일을 그대로 둡니다)" % result.unseen)
    if result.expired:
        lines.append("  %d일 넘게 안 보여 뺀 공고: %d건" % (retention_days, result.expired))
    if result.undated:
        lines.append("  최종확인일을 알 수 없어 남겨 둔 공고: %d건" % result.undated)
    return lines
