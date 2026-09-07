"""여섯 사이트를 돌리고 결과를 판정하는 일.

**가장 중요한 것은 종료 코드를 옳게 읽는가**다. `4`(조건이 넓어 건너뜀)를 실패로 읽으면
파이프라인 전체가 멎고, `2`(차단)를 정상으로 읽으면 절반만 든 CSV 를 온전한 것으로
착각한다. 그 판정이 이 파일의 절반이다.

이미지 판독 단계의 **배선**도 여기서 본다 — 합친 뒤에 부르는가, 그 단계가 실패해도 합본이
남는가, 어느 쪽이 실패하든 1 로 끝나는가. 소스 문자열을 견주지 않고 `main()` 을 실제로
돌린다. 글자만 보면 호출이 통째로 사라져도 통과하거나 오류로 터진다 — 실패가 아니라.

자식 프로세스도 네트워크도 타지 않는다 — `_run_one` 과 `_run_image_stage` 를 가짜로 바꿔
넣고, 합치기는 진짜를 임시 폴더에 돌린다. **저장소의 `csv/` 에는 손대지 않는다.**
"""
from __future__ import annotations

import contextlib
import io
import sys

import job_crawling_ochestrator as orch

from .helpers import check, check_equal, read_csv, temp_dir, write_csv


def _result(site, code=0, rows=0, log="", error="", seconds=1.0, output=None):
    return orch.Result(site=site, code=code, rows=rows, log=log, error=error,
                       seconds=seconds, output=output)


def _image(code=0, log=""):
    """이미지 판독 단계의 결과. **뜻풀이 표가 스크래퍼와 다르다.**"""
    return orch.Result(site="이미지판독", code=code, log=log,
                       meanings=orch.IMAGE_EXIT_MEANING)


def _fakes_with_csvs():
    """여섯 사이트가 저마다 한 행짜리 CSV 를 냈다고 치자. 합치기가 진짜로 돌 재료다."""
    home = temp_dir()
    fakes = {}
    for number, site in enumerate(orch.SITES, start=1):
        path = write_csv(home / ("%s.csv" % site),
                         [{"기업명": site, "URL": "https://ex/%d" % number}],
                         list(orch.COLUMNS))
        fakes[site] = _result(site, rows=1, output=path)
    return fakes


def _main_with(fake_results, image):
    """`main()` 을 **통째로** 돌린다. 자식 프로세스는 하나도 안 띄운다.

    스크래퍼(`_run_one`)와 이미지 단계(`_run_image_stage`)만 가짜로 바꾸고 **합치기는
    진짜를 돌린다** — 어디로 쓰는지만 임시 폴더로 옮긴다. 그래야 "합친 뒤에 부른다" 와
    "이미지 단계가 실패해도 합본은 남는다" 가 말이 아니라 사실로 확인된다.

    `(종료코드, 벌어진 일의 차례, 합본 경로, 화면에 찍힌 것)` 을 준다.
    """
    home = temp_dir()
    events = []
    real_merge = orch.merge_csvs

    def merge(paths, output):
        events.append("합치기")
        return real_merge(paths, output)

    def image_stage():
        events.append("이미지")
        return image

    saved = (orch._run_one, orch._run_image_stage, orch.merge_csvs,
             orch.ROOT_DIR, orch.OUTPUT)
    orch._run_one = lambda site, path: fake_results[site]
    orch._run_image_stage = image_stage
    orch.merge_csvs = merge
    orch.ROOT_DIR, orch.OUTPUT = home, home / "csv" / "merged.csv"
    noise = io.StringIO()
    try:
        with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
            code = orch.main()
    finally:
        (orch._run_one, orch._run_image_stage, orch.merge_csvs,
         orch.ROOT_DIR, orch.OUTPUT) = saved
    return code, events, home / "csv" / "merged.csv", noise.getvalue()


