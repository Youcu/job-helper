"""여섯 사이트를 돌리고 결과를 판정하는 일.

**가장 중요한 것은 종료 코드를 옳게 읽는가**다. `4`(조건이 넓어 건너뜀)를 실패로 읽으면
파이프라인 전체가 멎고, `2`(차단)를 정상으로 읽으면 절반만 든 CSV 를 온전한 것으로
착각한다. 그 판정이 이 파일의 절반이다.

자식 프로세스도 네트워크도 타지 않는다 — `_run_one` 을 가짜로 바꿔 넣는다.
"""
from __future__ import annotations

import job_crawling_ochestrator as orch

from .helpers import check, check_equal, temp_dir


def _result(site, code=0, rows=0, log="", error="", seconds=1.0):
    return orch.Result(site=site, code=code, rows=rows, log=log, error=error,
                       seconds=seconds)


def _run_with(fake_results):
    """`_run_all` 을 가짜 결과로 돌린다."""
    original = orch._run_one
    orch._run_one = lambda site, path: fake_results[site]
    try:
        return orch._run_all({site: temp_dir() / ("%s.py" % site) for site in fake_results})
    finally:
        orch._run_one = original


def test_NORMAL_zero_is_success():
    check(_result("wanted", code=0).ok, "0 은 정상")
    check_equal(_result("wanted", code=0).meaning, "정상", "뜻")


def test_NORMAL_runs_every_site():
    fakes = {site: _result(site, rows=3) for site in orch.SITES}
    results = _run_with(fakes)
    check_equal(len(results), len(orch.SITES), "여섯 곳 다 돌아야 한다")
    check(all(r.ok for r in results), "전부 정상")


def test_NORMAL_results_keep_the_declared_order():
    # 실행이 끝나는 차례는 제각각이지만, 보고와 합치기는 **정해진 차례**를 지켜야 한다 —
    # 실행마다 행 순서가 뒤바뀌면 `merged.csv` 를 눈으로 견주기 어렵다.
    fakes = {site: _result(site) for site in orch.SITES}
    results = _run_with(fakes)
    check_equal([r.site for r in results], list(orch.SITES), "선언한 차례")


def test_EXCEPTION_config_error_is_a_failure():
    result = _result("jumpit", code=1)
    check(not result.ok, "1 은 실패")
    check_equal(result.meaning, "설정 오류", "뜻")


def test_EXCEPTION_blocked_is_a_failure_even_though_rows_were_saved():
    # `2` 는 "모은 것은 저장했다" 는 뜻이지만, 절반만 걷힌 것이라 정상으로 세면 안 된다.
    result = _result("jobplanet", code=2, rows=20)
    check(not result.ok, "2 는 실패다 — 행이 있어도 온전하지 않다")
    check("모은 것은 저장" in result.meaning, result.meaning)


def test_EXCEPTION_already_running_is_a_failure():
    check(not _result("saramin", code=3).ok, "3 은 실패")


def test_EXCEPTION_timeout_has_no_code():
    result = _result("saramin", code=None, error="30분을 넘겨 끊었습니다")
    check(not result.ok, "코드가 없으면 실패")
    check_equal(result.meaning, "30분을 넘겨 끊었습니다", "왜인지 남아야 한다")


def test_EXCEPTION_unknown_code_is_a_failure():
    # 모르는 코드를 정상으로 세면 조용히 넘어간다. 모르면 실패로 본다.
    result = _result("wanted", code=99)
    check(not result.ok, "모르는 코드는 실패")
    check("알 수 없는" in result.meaning, result.meaning)


def test_BOUNDARY_skipped_is_not_a_failure():
    # **오케스트레이터와 맺은 계약이다.** 잡플래닛이 "조건이 넓어 이번엔 건너뛴다" 고
    # 말하는 신호라, 실패로 세면 파이프라인 전체가 멎는다.
    result = _result("jobplanet", code=4)
    check(result.ok, "4 는 실패가 아니다")
    check("건너뜀" in result.meaning, result.meaning)


def test_BOUNDARY_every_exit_code_has_a_meaning():
    # 스크래퍼가 내는 코드는 0~4 다. 하나라도 빠지면 "알 수 없는 코드" 로 떨어진다.
    for code in (0, 1, 2, 3, 4):
        check(code in orch.EXIT_MEANING, "%d 의 뜻이 없다" % code)


