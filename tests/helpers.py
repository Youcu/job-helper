"""오케스트레이터 테스트 공용 도구. 네트워크도 자식 프로세스도 타지 않는다."""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path


def temp_dir() -> Path:
    return Path(tempfile.mkdtemp())


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> Path:
    """사이트 하나가 낸 CSV 를 흉내 낸다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})
    return path


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class Failure(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


def check_equal(actual, expected, message: str = "") -> None:
    if actual != expected:
        raise Failure("%s\n      기대: %r\n      실제: %r" % (message, expected, actual))
