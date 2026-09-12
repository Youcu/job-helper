#!/usr/bin/env python3
"""**내가 쓸 기술**이 적힌 공고만 남긴다. `.env` 의 `CORE_TECH_STACKS` 가 기준이다.

    python3 core_stack.py

    csv/merged_rated.csv  →  csv/merged_core.csv        남은 공고
                             csv/core_stack_report.csv  **뺀 공고 전량 + 뺀 이유**

## 왜 세 칸을 다 보나

`기술스택` 칸만 보면 안 된다. **채용 사이트의 검색 조건에는 안 잡히는데 지원자격이나
우대사항에는 적혀 있는 공고가 있다** (2026-09-11 사용자 지적). 그래서 셋을 다 본다.

    기술스택 · 지원자격 · 우대사항  —  **어느 한 곳에라도 있으면 남긴다**

## 왜 마지막 단계인가

이건 걷는 조건이 아니라 **고르는 조건**이다. 수집기에 걸면 안 잡히는 공고를 아예 안
걷게 되고, 나중에 기준을 바꿔도 다시 걷기 전에는 알 수 없다. 걷어 둔 것을 마지막에
거르면 `.env` 한 줄을 고치고 다시 돌리기만 하면 된다.

## Spring 과 Spring Boot

`Spring Boot` 로 검색하면 잘 안 나와서 `.env` 에 `Spring` 이라고 적어 뒀다. 그런데
공고는 둘 중 아무 쪽으로나 적는다 — 실측 230행에서 `Spring` 57번 · `Spring Boot` 43번 ·
`Spring Framework` 11번 · `Spring Cloud` 2번 · `Spring Security` 2번 · `SpringBoot` 1번.

**둘은 서로를 잡는다** (사용자 지시).

    .env 에 `Spring`       → `Spring Boot` 가 적힌 공고도 남긴다
    .env 에 `Spring Boot`  → `Spring` 만 적힌 공고도 남긴다

앞쪽은 `Spring` 을 낱말로 찾으면 그대로 된다(`Spring Boot` 안에 `Spring` 이 낱말로 있다).
뒤쪽은 **적어 준 이름의 첫 낱말로도 함께 찾아서** 된다.

## 낱말로 찾는다 — 부분문자열이 아니다

    찾는다      Spring · Spring Boot · Spring/JPA · (Spring)
    안 찾는다   offspring · Springfield
    안 찾는다   `Java` 를 적었을 때의 `JavaScript`  ← **이것이 부분문자열의 함정이다**

앞뒤에 ASCII 영숫자가 붙지 않았을 때만 낱말로 본다. 한글은 경계로 치지 않는다 —
`Spring기반` 은 Spring 이다.

종료 코드
    0  정상
    1  입력이 없거나 `.env` 에 `CORE_TECH_STACKS` 가 없다
    3  이미 돌고 있다
"""
from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
INPUT = ROOT_DIR / "csv" / "merged_rated.csv"
OUTPUT = ROOT_DIR / "csv" / "merged_core.csv"
REPORT = ROOT_DIR / "csv" / "core_stack_report.csv"
LOCK = ROOT_DIR / "csv" / ".core_stack.lock"

sys.path.insert(0, str(ROOT_DIR / "job_sites"))
sys.path.insert(0, str(ROOT_DIR))

from _common.env import ConfigError, csv_list, read_env                 # noqa: E402
from _common.runlock import guarded                                    # noqa: E402
from _common.staleness import confirm, yes_given                          # noqa: E402
from _common.store import read_csv, write_csv                          # noqa: E402

SETTING = "CORE_TECH_STACKS"

# **사용자가 지정한 세 칸.** 위 "왜 세 칸을 다 보나" 를 보라.
TEXT_COLUMNS = ("기술스택", "지원자격", "우대사항")

REPORT_COLUMNS = ("기업명", "공고명", "사이트명", "URL", "판정", "기술스택")

# 걸린 이름 앞뒤로 이만큼을 보고에 함께 적는다.
CONTEXT = 24


def queries(name: str) -> list[str]:
    """이 이름으로 찾아 볼 것들. **적어 준 이름과 그 첫 낱말.**

    `Spring Boot` 를 적었으면 `Spring` 만 쓴 공고도 잡아야 한다 (사용자 지시).
    반대 방향은 따로 할 것이 없다 — `Spring` 을 낱말로 찾으면 `Spring Boot` 안의
    `Spring` 이 걸린다.

    첫 낱말이 한 글자면 안 쓴다. `C 언어` 를 적었다고 `C` 로 온 문서를 다 잡으면
    그건 찾는 것이 아니라 긁어 오는 것이다.
    """
    name = name.strip()
    if not name:
        return []
    found = [name]
    head = name.split()[0]
    if head.lower() != name.lower() and len(head) >= 2:
        found.append(head)
    return found


