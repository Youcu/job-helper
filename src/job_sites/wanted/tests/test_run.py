"""엔트리포인트. 모듈을 다 이어 붙였을 때 **종료 코드로 무엇이 나가는가.**

여기 테스트가 그동안 하나도 없었다 — 다섯 사이트 중 `wanted` 만 그랬다. 그래서
`_run()` 의 배선이 코드 차원에서 아무 보호를 못 받았다.

**종료 코드는 오케스트레이터와 맺은 계약이다.** 다 섞어서 `0` 을 주면 실패한 실행이
성공으로 기록된다 — 터지지도 멈추지도 않아 알아채기가 가장 어렵다.

    0  정상        1  설정 오류        2  온전히 못 걷음        3  이미 돌고 있음

네트워크도 파일도 안 탄다 — 모듈의 이름을 잠깐 바꿔 끼운다.
"""
from __future__ import annotations

import io
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import wanted
from lib.client import BlockedError


class _Config:
    job_group_ids = [518]
    job_ids: list[int] = []
    yoe = -1
    employment_types = ["정규직"]
    employment_type_keys = ["full_time"]
    home_locations: list[str] = []
    tech_stacks: list[str] = []
    hope_annual_salary = ""


def _job(job_id=1):
    """`to_row` 가 받아들이는 최소 모양."""
    return {"id": job_id,
            "company": {"name": "회사"},
            "position": "백엔드 개발자",
            "detail": {"requirements": "Java 3년", "preferred_points": "Spring"},
            "skill_tags": [{"title": "Java"}],
            "address": {"location": "서울 강남구"},
            "due_time": None}


def _run_with(listings, details, *, detail_raises=None, listing_raises=None):
    """`_run()` 을 네트워크·파일 없이 돌린다. `(종료 코드, 화면)` 을 준다."""
    home = Path(tempfile.mkdtemp())

    def fake_listings(_client, _params, group_label):
        if listing_raises is not None:
            raise listing_raises
        return listings, "다 훑었다"

    def fake_details(_client, job_ids):
        if detail_raises is not None:
            raise detail_raises
        return details

    monkey = {
        "load_config": lambda: _Config(),
        "resolve_locations": lambda names: ([], []),
        "job_groups": lambda: {518: "개발"},
        "WantedClient": lambda *a, **k: object(),
        "build_listing_params": lambda **k: [],
        "fetch_listings": fake_listings,
        "fetch_details": fake_details,
        "OUTPUT": home / "csv" / "wanted_post.csv",
        "ROOT": home,
    }
    original = {name: getattr(wanted, name) for name in monkey}
    for name, value in monkey.items():
        setattr(wanted, name, value)
    noise = io.StringIO()
    try:
        with redirect_stdout(noise), redirect_stderr(noise):
            code = wanted._run()
    finally:
        for name, value in original.items():
            setattr(wanted, name, value)
    return code, noise.getvalue()


# ── 일반 ────────────────────────────────────────────────────────────────

def test_NORMAL_a_good_run_returns_zero():
    code, _screen = _run_with({1: {}}, {1: _job(1)})
    assert code == 0, code


# ── 예외 ────────────────────────────────────────────────────────────────

def test_EXCEPTION_all_details_failing_is_not_a_normal_run():
    """**결함이었다.** 목록은 받았는데 상세를 한 건도 못 받으면 `0` 이 나갔다.

    화면에는 `정상 · 0행` 이라 찍혀, 사이트에 공고가 있는데도 없는 것처럼 보인다
    (`_common/outcome.py` 의 Pathsdog 사고). `fetch_details` 는 거르는 일을 하지
    않으므로 **`listings` 가 있는데 `details` 가 비었다 = 전멸**이고 다른 해석이 없다.
    """
    code, screen = _run_with({1: {}, 2: {}}, {})
    assert code == wanted.INCOMPLETE, code
    assert "하나도 못" in screen, screen


def test_EXCEPTION_blocked_while_fetching_details_returns_two():
    """**결함이었다.** 상세 단계의 차단이 삼켜져 `0` 이 나갔다.

    `BlockedError` 가 그냥 `Exception` 이라 (`lib/client.py`) `fetch()` 의
    `except Exception` 이 먼저 잡았다. 다른 넷은 `except BlockedError` 를 앞에
    따로 둬서 안 그런다.

    그래서 **목록에서 403 이면 `2`, 상세에서 403 이면 `0`** 이 됐다 — 같은 사고인데
    어디서 맞았느냐에 따라 다르게 보고했다. 403 은 재시도를 안 하므로
    (`client.get_json`) 한 번 막히면 남은 상세가 전부 같은 길로 간다.
    """
    code, screen = _run_with({1: {}}, {}, detail_raises=BlockedError("403"))
    assert code == 2, code
    assert "차단됨" in screen, screen


def test_EXCEPTION_blocked_while_listing_returns_two():
    """목록 단계의 차단. 위와 **같은 코드, 같은 말**이어야 한다."""
    code, screen = _run_with({1: {}}, {1: _job(1)},
                             listing_raises=BlockedError("403"))
    assert code == 2, code
    assert "차단됨" in screen, screen


# ── 경계 ────────────────────────────────────────────────────────────────

def test_BOUNDARY_empty_listing_is_a_normal_run():
    """목록부터 비었으면 정상이다 — **잃은 것이 없다.** 조건이 좁았을 뿐이다."""
    code, screen = _run_with({}, {})
    assert code == 0, code
    assert "조건에 맞는 공고가 없습니다" in screen, screen


def test_BOUNDARY_zero_rows_after_filtering_is_still_normal():
    """상세는 다 받았는데 **기술이 없어 다 걸러진** 것은 정상이다.

    `0행` 자체가 실패인 것이 아니다. 가르는 기준은 **잃은 것이 있는가**이다.
    """
    naked = _job(1)
    naked["skill_tags"] = []
    naked["detail"] = {"requirements": "성실한 분", "preferred_points": ""}
    code, _screen = _run_with({1: {}}, {1: naked})
    assert code == 0, code


def test_BOUNDARY_merge_summary_comes_from_common():
    """**병합 결과를 찍는 말은 `_common` 이 쥔다.** 여기 사본을 두면 안 된다.

    `store.merge_lines()` 는 그것을 막으려고 만든 함수다 — 세는 규칙이 바뀌면 찍는
    말도 같이 바뀌어야 하는데, 사이트마다 사본이 있으면 한 곳만 고치고 지나간다.
    예외도 안 나고 테스트도 안 깨지므로 **화면에 서로 다른 숫자가 나올 때까지 모른다.**

    `wanted` 는 그 사본을 갖고 있었다 — 여섯 줄이 글자까지 같았다.
    """
    from _common import store

    calls = []
    original = store.merge_lines
    store.merge_lines = lambda result, **kw: calls.append(result) or ["  (공통)"]
    wanted.merge_lines = store.merge_lines
    try:
        code, screen = _run_with({1: {}}, {1: _job(1)})
    finally:
        store.merge_lines = original
        wanted.merge_lines = original

    assert code == 0, code
    assert len(calls) == 1, "**공통 함수를 지나야 한다** — 사본을 쓰면 0이다"
    assert "(공통)" in screen, screen