class _Done:
    """`subprocess.run` 이 돌려주는 것 흉내."""
    def __init__(self, code=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = code, stdout, stderr


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


def test_NORMAL_image_stage_runs_after_merging():
    """합본이 있어야 읽을 것이 있다. **순서가 뒤집히면 빈 파일을 읽는다.**

    글자만 견주면(예전처럼 `inspect.getsource` 로 문자열 위치를 재면) 호출이 사라져도
    통과하거나 `ValueError` 로 터진다 — 실패가 아니라 오류로. 그래서 진짜로 돌린다.
    """
    code, events, merged, _ = _main_with(_fakes_with_csvs(), _image(code=0))
    check_equal(events, ["합치기", "이미지"], "합치기가 먼저다: %r" % events)
    check_equal(code, 0, "둘 다 멀쩡하면 0")
    check_equal(len(read_csv(merged)), len(orch.SITES), "합본에 여섯 행이 들어 있다")


def test_BOUNDARY_image_stage_is_a_child_process_not_an_import():
    # 불러들이면 오케스트레이터가 피하려던 `sys.path` 오염을 새로 만든다.
    # **무엇으로 부르는지**를 본다 — 소스에 "subprocess" 라는 글자가 있는지가 아니라.
    calls = []
    saved = orch.subprocess.run

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return _Done(code=0, stdout="이미지 본문 0건을 읽습니다")

    orch.subprocess.run = fake_run
    try:
        result = orch._run_image_stage()
    finally:
        orch.subprocess.run = saved

    check_equal(len(calls), 1, "한 번 불러야 한다")
    argv, kwargs = calls[0]
    check_equal(argv, [sys.executable, orch.IMAGE_STAGE.name],
                "엔트리포인트를 자식 프로세스로 부른다")
    check_equal(kwargs["cwd"], orch.ROOT_DIR, "저장소 뿌리에서 돈다")
    check_equal(result.code, 0, "자식의 종료 코드를 그대로 읽는다")
    check("이미지 본문" in result.log, "자식이 한 말을 붙잡아 둔다")


def test_BOUNDARY_image_stage_failure_does_not_lose_the_merged_file():
    # 이 단계가 실패해도 `merged.csv` 는 이미 나와 있다. **걷은 것을 잃으면 안 된다.**
    code, events, merged, screen = _main_with(_fakes_with_csvs(), _image(code=2))
    check_equal(events, ["합치기", "이미지"], "합치기는 이미 끝났다: %r" % events)
    check(merged.exists(), "합본 파일이 남아 있어야 한다: %s" % merged)
    check_equal(len(read_csv(merged)), len(orch.SITES), "걷은 행을 하나도 잃지 않는다")
    check_equal(code, 1, "그래도 오케스트레이터 자신은 1 로 끝난다")
    check("csv/merged.csv 는 그대로 있습니다" in screen, "그렇다고 사람에게 말해 준다")


def test_EXCEPTION_a_scraper_failure_and_an_image_failure_each_give_exit_one():
    # 둘은 서로 다른 이유다. 하나만 실패해도 1 이어야 하고, 다른 하나를 가려서도 안 된다.
    check_equal(_main_with(_fakes_with_csvs(), _image(code=0))[0], 0, "둘 다 멀쩡하면 0")

    broken = _fakes_with_csvs()
    broken["saramin"] = _result("saramin", code=1, log="설정 오류: SARAMIN_X 가 비었습니다")
    code, _events, _merged, screen = _main_with(broken, _image(code=0))
    check_equal(code, 1, "스크래퍼 하나가 실패하면 1")
    check("SARAMIN_X" in screen, "스크래퍼가 한 말을 그대로 보여 준다")

    check_equal(_main_with(_fakes_with_csvs(), _image(code=1))[0], 1,
                "이미지 단계만 실패해도 1")


def test_BOUNDARY_image_stage_does_not_borrow_the_scrapers_wording():
    """**`2` 가 "차단이거나 상세를 못 받음" 으로 찍히면 엉뚱한 곳을 뒤진다.**

    이 단계는 사이트를 긁지 않는다. 숫자 계약은 같아도 그 코드가 가리키는 사건이 다르다.
    """
    image = _image(code=2)
    check(not image.ok, "2 는 실패다")
    check("차단" not in image.meaning, "차단은 이 단계의 말이 아니다: %s" % image.meaning)
    check("못 읽" in image.meaning, "무엇이 안 됐는지 말해야 한다: %s" % image.meaning)
    check_equal(orch.EXIT_MEANING[2][0],
                "온전히 못 걷음 — 차단이거나 상세를 못 받음 (모은 것은 저장됨)",
                "스크래퍼 표는 건드리지 않는다")
    _code, _events, _merged, screen = _main_with(_fakes_with_csvs(), _image(code=2))
    check("차단" not in screen, "화면에도 안 새어 나가야 한다")


def test_BOUNDARY_the_image_stage_has_no_skip_code():
    # `4`(조건이 넓어 건너뜀)는 잡플래닛의 신호다. 이 단계에는 건너뛸 조건이 없다.
    check(4 not in orch.IMAGE_EXIT_MEANING, "건너뜀은 이 단계에 없다")
    for code in (0, 1, 2, 3):
        check(code in orch.IMAGE_EXIT_MEANING, "%d 의 뜻이 없다" % code)
    ok = {code for code, (_, good) in orch.IMAGE_EXIT_MEANING.items() if good}
    check_equal(ok, {0}, "성공으로 세는 코드는 0 뿐이어야 한다: %r" % ok)


def test_BOUNDARY_image_stage_does_not_report_a_leftover_output_file():
    # 이 단계가 파일을 쓰기 전에 끝났으면 거기 있는 `merged_read.csv` 는 **지난 실행의
    # 것**이다. 그걸 이번 결과로 적어 두면 언젠가 지난 데이터가 이번 것으로 보고된다.
    saved = orch.subprocess.run
    orch.subprocess.run = lambda argv, **kwargs: _Done(code=1, stderr="merged.csv 가 없습니다")
    try:
        result = orch._run_image_stage()
    finally:
        orch.subprocess.run = saved
    check_equal(result.rows, 0, "지난 실행이 남긴 행 수를 이번 결과로 적지 않는다")
    check_equal(result.output, None, "가리킬 산출물이 없다")
