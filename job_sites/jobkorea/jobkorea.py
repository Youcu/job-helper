#!/usr/bin/env python3
"""잡코리아 채용공고 스크래퍼.

    python3 jobkorea.py

`../../.env` 의 조건으로 공고를 전량 수집해 `csv/jobkorea_post.csv` 를 만든다.
본문이 그림인 공고는 **읽지 않는다** — 그림 주소를 기술스택 칸에 남겨 "아직 안 읽었다"
는 표시만 한다. 읽는 것은 수집이 끝난 뒤 도는 별도 단계의 일이다 (D-13).
조건 작성법과 코드표는 README.md 를 보라.
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
from lib import body, record
from lib.client import BlockedError, JobKoreaClient
from lib.collect import fetch_body, fetch_detail, fetch_listings
from lib.config import load_config
from lib.filters import LocationError, build_conditions

OUTPUT = ROOT_DIR / "csv" / "jobkorea_post.csv"
LOCK = ROOT_DIR / "csv" / ".jobkorea.lock"


def main() -> int:
    # 파이프라인은 주기로 돈다. 겹쳐 돌면 두 실행이 같은 CSV 를 읽고-고치고-써서
    # 한쪽 결과가 조용히 사라진다. 자물쇠와 종료 코드는 `_common` 이 쥔다.
    return guarded(LOCK, _run)


def _run() -> int:
    try:
        config = load_config()
        conditions = build_conditions(config)
    except (ConfigError, LocationError) as error:
        print("설정 오류: %s" % error, file=sys.stderr)
        return 1

    _print_conditions(config, conditions)
    client = JobKoreaClient()

    with tqdm(desc="목록", unit="건") as bar:
        listings = fetch_listings(client, conditions, on_page=bar.update)
    print("\n목록 수집 종료: %s" % listings.stop_reason)
    if listings.reported_total is None:
        print("  총계를 못 읽었습니다 — 조용히 적게 걷혔는지 확인할 수단이 없습니다.")
    else:
        agree = "일치" if listings.matches_reported_total else "**불일치**"
        print("  사이트 표기 총계 %d건 / 수집 %d건 — %s"
              % (listings.reported_total, len(listings.rows), agree))
        if not listings.matches_reported_total:
            print("  목록 선택자가 바뀌었을 수 있습니다. lib/collect.py 의 ITEM 을 보세요.")
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


def _collect_details(client, listings: list[dict]):
    """상세와 본문을 받아 CSV 행으로.

    **차단되면 거기서 멈추되 앞서 모은 것은 돌려준다.** 재시도하면 차단만 깊어지므로
    더 던지지 않는다. 멈춘 사실은 `stats["차단"]` 으로 알린다.
    """
    rows: list[dict] = []
    ai_rows: list[dict] = []
    stats = {"그림본문": 0, "그림대기": 0, "기술없음": 0, "번호없음": 0,
             "구조화없음": 0, "차단": False}

    for listing in tqdm(listings, desc="상세", unit="건"):
        gno = str(listing.get("gno") or "").strip()
        if not gno:
            stats["번호없음"] += 1
            continue
        try:
            detail_html = fetch_detail(client, gno)
            body_html = fetch_body(client, gno)
        except BlockedError as error:
            tqdm.write("차단됨: %s" % error)
            stats["차단"] = True
            break
        except Exception as error:
            tqdm.write("  %s 상세 실패: %s" % (gno, error))
            continue

        if not record.job_posting(detail_html):
            # JSON-LD 가 없으면 목록 값으로 메운다. 드물지만 알려는 둔다.
            stats["구조화없음"] += 1

        # 그림 주소를 남기는 조건 둘 — ①본문이 그림뿐, ②글은 있는데 기술을 못 찾았다.
        # 그림 있는 공고가 대부분이라 아무 때나 남기면 기술스택 칸이 주소로 덮인다.
        is_image_body = body.looks_like_image_body(body_html)
        if is_image_body:
            stats["그림본문"] += 1
        row = record.to_row(listing, detail_html, body_html)
        if not row["기술스택"] or is_image_body:
            pending = body.image_urls(body_html)
            if pending:
                stats["그림대기"] += 1
                row = record.to_row(listing, detail_html, body_html, image_urls=pending)

        if not row["기술스택"]:
            # 기술도 그림도 없다. 판단할 재료가 아무것도 없는 공고다.
            stats["기술없음"] += 1
            continue
        rows.append(row)
    return rows, ai_rows, stats


def _print_conditions(config, conditions: dict) -> None:
    career = "전체" if config.yoe < 0 else ("신입" if config.yoe == 0 else "%d년차" % config.yoe)
    print("수집 조건")
    print("  직무    : %s" % ", ".join(map(str, config.job_ids)))
    print("  경력    : %s" % career)
    print("  학력    : %s" % (config.education or "(조건 없음)"))
    print("  근무지  : %s" % (", ".join(config.home_locations) or "전국"))
    print("  지역코드: %s" % (conditions.get("local") or "(지역 파라미터 없음 = 전국)"))
    print("  고용형태: %s" % ", ".join(config.employment_types))
    print()
    # 이 사이트에 대응 코드가 없어 못 건 역할. **조용히 빠지면 왜 결과가 적은지 못 찾는다.**
    if config.missing_roles:
        print("  ! 이 사이트에 없는 직무라 못 걸었습니다: " + ", ".join(config.missing_roles))
        print("    다른 사이트에서는 걷힙니다. tags/jobkorea_role_map.json 을 보세요.")
        print()


def _print_summary(config, result, ai_rows, stats) -> None:
    print("\n%s — 모두 %d행" % (OUTPUT.relative_to(ROOT_DIR), len(result.rows)))
    for line in merge_lines(result):
        print(line)
    if stats["그림본문"]:
        print("  본문이 그림인 공고   : %d건 (그중 주소를 남긴 것 %d건)"
              % (stats["그림본문"], stats["그림대기"]))
        print("    기술스택 칸에 http 로 시작하는 주소가 들어 있습니다 — 아직 안 읽었다는 뜻입니다.")
    if stats["구조화없음"]:
        print("  JSON-LD 가 없던 공고 : %d건 (목록 값으로 메웠습니다)" % stats["구조화없음"])
    if ai_rows:
        print("  %s — AI 가 관여한 %d행을 복사해 두었습니다"
              % (ai_csv_path(OUTPUT).relative_to(ROOT_DIR), len(ai_rows)))
    if stats["기술없음"]:
        print("  기술도 그림도 없어 제외: %d건" % stats["기술없음"])
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
        print("\n  적용하지 않은 조건: %s — 현재는 거르지 않고 전량 수집합니다."
              % ", ".join(unused))


if __name__ == "__main__":
    raise SystemExit(main())
