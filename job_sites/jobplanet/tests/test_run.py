"""엔트리포인트의 **흐름과 종료 코드**.

종료 코드는 **오케스트레이터와 맺은 계약**이다. 여러 사이트를 병렬로 돌릴 때
`4`(조건이 넓어 건너뜀)를 실패로 잘못 읽으면 파이프라인 전체가 멎고, 반대로
`2`(차단)를 정상으로 읽으면 절반만 든 CSV 를 온전한 것으로 착각한다.
그래서 네 코드를 전부 여기서 굳힌다.

`_collect_details` 자체는 `test_jobplanet.py` 가 본다. 여기는 그 바깥 흐름이다.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import jobplanet
import lib.config as config_module
from lib.client import BlockedError
from lib.collect import Listings

from .helpers import check, check_equal, env_file

NARROW_ENV = ("JOB_ROLES=백엔드\nYOE=0\n"
              "HOME_LOCATIONS=서울\nEMPLOYMENT_TYPES=regular\n")


class Recorder:
    """실행 중에 찍힌 글을 모은다. 사람에게 무엇을 알렸는지 확인하려고."""

    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, *parts, **_kwargs):
        self.lines.append(" ".join(str(p) for p in parts))

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _run(env_text=NARROW_ENV, listings=None, details=None, blocked_at=None):
    """`_run()` 을 네트워크·파일 없이 돌린다. 찍힌 글과 종료 코드를 돌려준다."""
    listings = listings if listings is not None else Listings(
        rows=[{"id": 1, "posting_apply_type": "jobplanet"}], pages=1,
        seen=1, reported_total=1, stop_reason="다 훑었다")
    details = details or {}
    saved: dict = {}
    printed = Recorder()

    def fake_detail(_client, pid):
        if blocked_at is not None and pid == blocked_at:
            raise BlockedError("403")
        return details.get(pid, {"name": "회사", "skills": ["java"],
                                 "required_qualification": "Java 3년",
                                 "location": "서울 강남구"})

    def fake_save(rows, output, ai_rows=None):
        saved["rows"] = rows
        saved["output"] = output

        class Result:
            def __init__(self):
                self.rows, self.added, self.updated = rows, len(rows), 0
                self.unseen = self.expired = self.undated = 0
        return Result()

    original = {name: getattr(jobplanet, name)
                for name in ("fetch_listings", "fetch_detail", "save",
                             "JobPlanetClient", "print")
                if hasattr(jobplanet, name)}
    env_path = env_file(env_text)
    original_env = config_module.ENV_PATH
    config_module.ENV_PATH = env_path
    jobplanet.fetch_listings = lambda *a, **k: listings
    jobplanet.fetch_detail = fake_detail
    jobplanet.save = fake_save
    jobplanet.JobPlanetClient = lambda *a, **k: object()
    jobplanet.print = printed
    try:
        code = jobplanet._run()
    finally:
        config_module.ENV_PATH = original_env
        for name, value in original.items():
            setattr(jobplanet, name, value)
        if hasattr(jobplanet, "print"):
            del jobplanet.print
    return code, printed.text, saved


def test_NORMAL_narrow_condition_returns_zero_and_saves():
    code, text, saved = _run()
    check_equal(code, 0, "정상은 0")
    check_equal(len(saved.get("rows") or []), 1, "행을 저장해야 한다")
    check(saved["output"].name.endswith(".csv"), saved["output"])


def test_NORMAL_prints_the_conditions_it_will_use():
    _code, text, _saved = _run()
    for word in ("수집 조건", "직무", "경력", "근무지"):
        check(word in text, "%s 를 찍어야 한다" % word)


def test_NORMAL_prints_why_education_is_not_applied():
    # 조용히 무시하지 않는다 — 다른 사이트와 결과가 어긋난 이유를 찾을 수 있어야 한다.
    _code, text, _saved = _run(NARROW_ENV + "EDUCATION=대졸4\n")
    check("학력" in text and "걸지 않습니다" in text, "학력을 왜 안 거는지 알려야 한다")
    check("학력무관" in text, "근거를 함께 알려야 한다: %s" % text)


def test_NORMAL_prints_which_employment_types_are_unsupported():
    _code, text, _saved = _run(
        "JOB_ROLES=백엔드\nEMPLOYMENT_TYPES=regular,intern\n")
    check("intern" in text and "못 겁니다" in text, "못 건 것을 알려야 한다: %s" % text)


def test_EXCEPTION_config_error_returns_one():
    code, _text, saved = _run("YOE=0\n")          # JOB_ROLES 가 없다
    check_equal(code, 1, "설정 오류는 1")
    check("rows" not in saved, "저장하면 안 된다")


def test_EXCEPTION_unknown_location_returns_one():
    code, _text, saved = _run("JOB_ROLES=백엔드\nHOME_LOCATIONS=뉴욕\n")
    check_equal(code, 1, "옮길 수 없는 근무지도 설정 오류다")
    check("rows" not in saved, "저장하면 안 된다")


def test_EXCEPTION_blocked_returns_two_but_saves_what_it_got():
    listings = Listings(rows=[{"id": 1, "posting_apply_type": "jobplanet"},
                              {"id": 2, "posting_apply_type": "jobplanet"}],
                        pages=1, seen=2, reported_total=2, stop_reason="다 훑었다")
    code, _text, saved = _run(listings=listings, blocked_at=2)
    check_equal(code, 2, "차단은 2")
    check_equal(len(saved.get("rows") or []), 1, "차단 전까지 모은 것은 저장한다")


def test_BOUNDARY_over_budget_returns_four_and_saves_nothing():
    # **오케스트레이터와 맺은 계약이다.** 4 는 실패가 아니라 "이 사이트만 건너뛰라" 는 뜻이고,
    # 그때 CSV 를 건드리면 안 된다 — 반쯤 든 CSV 는 온전한 것과 구별이 안 된다.
    wide = Listings(rows=[{"id": i, "posting_apply_type": "jobplanet"} for i in range(108)],
                    pages=13, seen=1212, reported_total=1212, stop_reason="다 훑었다")
    code, text, saved = _run(listings=wide)
    check_equal(code, jobplanet.SKIPPED, "넓은 조건은 4")
    check_equal(code, 4, "코드 값 자체가 계약이다")
    check("rows" not in saved, "**CSV 를 건드리면 안 된다**")
    check("건너뜁니다" in text, "왜 물러나는지 알려야 한다")
    check("121" in text, "얼마나 필요한지 숫자로 알려야 한다: %s" % text)


def test_BOUNDARY_over_budget_on_the_listing_alone():
    over = Listings(pages=1, over_budget=True, reported_total=100000,
                    stop_reason="조건이 너무 넓다")
    code, text, saved = _run(listings=over)
    check_equal(code, 4, "목록만으로 넘겨도 4")
    check("rows" not in saved, "저장하면 안 된다")
    check("목록조차" in text, "목록도 다 안 훑었다고 알려야 한다: %s" % text)


def test_BOUNDARY_no_own_postings_is_zero_not_a_failure():
    # 조건에 자체 공고가 없을 수 있다. 그것은 정상이지 실패가 아니다.
    empty = Listings(rows=[], pages=1, seen=100, reported_total=100,
                     relayed=100, stop_reason="다 훑었다")
    code, text, saved = _run(listings=empty)
    check_equal(code, 0, "없는 것은 실패가 아니다")
    check("rows" not in saved, "쓸 행이 없으면 저장도 안 한다")
    check("자체 공고" in text, text)


def test_BOUNDARY_reports_total_mismatch():
    # 조용히 적게 걷히는 것을 잡는 유일한 수단이다. 눈에 띄어야 한다.
    off = Listings(rows=[{"id": 1, "posting_apply_type": "jobplanet"}], pages=1,
                   seen=90, reported_total=100, stop_reason="다 훑었다")
    _code, text, _saved = _run(listings=off)
    check("불일치" in text, "총계가 어긋나면 그렇게 말해야 한다: %s" % text)


def test_BOUNDARY_reports_window_limit():
    hit = Listings(rows=[{"id": 1, "posting_apply_type": "jobplanet"}], pages=100,
                   seen=10000, reported_total=34813, hit_window_limit=True,
                   stop_reason="창에 닿았다")
    code, text, _saved = _run(listings=hit)
    check("1만 건 창" in text, "창에 닿은 것을 알려야 한다: %s" % text)
    check_equal(code, 4, "창에 닿을 만큼 넓으면 어차피 예산도 넘는다")


def test_BOUNDARY_missing_total_is_said_out_loud():
    unknown = Listings(rows=[{"id": 1, "posting_apply_type": "jobplanet"}], pages=1,
                       seen=1, reported_total=None, stop_reason="다 훑었다")
    _code, text, _saved = _run(listings=unknown)
    check("총계를 못 읽었" in text, "확인 수단이 없다는 것을 알려야 한다: %s" % text)


def test_BOUNDARY_unused_conditions_are_reported():
    _code, text, _saved = _run(NARROW_ENV + "TECH_STACKS=Python\nHOPE_ANNUAL_SALARY=3300\n")
    check("적용하지 않은 조건" in text, "안 쓴 조건을 알려야 한다: %s" % text)
    check("TECH_STACKS" in text and "HOPE_ANNUAL_SALARY" in text, text)


def test_BOUNDARY_run_lock_returns_three():
    from _common.runlock import run_lock
    original_lock = jobplanet.LOCK
    jobplanet.LOCK = Path(tempfile.mkdtemp()) / ".test.lock"
    try:
        with run_lock(jobplanet.LOCK):
            check_equal(jobplanet.main(), 3, "겹쳐 돌면 3")
    finally:
        jobplanet.LOCK = original_lock


def test_BOUNDARY_every_exit_code_is_distinct():
    # 하나라도 겹치면 오케스트레이터가 구분을 못 한다.
    codes = {"정상": 0, "설정오류": 1, "차단": 2, "이미실행중": 3,
             "건너뜀": jobplanet.SKIPPED}
    check_equal(len(set(codes.values())), len(codes), "겹치는 코드가 있다: %r" % codes)


def test_BOUNDARY_summary_prints_every_counter():
    """요약의 **모든 줄**을 한 번씩 찍어 본다.

    출력은 수집이 다 끝난 뒤에 돈다. 여기서 서식이 틀리면 걷어 온 것을 눈앞에서
    잃는다 — 실제로 `ai_csv_path(...).relative_to(...)` 처럼 터질 수 있는 호출이 있다.
    """
    printed = Recorder()

    class Result:
        rows = [{"URL": "u"}]
        added, updated, unseen, expired, undated = 1, 2, 3, 4, 5

    class Config:
        tech_stacks = ["Python"]
        hope_annual_salary = "3300"

    stats = {"근무지밖": 6, "본문없음": 7, "기술없음": 8, "번호없음": 9, "차단": False}
    listings = Listings(rows=[{}], pages=1)
    original = jobplanet.print if hasattr(jobplanet, "print") else None
    jobplanet.print = printed
    try:
        jobplanet._print_summary(Config(), Result(), [{"URL": "u"}], stats, listings)
    finally:
        if original is None:
            del jobplanet.print
        else:
            jobplanet.print = original

    for word in ("이번에 안 보인 공고", "넘게 안 보여 뺀 공고", "최종확인일을 알 수 없어",
                 "근무지가 조건 밖", "본문이 빈 것", "AI 가 관여한",
                 "기술스택이 하나도 없어", "공고번호가 없어", "적용하지 않은 조건"):
        check(word in printed.text, "'%s' 를 못 찍었다:\n%s" % (word, printed.text))


def test_BOUNDARY_main_runs_when_the_lock_is_free():
    # `main()` 은 자물쇠만 감싼다. 자물쇠가 비면 `_run()` 의 결과를 그대로 내보내야 한다.
    original_lock, original_run = jobplanet.LOCK, jobplanet._run
    jobplanet.LOCK = Path(tempfile.mkdtemp()) / ".free.lock"
    jobplanet._run = lambda: 7          # 아무 값이나 — 그대로 나오는지만 본다
    try:
        check_equal(jobplanet.main(), 7, "_run 의 결과를 그대로 돌려줘야 한다")
    finally:
        jobplanet.LOCK, jobplanet._run = original_lock, original_run
