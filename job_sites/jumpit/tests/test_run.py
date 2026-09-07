"""엔트리포인트의 **흐름과 종료 코드**.

종료 코드는 **오케스트레이터와 맺은 계약**이다. 여러 사이트를 병렬로 돌릴 때 `2`(차단)를
정상으로 읽으면 절반만 든 CSV 를 온전한 것으로 착각한다. 그래서 네 코드를 여기서 굳힌다.

`_collect_details` 자체는 `test_jumpit.py` 가 본다. 여기는 그 바깥 흐름이다.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import jumpit
import lib.config as config_module
from lib.client import BlockedError
from lib.collect import Listings

from .helpers import check, check_equal, env_file

NARROW_ENV = "JOB_ROLES=백엔드\nYOE=0\nHOME_LOCATIONS=서울\n"


class Recorder:
    """실행 중에 찍힌 글을 모은다. 사람에게 무엇을 알렸는지 확인하려고."""

    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, *parts, **_kwargs):
        self.lines.append(" ".join(str(p) for p in parts))

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _run(env_text=NARROW_ENV, listings=None, blocked_at=None, fail_ids=()):
    """`_run()` 을 네트워크·파일 없이 돌린다. 찍힌 글과 종료 코드를 돌려준다."""
    listings = listings if listings is not None else Listings(
        rows=[{"id": 1, "techStacks": ["java"], "companyName": "회사"}],
        received=1, pages=1, reported_total=1, stop_reason="다 모았다")
    saved: dict = {}
    printed = Recorder()

    def fake_detail(_client, pid):
        if blocked_at is not None and pid == blocked_at:
            raise BlockedError("403")
        if pid in fail_ids:
            raise RuntimeError("상세 조회에 실패했습니다")
        return {"companyName": "회사", "qualifications": "Java 3년",
                "location": "서울 강남구", "techStacks": [{"stack": "java"}],
                "newcomer": True}

    def fake_save(rows, output, ai_rows=None):
        saved["rows"] = rows
        saved["output"] = output

        class Result:
            def __init__(self):
                self.rows, self.added, self.updated = rows, len(rows), 0
                self.unseen = self.expired = self.undated = 0
        return Result()

    original = {name: getattr(jumpit, name)
                for name in ("fetch_listings", "fetch_detail", "save", "JumpitClient")}
    original_env = config_module.ENV_PATH
    config_module.ENV_PATH = env_file(env_text)
    jumpit.fetch_listings = lambda *a, **k: listings
    jumpit.fetch_detail = fake_detail
    jumpit.save = fake_save
    jumpit.JumpitClient = lambda *a, **k: object()
    jumpit.print = printed
    try:
        code = jumpit._run()
    finally:
        config_module.ENV_PATH = original_env
        for name, value in original.items():
            setattr(jumpit, name, value)
        del jumpit.print
    return code, printed.text, saved


def test_NORMAL_returns_zero_and_saves():
    code, _text, saved = _run()
    check_equal(code, 0, "정상은 0")
    check_equal(len(saved.get("rows") or []), 1, "행을 저장해야 한다")


def test_NORMAL_prints_the_conditions_it_will_use():
    _code, text, _saved = _run()
    for word in ("수집 조건", "직무", "경력", "근무지"):
        check(word in text, "%s 를 찍어야 한다" % word)


def test_NORMAL_prints_why_tech_stacks_are_not_applied():
    # 이 사이트의 핵심 결정이다. 조용히 무시하면 왜 다른지 나중에 못 찾는다.
    _code, text, _saved = _run(NARROW_ENV + "TECH_STACKS=Spring Boot,Python\n")
    check("기술스택" in text and "걸지 않습니다" in text, "왜 안 거는지 알려야 한다")
    check("Spring Framework" in text, "근거를 함께 알려야 한다: %s" % text)


def test_NORMAL_prints_which_employment_types_are_unsupported():
    _code, text, _saved = _run(NARROW_ENV + "EMPLOYMENT_TYPES=regular,intern\n")
    check("regular" in text and "못 겁니다" in text, "못 건 것을 알려야 한다: %s" % text)


def test_NORMAL_prints_why_education_is_not_applied():
    _code, text, _saved = _run(NARROW_ENV + "EDUCATION=대졸4\n")
    check("학력" in text and "걸지 않습니다" in text, text)


def test_EXCEPTION_config_error_returns_one():
    code, _text, saved = _run("YOE=0\n")          # JOB_ROLES 가 없다
    check_equal(code, 1, "설정 오류는 1")
    check("rows" not in saved, "저장하면 안 된다")


def test_EXCEPTION_unknown_location_returns_one():
    code, _text, saved = _run("JOB_ROLES=백엔드\nHOME_LOCATIONS=뉴욕\n")
    check_equal(code, 1, "옮길 수 없는 근무지도 설정 오류다")
    check("rows" not in saved, "저장하면 안 된다")


def test_EXCEPTION_blocked_returns_two_but_saves_what_it_got():
    listings = Listings(rows=[{"id": 1, "techStacks": ["java"]},
                              {"id": 2, "techStacks": ["java"]}],
                        received=2, pages=1, reported_total=2, stop_reason="다 모았다")
    code, _text, saved = _run(listings=listings, blocked_at=2)
    check_equal(code, 2, "차단은 2")
    check_equal(len(saved.get("rows") or []), 1, "차단 전까지 모은 것은 저장한다")


def test_BOUNDARY_no_postings_is_zero_not_a_failure():
    empty = Listings(rows=[], received=0, pages=1, reported_total=0, stop_reason="비었다")
    code, text, saved = _run(listings=empty)
    check_equal(code, 0, "없는 것은 실패가 아니다")
    check("rows" not in saved, "쓸 행이 없으면 저장도 안 한다")
    check("공고가 없습니다" in text, text)


def test_BOUNDARY_reports_total_mismatch():
    # 조용히 적게 걷히는 것을 잡는 유일한 수단이다. 눈에 띄어야 한다.
    off = Listings(rows=[{"id": 1, "techStacks": ["java"]}], received=9, pages=1,
                   reported_total=10, stop_reason="다 모았다")
    _code, text, _saved = _run(listings=off)
    check("불일치" in text, "총계가 어긋나면 그렇게 말해야 한다: %s" % text)


def test_BOUNDARY_reports_duplicates_without_calling_it_a_mismatch():
    # 한 공고가 여러 직무에 걸치면 총계에 여러 번 세어진다. **일치인데 고유 수는 적다** —
    # 그 둘을 헷갈리게 찍으면 사람이 누락으로 오해한다.
    dup = Listings(rows=[{"id": 1, "techStacks": ["java"]}], received=2, pages=1,
                   reported_total=2, stop_reason="다 모았다")
    _code, text, _saved = _run(listings=dup)
    check("일치" in text and "불일치" not in text, "총계는 일치다: %s" % text)
    check("겹쳐" in text, "겹친 사실은 따로 알려야 한다: %s" % text)


def test_BOUNDARY_missing_total_is_said_out_loud():
    unknown = Listings(rows=[{"id": 1, "techStacks": ["java"]}], received=1, pages=1,
                       reported_total=None, stop_reason="끝났다")
    _code, text, _saved = _run(listings=unknown)
    check("총계를 못 읽었" in text, "확인 수단이 없다는 것을 알려야 한다: %s" % text)


def test_BOUNDARY_salary_is_reported_as_unavailable():
    _code, text, _saved = _run(NARROW_ENV + "HOPE_ANNUAL_SALARY=3300\n")
    check("적용하지 않은 조건" in text and "연봉" in text,
          "이 사이트가 연봉을 안 준다는 사실을 알려야 한다: %s" % text)


def test_BOUNDARY_main_returns_three_when_locked():
    from _common.runlock import run_lock
    original = jumpit.LOCK
    jumpit.LOCK = Path(tempfile.mkdtemp()) / ".test.lock"
    try:
        with run_lock(jumpit.LOCK):
            check_equal(jumpit.main(), 3, "겹쳐 돌면 3")
    finally:
        jumpit.LOCK = original


def test_BOUNDARY_main_runs_when_the_lock_is_free():
    original_lock, original_run = jumpit.LOCK, jumpit._run
    jumpit.LOCK = Path(tempfile.mkdtemp()) / ".free.lock"
    jumpit._run = lambda: 7
    try:
        check_equal(jumpit.main(), 7, "_run 의 결과를 그대로 돌려줘야 한다")
    finally:
        jumpit.LOCK, jumpit._run = original_lock, original_run


def test_BOUNDARY_summary_prints_every_counter():
    """요약의 **모든 줄**을 한 번씩 찍어 본다.

    출력은 수집이 다 끝난 뒤에 돈다. 여기서 서식이 틀리면 걷어 온 것을 눈앞에서
    잃는다 — `ai_csv_path(...).relative_to(...)` 처럼 터질 수 있는 호출이 있다.
    """
    printed = Recorder()

    class Result:
        rows = [{"URL": "u"}]
        added, updated, unseen, expired, undated = 1, 2, 3, 4, 5

    class Config:
        tech_stacks = ["Python"]
        hope_annual_salary = "3300"

    stats = {"기술없음": 6, "상세실패": 7, "번호없음": 8, "차단": False}
    jumpit.print = printed
    try:
        jumpit._print_summary(Config(), Result(), [{"URL": "u"}], stats)
    finally:
        del jumpit.print

    for word in ("AI 가 관여한", "기술스택이 하나도 없어", "상세를 못 받아",
                 "공고번호가 없어", "적용하지 않은 조건", "연봉은 이 사이트가"):
        check(word in printed.text, "'%s' 를 못 찍었다:\n%s" % (word, printed.text))


def test_EXCEPTION_every_detail_failing_is_not_a_normal_run():
    """상세가 **전부** 실패하면 종료 코드 2.

    Pathsdog 에서 실제로 난 일이다 — 상세 도구가 죽어 29건이 다 실패했는데, 공고
    하나의 실패를 견디는 코드가 전부의 실패도 똑같이 견뎌 **0** 을 냈다. 화면에는
    `정상 · 0행` 이라고 찍혔다. 여기도 같은 구조라 같이 굳힌다.
    """
    listings = Listings(rows=[{"id": 1, "techStacks": ["java"], "companyName": "회사"},
                              {"id": 2, "techStacks": ["java"], "companyName": "회사"}],
                        received=2, pages=1, reported_total=2, stop_reason="다 모았다")
    code, text, saved = _run(listings=listings, fail_ids={1, 2})
    check_equal(code, 2, "전부 실패는 정상이 아니다")
    check("걷은 것이 없습니다" in text, "왜 0행인지 말해야 한다: %s" % text)
    check_equal(len(saved.get("rows") or []), 0, "걷은 것이 없다")


def test_BOUNDARY_one_success_among_failures_is_still_a_normal_run():
    # 비율로 자르지 않는다. 하나라도 걷었으면 그 실행은 무언가를 해낸 것이다.
    listings = Listings(rows=[{"id": 1, "techStacks": ["java"], "companyName": "회사"},
                              {"id": 2, "techStacks": ["java"], "companyName": "회사"}],
                        received=2, pages=1, reported_total=2, stop_reason="다 모았다")
    code, _text, saved = _run(listings=listings, fail_ids={2})
    check_equal(code, 0, "하나라도 걷었으면 정상")
    check_equal(len(saved.get("rows") or []), 1, "걷은 것은 저장한다")
