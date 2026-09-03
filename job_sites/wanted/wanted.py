#!/usr/bin/env python3
"""Wanted 채용공고 스크래퍼.

    python3 wanted.py

`../../.env` 의 조건으로 공고를 전량 수집해 `csv/wanted_post.csv` 를 만든다.
조건 작성법과 코드표는 README.md 를 보라.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR.parent))

from _common.runlock import LockedError, run_lock
from _common.store import RETENTION_DAYS, merge, read_csv, write_csv
from lib.client import BlockedError, WantedClient
from lib.collect import build_listing_params, fetch_details, fetch_listings
from lib.config import ConfigError, load_config
from lib.record import to_row
from lib.filters import LocationError, job_groups, resolve_locations

ROOT = ROOT_DIR
OUTPUT = ROOT / "csv" / "wanted_post.csv"
LOCK = ROOT / "csv" / ".wanted.lock"


def main() -> int:
    # 파이프라인은 주기로 돈다. cron 이 겹쳐 두 실행이 같은 CSV 를 읽고-고치고-쓰면
    # 한쪽 결과가 조용히 사라진다.
    try:
        with run_lock(LOCK):
            return _run()
    except LockedError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 3


def _run() -> int:
    try:
        config = load_config()
        location_slugs, location_warnings = resolve_locations(config.home_locations)
    except (ConfigError, LocationError) as exc:
        print(f"설정 오류: {exc}", file=sys.stderr)
        return 1

    groups = job_groups()
    group_desc = ", ".join(f"{g}({groups.get(g, '?')})" for g in config.job_group_ids)
    career_desc = "전체" if config.yoe < 0 else ("신입" if config.yoe == 0 else f"{config.yoe}년차")
    print("수집 조건")
    print(f"  직군    : {group_desc}")
    print(f"  직무    : {', '.join(map(str, config.job_ids)) or '직군 전체'}")
    print(f"  경력    : {career_desc}")
    print(f"  근무지  : {', '.join(location_slugs)}")
    print(f"  고용형태: {', '.join(config.employment_types)}")
    for warning in location_warnings:
        print(f"  주의: {warning}")
    print()

    client = WantedClient()
    listings: dict[int, dict] = {}
    stop_reasons: list[str] = []
    try:
        for group_id in config.job_group_ids:
            params = build_listing_params(
                job_group_id=group_id,
                job_ids=config.job_ids,
                location_slugs=location_slugs,
                employment_type_keys=config.employment_type_keys,
                yoe=config.yoe,
            )
            label = f"{group_id}({groups.get(group_id, '?')})"
            rows, reason = fetch_listings(client, params, group_label=label)
            listings.update(rows)
            stop_reasons.append(f"{label}: {reason}")
    except BlockedError as exc:
        print(f"\n차단됨: {exc}", file=sys.stderr)
        return 2

    print("\n목록 수집 종료 사유")
    for reason in stop_reasons:
        print(f"  {reason}")

    if not listings:
        print("\n조건에 맞는 공고가 없습니다. .env 조건을 넓혀 보세요.")
        return 0

    print(f"\n공고 {len(listings)}건 (중복 제거 후). 상세를 가져옵니다.\n")
    details = fetch_details(client, sorted(listings))

    rows, broken = [], 0
    for job in details.values():
        try:
            rows.append(to_row(job))
        except ValueError:
            broken += 1      # 공고번호가 없어 URL 을 만들 수 없는 것

    # 태그에도 산문에도 기술 이름이 하나도 없는 공고는 뺀다. 개발 공고로 걸렀는데
    # 기술이 안 적힌 것이라 판단할 재료가 없다.
    kept = [r for r in rows if r["기술스택"]]
    dropped = len(rows) - len(kept)

    # 덮어쓰지 않고 쌓는다. 이번에 안 보인 공고도 바로 지우지 않는다 —
    # 마감돼 내려간 공고를 흔적 없이 잃으면 지원을 준비하던 것도 사라진다.
    # 다만 RETENTION_DAYS 넘게 안 보이면 뺀다.
    result = merge(read_csv(OUTPUT), kept)
    write_csv(OUTPUT, result.rows)

    print(f"\n{OUTPUT.relative_to(ROOT)} — 모두 {len(result.rows)}행")
    print(f"  새로 뜬 공고        : {result.added}건")
    print(f"  이번에도 보인 공고  : {result.updated}건")
    if result.unseen:
        print(f"  이번에 안 보인 공고 : {result.unseen}건 (최종확인일을 그대로 둡니다)")
    if result.expired:
        print(f"  {RETENTION_DAYS}일 넘게 안 보여 뺀 공고: {result.expired}건")
    if result.undated:
        print(f"  최종확인일을 알 수 없어 남겨 둔 공고: {result.undated}건")
    if dropped:
        print(f"  기술스택이 하나도 없어 제외: {dropped}건")
    if broken:
        print(f"  공고번호가 없어 제외: {broken}건")
    unused = []
    if config.tech_stacks:
        unused.append(f"TECH_STACKS({len(config.tech_stacks)}개)")
    if config.hope_annual_salary:
        unused.append(f"HOPE_ANNUAL_SALARY({config.hope_annual_salary})")
    if unused:
        print(
            f"  적용하지 않은 조건: {', '.join(unused)} — 현재는 조건에 맞는 공고를 "
            "거르지 않고 전량 수집합니다."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