def test_BOUNDARY_only_zero_and_four_are_success():
    ok = {code for code, (_, good) in orch.EXIT_MEANING.items() if good}
    check_equal(ok, {0, 4}, "정상으로 세는 코드는 둘뿐이어야 한다: %r" % ok)


def test_BOUNDARY_one_failure_does_not_stop_the_others():
    fakes = {site: _result(site, rows=2) for site in orch.SITES}
    fakes["saramin"] = _result("saramin", code=1)
    results = _run_with(fakes)
    check_equal(len(results), len(orch.SITES), "나머지도 다 돈다")
    check_equal(len([r for r in results if r.ok]), len(orch.SITES) - 1, "하나만 실패")


def test_BOUNDARY_failure_report_shows_what_the_scraper_said():
    # "설정 오류" 라고만 하면 사람이 여섯 폴더를 뒤져야 한다.
    log = "설정 오류: JUMPIT_JOB_IDS 가 비어 있습니다.\n  코드표는 README.md 에 있습니다."
    lines = orch._last_lines(log, 8)
    check("JUMPIT_JOB_IDS" in "\n".join(lines), "무엇을 채워야 하는지 남아야 한다: %r" % lines)


def test_BOUNDARY_progress_bars_are_stripped_from_the_report():
    # 자식이 tqdm 을 그린 줄까지 보여 주면 진짜 오류가 묻힌다.
    log = "상세:  50%|█████     | 5/10 [00:03<00:03]\n설정 오류: 무언가 잘못됐습니다"
    lines = orch._last_lines(log, 8)
    check_equal(lines, ["설정 오류: 무언가 잘못됐습니다"], "막대는 빼야 한다: %r" % lines)


def test_BOUNDARY_last_lines_handles_empty_log():
    check_equal(orch._last_lines("", 5), [], "빈 로그")
    check_equal(orch._last_lines(None, 5), [], "로그가 없어도 터지지 않는다")


def test_BOUNDARY_last_lines_takes_the_end_not_the_start():
    # 오류는 대개 끝에 있다. 앞을 보여 주면 정상 진행만 보인다.
    log = "\n".join("줄 %d" % n for n in range(1, 21))
    check_equal(orch._last_lines(log, 3), ["줄 18", "줄 19", "줄 20"], "끝에서 셋")


def test_BOUNDARY_site_list_matches_the_folders():
    # 사이트를 하나 더 붙였는데 목록에 안 넣으면 조용히 빠진다.
    folders = {p.name for p in orch.SITES_DIR.iterdir()
               if p.is_dir() and (p / ("%s.py" % p.name)).exists()}
    check_equal(set(orch.SITES), folders,
                "SITES 와 실제 폴더가 어긋난다 — 목록: %r · 폴더: %r"
                % (sorted(orch.SITES), sorted(folders)))


def test_BOUNDARY_output_is_outside_the_site_folders():
    # 합친 파일을 사이트 폴더 안에 두면 그 사이트가 다음 실행에서 자기 것으로 읽는다.
    check("job_sites" not in str(orch.OUTPUT), "사이트 폴더 밖이어야 한다: %s" % orch.OUTPUT)
    check_equal(orch.OUTPUT.name, "merged.csv", "이름")


def test_BOUNDARY_stale_rows_are_marked_not_counted_as_fresh():
    # 결함이 될 뻔한 곳: 실패한 사이트도 `행` 칸에 지난 CSV 행 수가 찍혀, 이번에 걷어
    # 온 것처럼 보였다. 합치기는 맞지만(30일 누적이라 현재 상태다) 밝혀야 한다.
    result = _result("jumpit", code=1, rows=7)
    check(result.stale, "이번엔 못 걷었는데 CSV 가 남아 있다")
    check("이번엔 못 걷음" in orch._tail(result), orch._tail(result))
    check("7행" in orch._tail(result), "지난 행 수도 밝힌다")


def test_BOUNDARY_failed_site_without_a_csv_is_not_stale():
    check(not _result("jumpit", code=1, rows=0).stale, "CSV 가 없으면 밝힐 것도 없다")


def test_BOUNDARY_successful_site_is_never_stale():
    check(not _result("wanted", code=0, rows=100).stale, "정상은 지난 것이 아니다")
    check(not _result("jobplanet", code=4, rows=5).stale, "건너뛴 것도 실패가 아니다")
