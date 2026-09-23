#!/usr/bin/env python3
"""걷은 공고에서 **버릴 것을 버린다.** 중복 제거 → 낱말 제외.

    python3 src/filter.py

    csv/merged_role.csv  →  csv/merged_filtered.csv   남은 공고
                            csv/filter_report.csv     **뺀 공고 전량 + 뺀 이유**

수집·병합·그림 판독은 원본을 지키는 일이라 아무것도 안 버린다. 그래서 같은 공고가 사이트
수만큼 행으로 들어오고, 지원할 생각이 없는 자리도 그대로 섞여 있다. 그것을 여기서 가른다.

**제자리에서 고치지 않는다.** 이 단계는 행을 없애므로, 입력을 덮어쓰면 없어진 행의 원본이
사라져 왜 없어졌는지 되짚을 수 없다.

**뺀 것은 전량 보고 CSV 로 나간다.** 낱말 규칙은 반드시 오탐을 낸다(`src/filter_words.py` 의
"이 표가 잡지 못하는 것"). 뺀 이유를 안 남기면 사람은 무엇을 잃었는지 영영 모른다.

종료 코드
    0  정상
    1  입력이 없다 — 먼저 수집을 돌려야 한다
    3  이미 돌고 있다 (`runlock.ALREADY_RUNNING`)
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR / "job_sites"))
sys.path.insert(0, str(SRC_DIR))

from paths import CACHE as CACHE_DIR, CSV, HISTORY as HISTORY_DIR  # noqa: E402
from paths import ROOT, SITES                                      # noqa: E402
INPUT = CSV / "merged_role.csv"
OUTPUT = CSV / "merged_filtered.csv"
REPORT = CSV / "filter_report.csv"
LOCK = CSV / ".filter.lock"


import career_words                                                # noqa: E402
import filter_words                                                # noqa: E402
from _common.env import ConfigError, csv_list, read_env             # noqa: E402
from _common.runlock import guarded                                # noqa: E402
from _common.staleness import confirm, yes_given                       # noqa: E402
from _common.store import (COLUMNS, FIRST_SEEN, LAST_SEEN, read_csv,
                           write_csv, write_rows)   # noqa: E402

# 본문이 가장 온전한 사본을 남기려고 재는 칸들. 사이트마다 같은 공고라도 본문을 얼마나
# 걷어 오는지가 다르다 — 실측으로 Wanted 는 API 원문을 통째로 주고, 사람인은 표 양식이면
# 절 구분이 어긋나 짧게 잘린다.
BODY_COLUMNS = ("지원자격", "우대사항", "기술스택")

REPORT_COLUMNS = ("기업명", "공고명", "사이트명", "URL", "판정", "걸린낱말", "근거")

# 경력 칸이 대놓고 경력직이라고 말하는 공고. 말 규칙은 `career_words` 에 있다 —
# 경력을 읽는 규칙이 두 군데로 갈리면 한쪽만 고치는 일이 생긴다.
#
# **여기서 빼는 이유는 순서다.** 이 단계는 `src/role.py` 바로 다음이고 평점·핵심 기술
# 앞이다. 경력직을 여기서 빼면 잡플래닛에 물어볼 회사와 모델에 물어볼 공고가 그만큼
# 준다. 실측(2026-09-22): `csv/merged_role.csv` 588행에서 23행.
CAREER_VERDICT = "제외 · 경력직"

# `.env` 항목 이름. `CORE_TECH_STACKS`(남길 것)의 반대다.
EXCLUDE_SETTING = "EXCLUDE_TECH_STACKS"


def weight(row: dict) -> int:
    """본문이 얼마나 들어 있는가. 큰 쪽을 남긴다."""
    return sum(len(row.get(column) or "") for column in BODY_COLUMNS)


def dedup(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """(남긴 행, 뺀 행). 키는 `filter_words.key` — 정규화한 기업명 + 공고명.

    **같은 사이트 안의 중복은 묶지 않는다.** 한 사이트가 같은 회사·같은 제목으로 두 번
    올렸다면 그것은 대개 부문이 다른 별개 공고다 (실측 2건). 사이트가 다를 때만 같은
    공고가 두 곳에 올라간 것으로 본다.

    묶을 때 **빈 칸만 채운다.** 값이 있는 칸은 덮지 않는다 — 사이트마다 표기가 달라
    덮으면 남긴 행의 원본이 무엇이었는지 사라진다. 날짜 두 칸만 예외로,
    `최초수집일` 은 가장 이른 것, `최종확인일` 은 가장 늦은 것을 쓴다.
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    order: list[tuple[str, str]] = []
    for row in rows:
        group_key = filter_words.key(row)
        if group_key not in groups:
            groups[group_key] = []
            order.append(group_key)
        groups[group_key].append(row)

    kept, dropped = [], []
    for group_key in order:
        group = groups[group_key]
        if len(group) == 1:
            kept.append(group[0])
            continue
        if not any(group_key):
            # **기업명과 공고명이 둘 다 비면 키가 없는 것이다.** 계약상 두 칸은 빌 수
            # 있으므로(`docs/convention/02-data-contract.md`) 이런 행끼리 묶으면
            # 아무 상관 없는 공고들이 한 행으로 뭉개진다. 판단할 재료가 없으면 안 묶는다.
            kept.extend(group)
            continue
        sites = [row.get("사이트명") for row in group]
        if len(set(sites)) != len(sites):
            kept.extend(group)          # 한 사이트에 두 번 — 다른 자리로 본다
            continue
        survivor = max(group, key=weight)
        for row in group:
            if row is not survivor:
                _fill_blanks(survivor, row)
                dropped.append((row, survivor))
        _stretch_dates(survivor, group)
        kept.append(survivor)
    return kept, dropped


