#!/usr/bin/env python3
"""잡플래닛 채용공고 스크래퍼.

    python3 jobplanet.py

`../../.env` 의 조건으로 **잡플래닛 자체 공고만** 수집해 `csv/jobplanet_post.csv` 를 만든다.
이 사이트 공고의 97%는 잡코리아 공고를 그대로 걸어 둔 것이고 본문이 아예 없어서, 그건
걸러 낸다 — 그 내용은 잡코리아 수집기가 이미 가져온다. 자세한 근거는 README.md 를 보라.
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
from lib.client import BlockedError, JobPlanetClient
from lib.collect import REQUEST_BUDGET, fetch_detail, fetch_listings
from lib.config import load_config
from lib.filters import LocationError, build_params

OUTPUT = ROOT_DIR / "csv" / "jobplanet_post.csv"
LOCK = ROOT_DIR / "csv" / ".jobplanet.lock"

# 조건이 넓어 전부 못 걷을 때 내는 코드. **실패가 아니라 "이번엔 건너뛴다" 는 뜻**이라
# 다른 코드와 섞으면 안 된다 — 오케스트레이터가 이 사이트만 빼고 나머지를 계속 돌린다.
SKIPPED = 4


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
    client = JobPlanetClient()

    with tqdm(desc="목록", unit="건") as bar:
        listings = fetch_listings(client, params, on_page=bar.update)
    _print_listing_summary(listings)
    if not listings.fits_budget():
        _print_skip_notice(listings)
        return SKIPPED
    if not listings.rows:
        print("\n조건에 맞는 **자체 공고**가 없습니다. 조건을 넓혀 보세요.")
        return 0

    rows, ai_rows, stats = _collect_details(client, listings.rows, config)
    result = save(rows, OUTPUT, ai_rows)
    _print_summary(config, result, ai_rows, stats, listings)
    if stats["차단"]:
        print("\n차단돼서 %d건에서 멈췄습니다. 여기까지 모은 것은 저장했습니다."
              % len(rows), file=sys.stderr)
        return 2
    return 0


def _collect_details(client, postings: list[dict], config):
    """상세를 받아 CSV 행으로.

    **차단되면 거기서 멈추되 앞서 모은 것은 돌려준다.** 재시도하면 차단만 깊어지므로
    더 던지지 않는다. 멈춘 사실은 `stats["차단"]` 으로 알린다.
    """
    rows: list[dict] = []
    ai_rows: list[dict] = []
    stats = {"기술없음": 0, "번호없음": 0, "근무지밖": 0, "본문없음": 0, "차단": False}

    for posting in tqdm(postings, desc="상세", unit="건"):
        if not str(posting.get("id") or "").strip():
            stats["번호없음"] += 1
            continue
        try:
            detail = fetch_detail(client, posting["id"])
        except BlockedError as error:
            tqdm.write("차단됨: %s" % error)
            stats["차단"] = True
            break
        except Exception as error:
            tqdm.write("  %s 상세 실패: %s" % (posting["id"], error))
            continue

        row = record.to_row(posting, detail)
        # 지역 코드가 시도까지밖에 없어서 여기서 다시 거른다 (README 의 "근무지" 절).
        if not record.matches_locations(row, config.home_locations):
            stats["근무지밖"] += 1
            continue
        if not row["지원자격"] and not row["우대사항"]:
            # 자체 공고인데 본문이 비었다. 드물지만 알려는 둔다.
            stats["본문없음"] += 1
        if not row["기술스택"]:
            # 판단할 재료가 아무것도 없는 공고다.
            stats["기술없음"] += 1
            continue
        rows.append(row)
    return rows, ai_rows, stats


def _print_skip_notice(listings) -> None:
    """조건이 넓어 물러난다. **상세를 한 건도 받지 않았고 CSV 도 안 건드렸다.**

    반쯤 걷느니 아예 안 걷는다 — 절반만 든 CSV 는 "이 조건에 공고가 이만큼" 이라는
    거짓을 만들고, 다음 실행에서 나머지가 채워진다는 보장도 없다.
    """
    print("\n조건이 넓어 **이번에는 잡플래닛을 건너뜁니다.** (종료 코드 %d)" % SKIPPED)
    if listings.over_budget:
        print("  목록만으로도 예산을 넘겨서, 목록조차 끝까지 훑지 않았습니다.")
    else:
        print("  끝까지 걷으려면 요청 %d개(목록 %d + 상세 %d)가 필요한데, 이 사이트가"
              % (listings.planned_requests, listings.pages, len(listings.rows)))
        print("  한 번에 견디는 것은 %d개쯤입니다 — 중간에 403 이 나서 절반만 걷힙니다."
              % REQUEST_BUDGET)
    print("  **CSV 는 건드리지 않았습니다.** 상세도 한 건도 받지 않았습니다.")
    print("\n  조건을 좁히면 걷힙니다 — 직무를 줄이거나(JOB_ROLES),")
    print("  경력·지역을 좁히세요. 왜 이런 제약이 있는지는 README.md 의 '차단' 절에 있습니다.")


def _print_conditions(config, params: dict) -> None:
    career = "전체" if config.yoe < 0 else ("신입" if config.yoe == 0 else "%d년차 이하" % config.yoe)
    print("수집 조건")
    print("  직무    : %s" % ", ".join(map(str, config.job_ids)))
    print("  경력    : %s%s" % (career, "  (%s)" % params["years_of_experience"]
                                if params.get("years_of_experience") else ""))
    print("  근무지  : %s" % (", ".join(config.home_locations) or "전국"))
    print("  지역코드: %s" % (params.get("city") or "(지역 파라미터 없음 = 전국)"))
    print("  고용형태: %s" % (", ".join(config.employment_types) or "(조건 없음)"))
    print()
    # 이 사이트에 대응 코드가 없어 못 건 역할. **조용히 빠지면 왜 결과가 적은지 못 찾는다.**
    if config.missing_roles:
        print("  ! 이 사이트에 없는 직무라 못 걸었습니다: " + ", ".join(config.missing_roles))
        print("    다른 사이트에서는 걷힙니다. tags/jobplanet_role_map.json 을 보세요.")
        print()
    # 조용히 무시하지 않는다 — 다른 사이트와 결과가 어긋난 이유를 나중에 찾을 수 있어야 한다.
    if config.education:
        print("  ! 학력(%s)은 **조건으로 걸지 않습니다.**" % config.education)
        print("    자체 공고의 84%가 '학력무관'으로 등록돼 있어, 걸면 대부분이 사라집니다")
        print("    (실측: 백엔드·서울경기·정규직에서 자체 공고 37건 → 6건).")
    if config.unsupported_employment_types:
        print("  ! 고용형태 %s 는 **이 사이트에 코드가 없어 못 겁니다.**"
              % ", ".join(config.unsupported_employment_types))
        print("    잡플래닛 고용형태는 정규직·계약직 둘뿐입니다.")
    if config.education or config.unsupported_employment_types:
        print()


def _print_listing_summary(listings) -> None:
    print("\n목록 수집 종료: %s" % listings.stop_reason)
    if listings.reported_total is None:
        print("  총계를 못 읽었습니다 — 조용히 적게 걷혔는지 확인할 수단이 없습니다.")
    else:
        agree = "일치" if listings.matches_reported_total else "**불일치**"
        print("  사이트 표기 총계 %d건 / 훑은 공고 %d건 — %s"
              % (listings.reported_total, listings.seen, agree))
        if not listings.matches_reported_total and not listings.hit_window_limit:
            print("  목록 응답이 바뀌었을 수 있습니다. lib/collect.py 를 보세요.")
    if listings.hit_window_limit:
        print("  ! 1만 건 창에 닿았습니다 — 잡플래닛은 1만 번째 너머를 안 줍니다.")
        print("    조건을 좁혀 나눠 돌리세요 (직무를 쪼개거나 지역을 나눕니다).")
    print("  자체 공고 %d건 · 잡코리아 중계라 걸러낸 것 %d건"
          % (len(listings.rows), listings.relayed))


def _print_summary(config, result, ai_rows, stats, listings) -> None:
    print("\n%s — 모두 %d행" % (OUTPUT.relative_to(ROOT_DIR), len(result.rows)))
    for line in merge_lines(result):
        print(line)
    if stats["근무지밖"]:
        print("  근무지가 조건 밖이라 제외: %d건" % stats["근무지밖"])
        print("    잡플래닛 지역 코드는 시도까지라, 넓게 받아 근무지 글로 다시 걸렀습니다.")
    if stats["본문없음"]:
        print("  자체 공고인데 본문이 빈 것: %d건" % stats["본문없음"])
    if ai_rows:
        print("  %s — AI 가 관여한 %d행을 복사해 두었습니다"
              % (ai_csv_path(OUTPUT).relative_to(ROOT_DIR), len(ai_rows)))
    if stats["기술없음"]:
        print("  기술스택이 하나도 없어 제외: %d건" % stats["기술없음"])
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
