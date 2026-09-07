#!/usr/bin/env python3
"""Pathsdog 채용공고 스크래퍼.

    python3 pathsdog.py

`../../.env` 의 조건으로 공고를 전량 수집해 `csv/pathsdog_post.csv` 를 만든다.

**다섯 사이트 중 유일하게 공식 인터페이스를 쓴다** — HTML 을 긁는 대신 MCP 서버
(`https://jobs.pathsdog.com/mcp`)의 `search_jobs` · `get_job_detail` 을 부른다.
근무지는 도구에 파라미터가 없어 **받은 뒤 우리가 거른다.** 자세한 근거는 README.md 를 보라.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR.parent))
sys.path.insert(0, str(ROOT_DIR))

from tqdm import tqdm

from _common.env import ConfigError
from _common.outcome import INCOMPLETE, incomplete
from _common.runlock import guarded
from _common.store import ai_csv_path, merge_lines, save
from lib import record
from lib.client import BlockedError, PathsdogClient
from lib.collect import fetch_detail, fetch_listings
from lib.config import load_config
from lib.filters import (LocationError, build_arguments, unknown_roles,
                         wanted_employments, wanted_locations)

OUTPUT = ROOT_DIR / "csv" / "pathsdog_post.csv"
LOCK = ROOT_DIR / "csv" / ".pathsdog.lock"


def main() -> int:
    # 파이프라인은 주기로 돈다. 겹쳐 돌면 두 실행이 같은 CSV 를 읽고-고치고-써서
    # 한쪽 결과가 조용히 사라진다. 자물쇠와 종료 코드는 `_common` 이 쥔다.
    return guarded(LOCK, _run)


def _run() -> int:
    try:
        config = load_config()
        arguments = build_arguments(config)
    except (ConfigError, LocationError) as error:
        print("설정 오류: %s" % error, file=sys.stderr)
        return 1

    places = wanted_locations(config.home_locations)
    jobtypes = wanted_employments(config)
    _print_conditions(config, arguments, places, jobtypes)
    client = PathsdogClient()

    with tqdm(desc="목록", unit="건") as bar:
        listings = fetch_listings(client, arguments, on_page=bar.update)
    _print_listing_summary(listings)
    if not listings.rows:
        print("\n조건에 맞는 공고가 없습니다. .env 조건을 넓혀 보세요.")
        return 0

    rows, ai_rows, stats = _collect_details(client, listings.rows, places, jobtypes)
    result = save(rows, OUTPUT, ai_rows)
    _print_summary(config, result, ai_rows, stats)
    if stats["차단"]:
        print("\n차단돼서 %d건에서 멈췄습니다. 여기까지 모은 것은 저장했습니다."
              % len(rows), file=sys.stderr)
        return 2
    if incomplete(stats, rows):
        # 걷은 것이 없는데 상세를 못 받은 것이 있다. 여기서 0 을 내면 화면에
        # `정상 · 0행` 이라고 찍혀, 사이트에 공고가 있는데도 없는 것처럼 보인다.
        print("\n걷은 것이 없습니다 — 상세를 %d건 물어봐서 %d건을 못 받았습니다.\n"
              "  목록은 %d건 받았으니 사이트가 아니라 상세 쪽 문제일 수 있습니다."
              % (stats["상세시도"], stats["상세실패"], len(listings.rows)),
              file=sys.stderr)
        return INCOMPLETE
    return 0


def _collect_details(client, listings: list[dict], places: list[str],
                     jobtypes: list[str]):
    """상세를 받아 CSV 행으로.

    **차단되면 거기서 멈추되 앞서 모은 것은 돌려준다.** 재시도하면 차단만 깊어지므로
    더 던지지 않는다. 멈춘 사실은 `stats["차단"]` 으로 알린다.
    """
    rows: list[dict] = []
    ai_rows: list[dict] = []
    stats = {"기술없음": 0, "번호없음": 0, "상세실패": 0, "상세시도": 0, "근무지밖": 0,
             "고용형태밖": 0, "차단": False}

    for listing in tqdm(listings, desc="상세", unit="건"):
        if not str(listing.get("id") or "").strip():
            stats["번호없음"] += 1
            continue
        stats["상세시도"] += 1
        try:
            detail = fetch_detail(client, listing["id"])
        except BlockedError as error:
            tqdm.write("차단됨: %s" % error)
            stats["차단"] = True
            break
        except Exception as error:
            # 열린 집합이라 종류를 세지 않는다 — `ToolError` 도 여기 든다.
            # 공고 하나 때문에 실행 전체가 죽으면 앞서 모은 것을 다 잃는다.
            tqdm.write("  %s 상세 실패: %s" % (listing["id"], error))
            stats["상세실패"] += 1
            continue

        row = record.to_row(listing, detail)
        # 서버가 못 거르는 둘을 여기서 거른다 — 지역은 파라미터가 없고, 고용형태는
        # 값 하나만 받아서 `정규직,인턴` 중 하나를 잃는다 (README 의 "우리가 거르는 것").
        if not record.matches_locations(row, places):
            stats["근무지밖"] += 1
            continue
        if not record.matches_employment(detail, jobtypes):
            stats["고용형태밖"] += 1
            continue
        if not row["기술스택"]:
            # 판단할 재료가 아무것도 없는 공고다.
            stats["기술없음"] += 1
            continue
        rows.append(row)
    return rows, ai_rows, stats


def _print_conditions(config, arguments: dict, places: list[str],
                      jobtypes: list[str]) -> None:
    career = "전체" if config.yoe < 0 else ("신입" if config.yoe == 0 else "%d년차" % config.yoe)
    print("수집 조건")
    print("  역할    : %s" % (", ".join(arguments.get("skills") or []) or "(전체)"))
    print("  경력    : %s%s" % (career, "  → %s" % arguments["experience_filter"]
                                if arguments.get("experience_filter") else ""))
    print("  근무지  : %s" % (", ".join(places) or "전국"))
    print("  고용형태: %s" % (", ".join(jobtypes) or "(조건 없음)"))
    print()
    # 이 사이트에 대응 코드가 없어 못 건 역할. **조용히 빠지면 왜 결과가 적은지 못 찾는다.**
    if config.missing_roles:
        print("  ! 이 사이트에 없는 직무라 못 걸었습니다: " + ", ".join(config.missing_roles))
        print("    다른 사이트에서는 걷힙니다. tags/pathsdog_role_map.json 을 보세요.")
        print()
    # 조용히 무시하지 않는다 — 다른 사이트와 결과가 어긋난 이유를 나중에 찾을 수 있어야 한다.
    if places:
        print("  ! 근무지는 **서버가 못 거릅니다** — 받은 뒤 근무지 글로 우리가 거릅니다.")
        print("    MCP search_jobs 에 지역 파라미터가 없습니다 (화면에는 있습니다).")
    strays = unknown_roles(config.job_ids)
    if strays:
        print("  ! 코드표에 없는 역할 이름: %s" % ", ".join(strays))
        print("    막지는 않습니다 — 이 사이트의 skills 는 닫힌 코드표가 아닙니다.")
        print("    다만 오타면 결과가 0건이 되니 확인해 보세요.")
    if jobtypes:
        print("  ! 고용형태도 **서버가 못 거릅니다** — 값 하나만 받아서 둘 이상이면")
        print("    나머지를 잃습니다. 받은 뒤 상세의 고용형태로 거릅니다.")
    if config.unsupported_employment_types:
        print("  ! 고용형태 %s 는 이 사이트에 없는 값입니다."
              % ", ".join(config.unsupported_employment_types))
    if config.education:
        print("  ! 학력(%s)은 **조건으로 걸지 않습니다** — 도구에 파라미터가 없습니다."
              % config.education)
    if config.tech_stacks:
        print("  ! 기술스택(%d개)은 조건으로 걸지 않습니다 — 전량 받아 본문에서 읽습니다."
              % len(config.tech_stacks))
    print()


def _print_listing_summary(listings) -> None:
    print("\n목록 수집 종료: %s" % listings.stop_reason)
    if listings.reported_total is None:
        print("  서버가 개수를 안 알렸습니다 — 조용히 적게 읽혔는지 확인할 수단이 없습니다.")
    else:
        agree = "일치" if listings.matches_reported_total else "**불일치**"
        print("  서버 표기 %d건 / 읽어 낸 %d건 — %s"
              % (listings.reported_total, len(listings.rows), agree))
        if not listings.matches_reported_total:
            print("  MCP 응답 서식이 바뀌었을 수 있습니다. lib/collect.py 의 ITEM 을 보세요.")


def _print_summary(config, result, ai_rows, stats) -> None:
    print("\n%s — 모두 %d행" % (OUTPUT.relative_to(ROOT_DIR), len(result.rows)))
    for line in merge_lines(result):
        print(line)
    if stats["근무지밖"]:
        print("  근무지가 조건 밖이라 제외: %d건" % stats["근무지밖"])
        print("    서버가 지역을 못 걸러서, 받은 뒤 근무지 글로 걸렀습니다.")
    if stats["고용형태밖"]:
        print("  고용형태가 조건 밖이라 제외: %d건" % stats["고용형태밖"])
    if ai_rows:
        print("  %s — AI 가 관여한 %d행을 복사해 두었습니다"
              % (ai_csv_path(OUTPUT).relative_to(ROOT_DIR), len(ai_rows)))
    if stats["기술없음"]:
        print("  기술스택이 하나도 없어 제외: %d건" % stats["기술없음"])
    if stats["상세실패"]:
        print("  상세를 못 받아 제외: %d건" % stats["상세실패"])
    if stats["번호없음"]:
        print("  공고번호가 없어 제외: %d건" % stats["번호없음"])

    candidates = ROOT_DIR.parent / "_common" / "corpus_candidates.json"
    if candidates.exists():
        print("\n  %s 에 표준 이름으로 못 푼 기술 이름이 쌓였습니다."
              % candidates.relative_to(ROOT_DIR.parent.parent))
        print("  이 사이트는 직무 이름(Backend 등)도 기술 칸에 넣어서 많이 올라옵니다.")

    unused = []
    if config.tech_stacks:
        unused.append("TECH_STACKS(%d개)" % len(config.tech_stacks))
    if config.hope_annual_salary:
        unused.append("HOPE_ANNUAL_SALARY")
    if unused:
        print("\n  적용하지 않은 조건: %s" % ", ".join(unused))


if __name__ == "__main__":
    raise SystemExit(main())