def _fill_blanks(survivor: dict, other: dict) -> None:
    for column in COLUMNS:
        if not (survivor.get(column) or "").strip() and (other.get(column) or "").strip():
            survivor[column] = other[column]


def _stretch_dates(survivor: dict, group: list[dict]) -> None:
    firsts = [row.get(FIRST_SEEN) for row in group if (row.get(FIRST_SEEN) or "").strip()]
    lasts = [row.get(LAST_SEEN) for row in group if (row.get(LAST_SEEN) or "").strip()]
    if firsts:
        survivor[FIRST_SEEN] = min(firsts)
    if lasts:
        survivor[LAST_SEEN] = max(lasts)


def screen(rows: list[dict], excluded: list | None = None
           ) -> tuple[list[dict], list[tuple[dict, list]]]:
    """(남긴 행, [(뺀 행, 걸린 낱말들)]).

    세 가지로 뺀다. **보는 칸이 저마다 다르다.**

    | 무엇 | 보는 칸 | 정하는 곳 |
    |---|---|---|
    | 낱말 | `공고명`·`지원자격`·`우대사항` | `filter_words.BANNED` (코드) |
    | 기술 | `기술스택` | `.env` 의 `EXCLUDE_TECH_STACKS` |
    | 경력 | `경력` | `career_words.closed_to_newbie` (코드) |

    기술을 산문에서 보면 "PHP 경험 있으면 좋지만 필수 아님" 같은 문장에도 걸린다.
    낱말표를 `.env` 로 못 옮기는 이유는 `filter_words` 의 주석을 보라 — 낱말마다
    규칙이 달라 평문으로 표현할 수 없다.
    """
    excluded = excluded or []
    kept, dropped = [], []
    for row in rows:
        # **낱말은 여기서 안 자른다.** 같은 낱말이 정반대를 뜻한다 —
        # `단순 SI가 아닌` · `2,000개 이상의 고객사를 유치` · `보충역 지원 가능합니다`.
        # 탐지는 여기 규칙이 하고 **판정은 `src/nuance.py` 가 모델에게 묻는다**
        # (2026-09-22 사용자). 여기서 자르면 그 오탐이 조용히 삭제가 된다.
        hits = []
        techs = filter_words.excluded_techs(row, excluded)
        if techs:
            hits = hits + [(name, "기술스택") for name in techs]
        # **경력은 낱말과 같은 자루에 담되 이름을 달리 적는다.** 보고 CSV 에서
        # "낱말에 걸린 것" 과 "경력직이라 빠진 것" 이 눈으로 갈려야 한다.
        closed = career_words.closed_to_newbie(row.get("경력"))
        if closed:
            hits = hits + [("경력직", closed)]
        if hits:
            dropped.append((row, hits))
        else:
            kept.append(row)
    return kept, dropped