def pattern(name: str) -> re.Pattern[str]:
    """이름 하나를 **낱말로** 찾는 정규식.

    앞뒤에 ASCII 영숫자가 붙으면 다른 낱말이다 — `Java` 는 `JavaScript` 가 아니다.
    한글은 경계로 안 친다: `Spring기반` 은 Spring 이다.
    대소문자는 안 가린다 — 공고가 `spring boot` 라고도 적는다.
    """
    return re.compile(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(name),
                      re.IGNORECASE)


def build(wanted: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    """(적어 준 이름, 찾을 정규식) 들. 한 이름이 규칙 둘을 낳을 수 있다."""
    built = []
    for name in wanted:
        for query in queries(name):
            built.append((name, pattern(query)))
    return built


def text_of(row: dict) -> str:
    return "\n".join((row.get(column) or "") for column in TEXT_COLUMNS)


def hits(row: dict, rules: list) -> list[tuple[str, str]]:
    """(적어 준 이름, 걸린 자리의 글) 들. 하나도 없으면 빈 리스트."""
    text = text_of(row)
    found: dict[str, str] = {}
    for name, rule in rules:
        if name in found:
            continue
        match = rule.search(text)
        if match:
            start = max(0, match.start() - CONTEXT)
            end = min(len(text), match.end() + CONTEXT)
            found[name] = " ".join(text[start:end].split())
    return list(found.items())


def main(argv: list[str] | None = None) -> int:
    assume_yes = yes_given(argv)
    return guarded(LOCK, lambda: _run(assume_yes=assume_yes))


def _run(source: Path = INPUT, output: Path = OUTPUT, report: Path = REPORT,
         env_path: Path | None = None, assume_yes: bool = False) -> int:
    """경로를 인자로 받는 이유는 **테스트가 진짜 `csv/` 와 `.env` 를 안 건드리게** 하려는 것이다."""
    if not source.exists():
        print("%s 가 없습니다. 먼저 앞 단계까지 돌리세요." % source, file=sys.stderr)
        print("  python3 job_crawling_ochestrator.py", file=sys.stderr)
        return 1
    if not confirm(source, assume_yes=assume_yes):
        print("멈췄습니다 — 아무것도 안 바꿨습니다.", file=sys.stderr)
        return 1
    try:
        wanted = csv_list(read_env(env_path).get(SETTING))
    except ConfigError as error:
        print("설정 오류: %s" % error, file=sys.stderr)
        return 1
    if not wanted:
        print(".env 에 %s 가 비어 있습니다. 거를 기준이 없습니다." % SETTING, file=sys.stderr)
        print("  예) %s=Spring, FastAPI" % SETTING, file=sys.stderr)
        return 1

    rules = build(wanted)
    rows = read_csv(source)
    kept, cut = [], []
    for row in rows:
        found = hits(row, rules)
        (kept if found else cut).append((row, found))

    write_csv(output, [row for row, _found in kept])
    _write_report(report, cut)
    _print(wanted, rules, kept, cut, source, output, report)
    return 0


def _write_report(path: Path, cut: list) -> None:
    lines = [{"기업명": row.get("기업명", ""), "공고명": row.get("공고명", ""),
              "사이트명": row.get("사이트명", ""), "URL": row.get("URL", ""),
              "판정": "제외 · 핵심 기술 없음", "기술스택": row.get("기술스택", "")}
             for row, _found in cut]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".%s.tmp%d" % (path.name, os.getpid()))
    try:
        with tmp.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS,
                                    extrasaction="ignore")
            writer.writeheader()
            writer.writerows(lines)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _print(wanted: list, rules: list, kept: list, cut: list,
           source: Path, output: Path, report: Path) -> None:
    counts: dict[str, int] = {}
    for _row, found in kept:
        for name, _where in found:
            counts[name] = counts.get(name, 0) + 1
    print("%s = %s" % (SETTING, ", ".join(wanted)))
    print("  찾는 이름 : %s" % " · ".join(
        sorted({query for name in wanted for query in queries(name)})))
    for name, count in sorted(counts.items(), key=lambda pair: -pair[1]):
        print("  %-14s: %d행" % (name, count))
    print("\n%s — %d행 (%s %d행에서 %d행 뺌)"
          % (_shown(output), len(kept), _shown(source), len(kept) + len(cut), len(cut)))
    print("%s — %d행 (뺀 이유 전량)" % (_shown(report), len(cut)))


def _shown(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
