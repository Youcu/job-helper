"""목록 페이지네이션과 상세 수집.

위험요소는 페이지 크기가 아니라 (1) 서버가 offset 을
무시해 같은 페이지를 계속 주는 것, (2) 수집 도중 공고가 추가·삭제돼 경계가 밀리는
것이다. 아래 루프는 그 둘을 막는다.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from tqdm import tqdm

from .client import WantedClient

LISTINGS_PATH = "/api/chaos/navigation/v1/results"
DETAIL_PATH = "/api/chaos/jobs/v2/{job_id}/details"
PAGE_SIZE = 100
MAX_OFFSET = 100_000  # 폭주 방지. 정상 조건이면 근처에도 못 간다.


def build_listing_params(
    *,
    job_group_id: int,
    job_ids: list[int],
    location_slugs: list[str],
    employment_type_keys: list[str],
    yoe: int,
) -> list[tuple[str, str]]:
    """API 는 같은 키를 여러 번 받으므로 dict 가 아니라 (키, 값) 목록으로 만든다."""
    params: list[tuple[str, str]] = [
        ("country", "kr"),
        ("job_group_id", str(job_group_id)),
        ("job_sort", "job.latest_order"),
    ]
    params += [("job_ids", str(i)) for i in job_ids]
    params += [("locations", slug) for slug in location_slugs]
    params += [("employment_types", key) for key in employment_type_keys]
    if yoe >= 0:  # -1(전체) 이면 파라미터를 아예 빼야 전체가 나온다.
        params.append(("years", str(yoe)))
    return params


def fetch_listings(
    client: WantedClient,
    base_params: list[tuple[str, str]],
    *,
    group_label: str,
    page_size: int = PAGE_SIZE,
) -> tuple[dict[int, dict], str]:
    """한 직군의 목록을 끝까지 가져온다. (공고번호→공고, 종료 이유) 를 돌려준다."""
    referer = f"https://www.wanted.co.kr/wdlist/{dict(base_params).get('job_group_id', '')}"
    rows: dict[int, dict] = {}
    offset = 0
    reason = "알 수 없음"
    bar = tqdm(desc=f"목록 {group_label}", unit="건", leave=True)
    try:
        while True:
            params = base_params + [("limit", str(page_size)), ("offset", str(offset))]
            try:
                payload = client.get_json(LISTINGS_PATH, params=params, referer=referer)
            except Exception as exc:
                # 여기서 그냥 죽으면 앞서 모은 페이지까지 통째로 잃는다.
                # 멈추되 왜 멈췄는지 남기고, 모은 것은 돌려준다.
                reason = f"요청 실패 (offset={offset}): {type(exc).__name__}: {exc}"
                break
            if not isinstance(payload, dict):
                reason = f"응답이 JSON 객체가 아님 (offset={offset}): {type(payload).__name__}"
                break
            page = payload.get("data") or []
            if not isinstance(page, list):
                reason = f"data 가 목록이 아님 (offset={offset}): {type(page).__name__}"
                break

            if not page:
                reason = f"빈 응답 (offset={offset})"
                break

            # id 없는 항목은 세지 않는다 — 나중에 상세를 부를 수도, URL 을 만들 수도 없다.
            fresh = {
                item["id"]: item
                for item in page
                if isinstance(item, dict) and item.get("id") is not None and item["id"] not in rows
            }
            rows.update(fresh)
            bar.update(len(fresh))

            if not fresh:
                # 서버가 offset 을 무시하고 같은 페이지를 반복해 주는 상황.
                # 그대로 두면 영원히 돈다.
                reason = f"새 공고 없음 — 같은 페이지 반복 의심 (offset={offset})"
                break
            if not (payload.get("links") or {}).get("next"):
                # 실측상 next 는 잔여 여부를 정확히 반영한다. 페이지가 꽉 차 있어도
                # 남은 게 없으면 null 이다.
                reason = f"links.next 없음 (offset={offset}, 마지막 페이지 {len(page)}건)"
                break

            offset += page_size
            if offset > MAX_OFFSET:
                reason = f"안전 상한 도달 (offset>{MAX_OFFSET}) — 조건을 좁혀 주세요"
                break
    finally:
        bar.close()
    return rows, reason


def fetch_details(client: WantedClient, job_ids: list[int], *, workers: int = 4) -> dict[int, dict]:
    """공고 상세를 병렬로 가져온다. 실패한 건은 조용히 빼지 않고 따로 알린다."""
    details: dict[int, dict] = {}
    failures: list[tuple[int, str]] = []

    def fetch(job_id: int) -> tuple[int, dict | None, str | None]:
        try:
            payload = client.get_json(
                DETAIL_PATH.format(job_id=job_id),
                referer=f"https://www.wanted.co.kr/wd/{job_id}",
            )
            return job_id, payload.get("job"), None
        except Exception as exc:  # 한 건 실패로 전체를 접지 않는다
            return job_id, None, f"{type(exc).__name__}: {exc}"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for job_id, job, error in tqdm(
            pool.map(fetch, job_ids), total=len(job_ids), desc="상세 수집", unit="건"
        ):
            if job:
                details[job_id] = job
            else:
                failures.append((job_id, error or "unknown"))

    if failures:
        print(f"\n  상세 수집 실패 {len(failures)}건:")
        for job_id, error in failures[:5]:
            print(f"    - {job_id}: {error}")
        if len(failures) > 5:
            print(f"    ... 외 {len(failures) - 5}건")
    return details