def main(argv: list[str] | None = None) -> int:
    assume_yes = yes_given(argv)
    return guarded(LOCK, lambda: _run(assume_yes=assume_yes))


def _run(source: Path = INPUT, output: Path = OUTPUT, report: Path = REPORT,
         env_path: Path | None = None, assume_yes: bool = False) -> int:
    """기본 경로를 인자로 받는 이유는 **테스트가 진짜 `csv/` 를 건드리지 않게** 하려는 것이다."""
    if not source.exists():
        print("%s 가 없습니다. 먼저 그림 판독까지 돌리세요." % source, file=sys.stderr)
        print("  python3 job_crawling_ochestrator.py    # 수집부터 전부", file=sys.stderr)
        print("  python3 src/job_image_process.py           # 그림 판독만", file=sys.stderr)
        return 1
    if not confirm(source, assume_yes=assume_yes):
        print("멈췄습니다 — 아무것도 안 바꿨습니다.", file=sys.stderr)
        return 1

    try:
        excluded = filter_words.build_excluded(
            csv_list(read_env(env_path).get(EXCLUDE_SETTING)))
    except ConfigError as error:
        print("설정 오류: %s" % error, file=sys.stderr)
        return 1

    rows = read_csv(source)
    unique, duplicated = dedup(rows)
    kept, banned = screen(unique, excluded)

    write_csv(output, kept)
    _write_report(report, duplicated, banned)
    _print(len(rows), len(duplicated), banned, len(kept), source, output, report,
           excluded)
    return 0


def _write_report(path: Path, duplicated: list, banned: list) -> None:
    """뺀 행을 전량 적는다. 리포트는 14칸 스키마가 아니라 `write_rows` 로 쓴다."""
    lines = []
    for row, survivor in duplicated:
        lines.append(_report_row(row, "제외 · 중복", "",
                                 "남긴 행: %s" % (survivor.get("URL") or "")))
    for row, hits in banned:
        # **판정을 갈라 적는다.** 경력직으로 빠진 것과 낱말에 걸린 것은 되짚는 방법이
        # 다르다 — 낱말은 오탐을 의심하며 보고, 경력직은 경력 칸을 보면 끝난다.
        verdict = (CAREER_VERDICT if any(name == "경력직" for name, _ in hits)
                   else "제외 · 낱말")
        lines.append(_report_row(
            row, verdict, ", ".join(name for name, _ in hits),
            " / ".join("%s «%s»" % (name, where) for name, where in hits)))

    write_rows(path, REPORT_COLUMNS, lines)


def _report_row(row: dict, verdict: str, words: str, why: str) -> dict:
    return {"기업명": row.get("기업명", ""), "공고명": row.get("공고명", ""),
            "사이트명": row.get("사이트명", ""), "URL": row.get("URL", ""),
            "판정": verdict, "걸린낱말": words, "근거": why}


def _print(before: int, duplicated: int, banned: list, after: int,
           source: Path, output: Path, report: Path, excluded: list) -> None:
    counts: dict[str, int] = {}
    for _, hits in banned:
        for name, _ in hits:
            counts[name] = counts.get(name, 0) + 1
    # **경력직은 따로 센다.** 낱말과 한 줄에 묶으면 규칙을 고쳤을 때 무엇이 움직였는지
    # 화면만 보고는 알 수 없다.
    by_career = sum(1 for _, hits in banned if any(n == "경력직" for n, _ in hits))
    print("  중복으로 뺌 : %d행" % duplicated)
    print("  낱말·기술로 뺌 : %d행" % (len(banned) - by_career))
    print("  경력직이라 뺌 : %d행" % by_career)
    if excluded:
        print("    기술 제외 기준: %s" % ", ".join(name for name, _ in excluded))
    else:
        # **비었으면 그렇게 말한다.** 안 말하면 걸렀다고 믿는다.
        print("    %s 가 비어 있어 기술로는 안 뺐습니다" % EXCLUDE_SETTING)
    if counts:
        print("    %s" % " · ".join(
            "%s %d" % (name, count)
            for name, count in sorted(counts.items(), key=lambda pair: -pair[1])))
    print("\n%s — %d행 (%s %d행에서 %d행 뺌)"
          % (_shown(output), after, _shown(source), before, before - after))
    print("%s — %d행 (뺀 이유 전량)" % (_shown(report), duplicated + len(banned)))


def _shown(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
