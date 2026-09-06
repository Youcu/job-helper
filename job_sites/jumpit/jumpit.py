#!/usr/bin/env python3
"""점핏 채용공고 스크래퍼.

    python3 jumpit.py

`../../.env` 의 조건으로 공고를 전량 수집해 `csv/jumpit_post.csv` 를 만든다.
**지역·경력·직무만 거른다** — 기술스택 필터는 이 사이트에서 오히려 독이다.
`Spring Boot` 를 고르면 아무것도 안 나오는데 그 필터를 풀고 공고를 열면 본문이
`Spring Framework` 를 요구한다. 자세한 근거는 README.md 를 보라.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR.parent))
sys.path.insert(0, str(ROOT_DIR))

from tqdm import tqdm

from _common.env import ConfigError
from _common.runlock import guarded
from _common.store import ai_csv_path, merge_lines, save
from lib import record
from lib.client import BlockedError, JumpitClient
from lib.collect import fetch_detail, fetch_listings
from lib.config import load_config
from lib.filters import LocationError, build_params

OUTPUT = ROOT_DIR / "csv" / "jumpit_post.csv"
LOCK = ROOT_DIR / "csv" / ".jumpit.lock"


def main() -> int:
    # 파이프라인은 주기로 돈다. 겹쳐 돌면 두 실행이 같은 CSV 를 읽고-고치고-써서
    # 한쪽 결과가 조용히 사라진다. 자물쇠와 종료 코드는 `_common` 이 쥔다.
    return guarded(LOCK, _run)


def _run() -> int:
    try:
        config = load_config()
        params = build_params(config)
    except (ConfigError, LocationError) as error:
        print("설정 오류: %s" % error, file=sys.stderr)
        return 1

    _print_conditions(config, params)
    client = JumpitClient()

    with tqdm(desc="목록", unit="건") as bar:
        listings = fetch_listings(client, params, on_page=bar.update)
    _print_listing_summary(listings)
    if not listings.rows:
        print("\n조건에 맞는 공고가 없습니다. .env 조건을 넓혀 보세요.")
        return 0

    rows, ai_rows, stats = _collect_details(client, listings.rows)
    result = save(rows, OUTPUT, ai_rows)
    _print_summary(config, result, ai_rows, stats)
    if stats["차단"]:
        print("\n차단돼서 %d건에서 멈췄습니다. 여기까지 모은 것은 저장했습니다."
              % len(rows), file=sys.stderr)
        return 2
    return 0


def _collect_details(client, positions: list[dict]):
    """상세를 받아 CSV 행으로.

    **차단되면 거기서 멈추되 앞서 모은 것은 돌려준다.** 재시도하면 차단만 깊어지므로
    더 던지지 않는다. 멈춘 사실은 `stats["차단"]` 으로 알린다.
    """
    rows: list[dict] = []
    ai_rows: list[dict] = []
    stats = {"기술없음": 0, "번호없음": 0, "상세실패": 0, "차단": False}

    for position in tqdm(positions, desc="상세", unit="건"):
        if not str(position.get("id") or "").strip():
            stats["번호없음"] += 1
            continue
        try:
            detail = fetch_detail(client, position["id"])
        except BlockedError as error:
            tqdm.write("차단됨: %s" % error)
            stats["차단"] = True
            break
        except Exception as error:
            tqdm.write("  %s 상세 실패: %s" % (position["id"], error))
            stats["상세실패"] += 1
            continue

        row = record.to_row(position, detail)
        if not row["기술스택"]:
            # 판단할 재료가 아무것도 없는 공고다.
            stats["기술없음"] += 1
            continue
        rows.append(row)
    return rows, ai_rows, stats


def _print_conditions(config, params: dict) -> None:
    career = "전체" if config.yoe < 0 else ("신입" if config.yoe == 0 else "%d년차" % config.yoe)
    print("수집 조건")
    print("  직무    : %s" % ", ".join(map(str, config.job_ids)))
    print("  경력    : %s" % career)
    print("  근무지  : %s" % (", ".join(config.home_locations) or "전국"))
    print("  지역코드: %s" % (", ".join(params.get("locationTag") or []) or "(지역 파라미터 없음 = 전국)"))
    print()
    # 조용히 무시하지 않는다 — 다른 사이트와 결과가 어긋난 이유를 나중에 찾을 수 있어야 한다.
    if config.tech_stacks:
        print("  ! 기술스택(%d개)은 **조건으로 걸지 않습니다.**" % len(config.tech_stacks))
        print("    이 사이트의 기술 필터는 공고 본문과 어긋납니다 — `Spring Boot` 를 고르면")
        print("    아무것도 안 나오는데, 그 필터를 풀고 공고를 열면 `Spring Framework` 를 요구합니다.")
    if config.unsupported_employment_types:
        print("  ! 고용형태 %s 는 **이 사이트에 필터가 없어 못 겁니다.**"
              % ", ".join(config.unsupported_employment_types))
    if config.education:
        print("  ! 학력(%s)은 **조건으로 걸지 않습니다** — 필터 파라미터가 없습니다."
              % config.education)
    if config.tech_stacks or config.unsupported_employment_types or config.education:
        print()


def _print_listing_summary(listings) -> None:
    print("\n목록 수집 종료: %s" % listings.stop_reason)
    if listings.reported_total is None:
        print("  총계를 못 읽었습니다 — 조용히 적게 걷혔는지 확인할 수단이 없습니다.")
    else:
        agree = "일치" if listings.matches_reported_total else "**불일치**"
        print("  사이트 표기 총계 %d건 / 받은 항목 %d건 — %s"
              % (listings.reported_total, listings.received, agree))
        if not listings.matches_reported_total:
            print("  목록 응답이 바뀌었을 수 있습니다. lib/collect.py 를 보세요.")
    if listings.duplicates:
        print("  고유 공고 %d건 (같은 공고가 여러 직무에 걸쳐 %d번 겹쳐 왔습니다)"
              % (len(listings.rows), listings.duplicates))


def _print_summary(config, result, ai_rows, stats) -> None:
    print("\n%s — 모두 %d행" % (OUTPUT.relative_to(ROOT_DIR), len(result.rows)))
    for line in merge_lines(result):
        print(line)
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
        print("  사람이 보고 tech_corpus.json / tech_aliases.json 로 옮겨 주세요.")

    unused = []
    if config.tech_stacks:
        unused.append("TECH_STACKS(%d개)" % len(config.tech_stacks))
    if config.hope_annual_salary:
        unused.append("HOPE_ANNUAL_SALARY")
    if unused:
        print("\n  적용하지 않은 조건: %s" % ", ".join(unused))
        print("  연봉은 이 사이트가 아예 주지 않습니다 (상세 43칸에 급여 필드가 없습니다).")


if __name__ == "__main__":
    raise SystemExit(main())
