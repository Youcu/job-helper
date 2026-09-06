"""엔트리포인트의 **흐름과 종료 코드**.

종료 코드는 **오케스트레이터와 맺은 계약**이다. `2`(차단)를 정상으로 읽으면 절반만 든
CSV 를 온전한 것으로 착각한다. 그래서 네 코드를 여기서 굳힌다.

`_collect_details` 자체는 `test_pathsdog.py` 가 본다. 여기는 그 바깥 흐름이다.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import lib.config as config_module
import pathsdog
from lib.client import BlockedError
from lib.collect import Listings

from .helpers import check, check_equal, env_file

NARROW_ENV = "PATHSDOG_JOB_IDS=Backend\nYOE=0\nHOME_LOCATIONS=서울\n"


class Recorder:
    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, *parts, **_kwargs):
        self.lines.append(" ".join(str(p) for p in parts))

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _detail(place="서울 강남구", jobtype="정규직"):
    return ("📋 회사 - 공고\n- 기술스택: java\n- 경력: 신입\n- 근무지: %s\n"
            "- 고용형태: %s\n- 서류 마감: 2026-09-30\n[상세 내용]\n자격요건\nJava 3년\n"
            % (place, jobtype))


def _run(env_text=NARROW_ENV, listings=None, blocked_at=None):
    listings = listings if listings is not None else Listings(
        rows=[{"id": "1", "기업명": "회사", "기술": "Python",
               "조건": "신입 | 근무지: 서울 | 정규직", "마감": "2026-09-30"}],
        pages=1, reported_total=1, stop_reason="다 읽었다")
    saved: dict = {}
    printed = Recorder()

    def fake_detail(_client, job_id):
        if blocked_at is not None and job_id == blocked_at:
            raise BlockedError("403")
        return _detail()

    def fake_save(rows, output, ai_rows=None):
        saved["rows"] = rows

        class Result:
            def __init__(self):
                self.rows, self.added, self.updated = rows, len(rows), 0
                self.unseen = self.expired = self.undated = 0
        return Result()

    original = {name: getattr(pathsdog, name)
                for name in ("fetch_listings", "fetch_detail", "save", "PathsdogClient")}
    original_env = config_module.ENV_PATH
    config_module.ENV_PATH = env_file(env_text)
    pathsdog.fetch_listings = lambda *a, **k: listings
    pathsdog.fetch_detail = fake_detail
    pathsdog.save = fake_save
    pathsdog.PathsdogClient = lambda *a, **k: object()
    pathsdog.print = printed
    try:
        code = pathsdog._run()
    finally:
        config_module.ENV_PATH = original_env
        for name, value in original.items():
            setattr(pathsdog, name, value)
        del pathsdog.print
    return code, printed.text, saved


def test_NORMAL_returns_zero_and_saves():
    code, _text, saved = _run()
    check_equal(code, 0, "정상은 0")
    check_equal(len(saved.get("rows") or []), 1, "행을 저장해야 한다")


def test_NORMAL_prints_the_conditions():
    _code, text, _saved = _run()
    for word in ("수집 조건", "역할", "경력", "근무지"):
        check(word in text, "%s 를 찍어야 한다" % word)


def test_NORMAL_says_the_server_cannot_filter_location():
    # 이 사이트의 핵심 제약이다. 조용히 넘기면 왜 다른지 나중에 못 찾는다.
    _code, text, _saved = _run()
    check("근무지는 **서버가 못 거릅니다**" in text, "알려야 한다: %s" % text)
    check("지역 파라미터가 없습니다" in text, text)


def test_NORMAL_says_the_server_cannot_filter_employment():
    _code, text, _saved = _run(NARROW_ENV + "EMPLOYMENT_TYPES=regular,intern\n")
    check("고용형태도 **서버가 못 거릅니다**" in text, "알려야 한다: %s" % text)


def test_NORMAL_warns_about_an_unknown_role():
    _code, text, _saved = _run("PATHSDOG_JOB_IDS=Backend,쿠버네티스마스터\nYOE=0\n")
    check("코드표에 없는 역할" in text and "쿠버네티스마스터" in text, text)
    check("막지는 않습니다" in text, "막는 게 아니라는 것도 알려야 한다")


def test_NORMAL_says_education_and_tech_are_not_applied():
    _code, text, _saved = _run(NARROW_ENV + "EDUCATION=대졸4\nTECH_STACKS=Python\n")
    check("학력" in text and "기술스택" in text, text)


def test_EXCEPTION_config_error_returns_one():
    code, _text, saved = _run("YOE=0\n")          # 역할이 없다
    check_equal(code, 1, "설정 오류는 1")
    check("rows" not in saved, "저장하면 안 된다")


def test_EXCEPTION_blocked_returns_two_but_saves_what_it_got():
    listings = Listings(rows=[{"id": "1", "기술": "Python", "조건": ""},
                              {"id": "2", "기술": "Python", "조건": ""}],
                        pages=1, reported_total=2, stop_reason="다 읽었다")
    code, _text, saved = _run(listings=listings, blocked_at="2")
    check_equal(code, 2, "차단은 2")
    check_equal(len(saved.get("rows") or []), 1, "차단 전까지 모은 것은 저장한다")


def test_BOUNDARY_no_postings_is_zero_not_a_failure():
    empty = Listings(rows=[], pages=1, reported_total=0, stop_reason="비었다")
    code, text, saved = _run(listings=empty)
    check_equal(code, 0, "없는 것은 실패가 아니다")
    check("rows" not in saved, "쓸 행이 없으면 저장도 안 한다")
    check("공고가 없습니다" in text, text)


def test_BOUNDARY_count_mismatch_is_visible():
    # 응답이 글이라 서식이 바뀌면 조용히 적게 읽힌다. 그때 눈에 띄어야 한다.
    off = Listings(rows=[{"id": "1", "기술": "Python", "조건": ""}], pages=1,
                   reported_total=9, stop_reason="다 읽었다")
    _code, text, _saved = _run(listings=off)
    check("불일치" in text, "어긋나면 그렇게 말해야 한다: %s" % text)
    check("서식이 바뀌었을 수 있습니다" in text, "무엇을 의심할지 알려야 한다")


def test_BOUNDARY_missing_count_is_said_out_loud():
    unknown = Listings(rows=[{"id": "1", "기술": "Python", "조건": ""}], pages=1,
                       reported_total=None, stop_reason="끝났다")
    _code, text, _saved = _run(listings=unknown)
    check("개수를 안 알렸습니다" in text, "확인 수단이 없다는 것을 알려야 한다: %s" % text)


def test_BOUNDARY_summary_prints_every_counter():
    """요약의 **모든 줄**을 한 번씩 찍어 본다.

    출력은 수집이 다 끝난 뒤에 돈다. 여기서 서식이 틀리면 걷어 온 것을 눈앞에서 잃는다.
    """
    printed = Recorder()

    class Result:
        rows = [{"URL": "u"}]
        added, updated, unseen, expired, undated = 1, 2, 3, 4, 5

    class Config:
        tech_stacks = ["Python"]
        hope_annual_salary = "3300"

    stats = {"기술없음": 6, "상세실패": 7, "번호없음": 8, "근무지밖": 9,
             "고용형태밖": 10, "차단": False}
    pathsdog.print = printed
    try:
        pathsdog._print_summary(Config(), Result(), [{"URL": "u"}], stats)
    finally:
        del pathsdog.print
    for word in ("근무지가 조건 밖", "고용형태가 조건 밖", "AI 가 관여한",
                 "기술스택이 하나도 없어", "상세를 못 받아", "공고번호가 없어",
                 "적용하지 않은 조건"):
        check(word in printed.text, "'%s' 를 못 찍었다:\n%s" % (word, printed.text))


def test_BOUNDARY_main_returns_three_when_locked():
    from _common.runlock import run_lock
    original = pathsdog.LOCK
    pathsdog.LOCK = Path(tempfile.mkdtemp()) / ".test.lock"
    try:
        with run_lock(pathsdog.LOCK):
            check_equal(pathsdog.main(), 3, "겹쳐 돌면 3")
    finally:
        pathsdog.LOCK = original


def test_BOUNDARY_main_runs_when_the_lock_is_free():
    original_lock, original_run = pathsdog.LOCK, pathsdog._run
    pathsdog.LOCK = Path(tempfile.mkdtemp()) / ".free.lock"
    pathsdog._run = lambda: 7
    try:
        check_equal(pathsdog.main(), 7, "_run 의 결과를 그대로 돌려줘야 한다")
    finally:
        pathsdog.LOCK, pathsdog._run = original_lock, original_run


def test_NORMAL_says_which_employment_types_do_not_exist_here():
    # `dispatch`(파견) 는 다른 사이트에는 있고 여기는 없다.
    _code, text, _saved = _run(NARROW_ENV + "EMPLOYMENT_TYPES=regular,dispatch\n")
    check("dispatch" in text and "없는 값" in text, "무엇이 없는 값인지 알려야 한다: %s" % text)
