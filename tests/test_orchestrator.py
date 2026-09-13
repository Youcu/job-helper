"""여섯 사이트를 돌리고 결과를 판정하는 일.

**가장 중요한 것은 종료 코드를 옳게 읽는가**다. `4`(조건이 넓어 건너뜀)를 실패로 읽으면
파이프라인 전체가 멎고, `2`(차단)를 정상으로 읽으면 절반만 든 CSV 를 온전한 것으로
착각한다. 그 판정이 이 파일의 절반이다.

이미지 판독 단계의 **배선**도 여기서 본다 — 합친 뒤에 부르는가, 그 단계가 실패해도 합본이
남는가, 어느 쪽이 실패하든 1 로 끝나는가. 소스 문자열을 견주지 않고 `main()` 을 실제로
돌린다. 글자만 보면 호출이 통째로 사라져도 통과하거나 오류로 터진다 — 실패가 아니라.

자식 프로세스도 네트워크도 타지 않는다 — `_run_one` 과 `_run_stage` 를 가짜로 바꿔
넣고, 합치기는 진짜를 임시 폴더에 돌린다. **저장소의 `csv/` 에는 손대지 않는다.**
"""
from __future__ import annotations

import contextlib
import io
import sys

import job_crawling_ochestrator as orch

from .helpers import check, check_equal, read_csv, temp_dir, write_csv


def _result(site, code=0, rows=0, log="", error="", seconds=1.0, output=None, err=""):
    return orch.Result(site=site, code=code, rows=rows, log=log, error=error,
                       seconds=seconds, output=output, err=err)


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


def _main_with(fake_results, image, filtered=None, rated=None, cored=None,
               historied=None):
    """`main()` 을 **통째로** 돌린다. 자식 프로세스는 하나도 안 띄운다.

    스크래퍼(`_run_one`)와 수집 뒤 단계(`_run_stage`)만 가짜로 바꾸고 **합치기는
    진짜를 돌린다** — 어디로 쓰는지만 임시 폴더로 옮긴다. 그래야 "합친 뒤에 부른다" 와
    "이미지 단계가 실패해도 합본은 남는다" 가 말이 아니라 사실로 확인된다.

    `filtered`·`rated` 를 안 주면 그 단계는 정상으로 끝난 것으로 둔다.

    `(종료코드, 벌어진 일의 차례, 합본 경로, 화면에 찍힌 것)` 을 준다.
    """
    home = temp_dir()
    events = []
    real_merge = orch.merge_csvs
    stages = {orch.IMAGE_STAGE.name: ("이미지", image),
              orch.FILTER_STAGE.name: ("거르기", filtered or _stage("거르기", code=0)),
              orch.RATING_STAGE.name: ("평점", rated or _stage("평점", code=0)),
              orch.CORE_STACK_STAGE.name: ("핵심기술",
                                           cored or _stage("핵심기술", code=0)),
              orch.HISTORY_STAGE.name: ("이력", historied or _stage("이력", code=0))}

    def merge(paths, output):
        events.append("합치기")
        return real_merge(paths, output)

    def run_stage(script, name, meanings, timeout=orch.TIMEOUT_SECONDS):
        label, result = stages[script.name]
        events.append(label)
        return result

    saved = (orch._run_one, orch._run_stage, orch.merge_csvs,
             orch.ROOT_DIR, orch.OUTPUT)
    orch._run_one = lambda site, path: fake_results[site]
    orch._run_stage = run_stage
    orch.merge_csvs = merge
    orch.ROOT_DIR, orch.OUTPUT = home, home / "csv" / "merged.csv"
    noise = io.StringIO()
    try:
        with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
            code = orch.main()
    finally:
        (orch._run_one, orch._run_stage, orch.merge_csvs,
         orch.ROOT_DIR, orch.OUTPUT) = saved
    return code, events, home / "csv" / "merged.csv", noise.getvalue()


def _stage(name, code=0, log=""):
    return orch.Result(site=name, code=code, log=log,
                       meanings=orch.FILTER_EXIT_MEANING)


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


def test_BOUNDARY_block_reason_survives_a_noisy_stdout():
    """**결함이었다.** 스크래퍼가 `403 으로 막았습니다` 를 stdout 에 찍었는데, stdout 끝
    8줄은 뒤따라 나온 안내문이 차지해 정작 왜 막혔는지가 화면에서 사라졌다.

    403(차단)과 429(속도 제한)는 대응이 정반대다. 그 한 줄이 다음 실행을 가른다.
    이제 스크래퍼는 멈춘 이유를 stderr 로 말하고, 여기서는 그것을 **먼저 통째로** 보여 준다.
    """
    reason = "차단됨: 잡플래닛이 403 로 막았습니다 (https://…/postings/1)."
    noise = "\n".join("안내 %d줄" % n for n in range(1, 21))
    result = _result("jobplanet", code=2, err=reason + "\n차단돼서 0건에서 멈췄습니다.",
                     log=noise + "\n" + reason + "\n" + noise)

    shown = _captured_failure_report([result])
    check("403" in shown, "왜 막혔는지가 남아야 한다:\n%s" % shown)
    check("차단됨" in shown, "스크래퍼가 한 말이 남아야 한다")


def test_BOUNDARY_failure_report_falls_back_when_there_is_no_stderr():
    # 아무 말 없이 죽는 스크래퍼도 있다. 그때는 진행 기록 끝부분만 보여 준다.
    result = _result("jumpit", code=1, err="", log="설정 오류: YOE 가 비어 있습니다")
    shown = _captured_failure_report([result])
    check("YOE" in shown, "stderr 가 없어도 stdout 끝은 보여야 한다:\n%s" % shown)
    check("스크래퍼가 말한 것" not in shown, "빈 stderr 에 머리말을 달지 않는다")


def _captured_failure_report(results) -> str:
    import contextlib, io
    buffer = io.StringIO()
    with contextlib.redirect_stderr(buffer):
        orch._print_failures(results)
    return buffer.getvalue()


def test_BOUNDARY_first_lines_takes_the_start_not_the_end():
    # stderr 는 앞쪽이 이유다 — 처음 막힌 곳이 원인이고 뒤는 그 여파다.
    text = "\n".join("줄 %d" % n for n in range(1, 21))
    check_equal(orch._first_lines(text, 3), ["줄 1", "줄 2", "줄 3"], "앞에서 셋")
    check_equal(orch._first_lines("", 5), [], "빈 글")
    check_equal(orch._first_lines(None, 5), [], "글이 없어도 터지지 않는다")


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


def test_NORMAL_stages_run_in_order_after_merging():
    """합본이 있어야 읽을 것이 있다. **순서가 뒤집히면 빈 파일을 읽는다.**

    글자만 견주면(예전처럼 `inspect.getsource` 로 문자열 위치를 재면) 호출이 사라져도
    통과하거나 `ValueError` 로 터진다 — 실패가 아니라 오류로. 그래서 진짜로 돌린다.
    """
    code, events, merged, _ = _main_with(_fakes_with_csvs(), _image(code=0))
    check_equal(events, ["합치기", "이미지", "거르기", "평점", "핵심기술", "이력"],
                "차례가 이것이다: %r" % events)
    check_equal(code, 0, "여섯 다 멀쩡하면 0")
    check_equal(len(read_csv(merged)), len(orch.SITES), "합본에 여섯 행이 들어 있다")


def test_EXCEPTION_filter_is_not_called_when_the_image_stage_died():
    """**앞이 죽으면 뒤를 안 부른다.**

    거르기의 입력은 앞 단계가 낸 파일이다. 앞이 죽었으면 거기 있는 것은 지난 실행이 남긴
    것이고, 그걸 걸러 내면 **어제 결과가 오늘 것처럼** 나온다 — 터지지 않으니 더 나쁘다.
    """
    code, events, _merged, _ = _main_with(_fakes_with_csvs(), _image(code=2))
    check("거르기" not in events, "부르면 안 된다: %r" % events)
    check_equal(code, 1, "그래도 1 로 끝난다")


def test_EXCEPTION_filter_failure_alone_gives_exit_one():
    code, events, merged, screen = _main_with(
        _fakes_with_csvs(), _image(code=0), _stage("거르기", code=1))
    check_equal(events, ["합치기", "이미지", "거르기"], "거기까지는 부른다")
    check("평점" not in events, "**거르기가 죽으면 평점도 안 부른다**: %r" % events)
    check_equal(code, 1, "거르기만 실패해도 1 이어야 자동화가 성공으로 안 읽는다")
    check(merged.exists(), "**걷은 것은 남아 있어야 한다**")
    check("csv/merged_read.csv 는 그대로 있습니다" in screen,
          "무엇이 안 지워졌는지 말해 준다: %r" % screen[-300:])


def test_BOUNDARY_filter_stage_has_no_partial_failure_code():
    # `2`(부분 실패)와 `4`(건너뜀)는 이 단계에 없는 사건이다. 표에 적어 두면
    # 있지도 않은 일이 화면에 찍힌다.
    for absent in (2, 4):
        check(absent not in orch.FILTER_EXIT_MEANING, "%d 는 이 단계에 없다" % absent)
    for present in (0, 1, 3):
        check(present in orch.FILTER_EXIT_MEANING, "%d 의 뜻이 없다" % present)
    ok = {code for code, (_, good) in orch.FILTER_EXIT_MEANING.items() if good}
    check_equal(ok, {0}, "성공으로 세는 코드는 0 뿐: %r" % ok)


def test_BOUNDARY_filter_stage_does_not_borrow_another_stages_wording():
    check_equal(orch.FILTER_EXIT_MEANING[1][0], "단계를 못 돌림 — merged_read.csv 가 없음",
                "이 단계가 읽는 파일을 말해야 한다")
    check("claude" not in orch.FILTER_EXIT_MEANING[1][0],
          "거르기는 모델을 안 부른다")


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
        result = orch._run_stage(orch.IMAGE_STAGE, "이미지판독",
                                 orch.IMAGE_EXIT_MEANING)
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
        result = orch._run_stage(orch.IMAGE_STAGE, "이미지판독",
                                 orch.IMAGE_EXIT_MEANING)
    finally:
        orch.subprocess.run = saved
    check_equal(result.rows, 0, "지난 실행이 남긴 행 수를 이번 결과로 적지 않는다")
    check_equal(result.output, None, "가리킬 산출물이 없다")


def test_EXCEPTION_rating_is_not_called_when_filtering_died():
    """평점 걷기는 **거르기가 낸 파일**을 읽는다. 앞이 죽었으면 거기 있는 것은 지난 것이다.

    이 단계는 그물을 타고 한 시간 넘게 돈다. 지난 파일로 그걸 돌리면 시간만 버리는 것이
    아니라, **어제 공고 목록으로 오늘 평점을 걷어** 결과가 맞는 것처럼 보인다.
    """
    code, events, _merged, _ = _main_with(_fakes_with_csvs(), _image(code=0),
                                          _stage("거르기", code=1))
    check("평점" not in events, "부르면 안 된다: %r" % events)
    check_equal(code, 1, "그래도 1 로 끝난다")


def test_EXCEPTION_partly_collected_rating_is_not_counted_as_success():
    # `2` 는 "걷은 것은 저장됐다" 는 뜻이지만, 덜 걷힌 평점으로 거른 결과를 온전한
    # 것으로 읽으면 안 된다. 종료 코드는 1 이어야 한다.
    code, events, _merged, screen = _main_with(_fakes_with_csvs(), _image(code=0),
                                               None, _stage("평점", code=2))
    check("핵심기술" not in events, "평점이 덜 걷혔으면 핵심 기술도 안 부른다: %r" % events)
    check_equal(code, 1, "덜 걷었으면 성공이 아니다")
    check("csv/merged_filtered.csv 는 그대로 있습니다" in screen,
          "무엇이 안 지워졌는지 말해 준다")


def test_BOUNDARY_rating_stage_has_its_own_exit_table():
    # `4`(건너뜀)는 잡플래닛 **수집기**의 신호다. 이 단계에는 건너뛸 조건이 없다.
    check(4 not in orch.RATING_EXIT_MEANING, "건너뜀은 이 단계에 없다")
    for code in (0, 1, 2, 3):
        check(code in orch.RATING_EXIT_MEANING, "%d 의 뜻이 없다" % code)
    ok = {c for c, (_, good) in orch.RATING_EXIT_MEANING.items() if good}
    check_equal(ok, {0}, "성공으로 세는 코드는 0 뿐: %r" % ok)
    check("이어감" in orch.RATING_EXIT_MEANING[2][0],
          "2 는 다시 돌리면 된다고 말해야 한다: %s" % orch.RATING_EXIT_MEANING[2][0])


def test_BOUNDARY_rating_timeout_is_much_longer_than_the_others():
    # 그물을 타는 단계다. 스크래퍼 하나에 맞춘 30분을 그대로 쓰면 중간에 끊긴다.
    check(orch.RATING_TIMEOUT > orch.FILTER_TIMEOUT * 10,
          "평점 제한 시간이 거르기와 같은 자릿수면 안 된다: %d초" % orch.RATING_TIMEOUT)


def test_EXCEPTION_core_stack_is_not_called_when_rating_died():
    code, events, _merged, _ = _main_with(_fakes_with_csvs(), _image(code=0), None,
                                          _stage("평점", code=2))
    check("핵심기술" not in events, "앞이 덜 걷었으면 안 부른다: %r" % events)
    check_equal(code, 1, "1 로 끝난다")


def test_BOUNDARY_core_stack_exit_table_names_the_env_setting():
    """`1` 의 뜻에 **`.env` 항목 이름**이 들어가야 한다.

    이 단계만 `CORE_TECH_STACKS` 를 읽는다. 다른 단계의 표를 빌려 쓰면 "단계를 못 돌림"
    이라고만 찍혀서, 사람이 어느 파일의 어느 줄을 고쳐야 할지 못 짚는다.
    """
    check("CORE_TECH_STACKS" in orch.CORE_STACK_EXIT_MEANING[1][0],
          orch.CORE_STACK_EXIT_MEANING[1][0])
    check(2 not in orch.CORE_STACK_EXIT_MEANING, "부분 실패라는 것이 없다")
    ok = {c for c, (_, good) in orch.CORE_STACK_EXIT_MEANING.items() if good}
    check_equal(ok, {0}, "성공은 0 뿐: %r" % ok)


def test_EXCEPTION_history_is_not_called_when_core_stack_died():
    """**최종본까지 다 나왔을 때만 이력을 쌓는다.**

    중간에 멈춘 실행의 반쪽 결과를 이력에 섞으면, 나중에 "그때 이 공고가 없었다" 를
    거짓으로 읽는다. 그리고 이력 단계는 **사이트 CSV 를 지우므로** 더 위험하다 —
    반쪽 결과를 쌓고 원본까지 지우면 다시 걷는 수밖에 없다.
    """
    code, events, _merged, _ = _main_with(_fakes_with_csvs(), _image(code=0), None, None,
                                          _stage("핵심기술", code=1))
    check("이력" not in events, "앞이 죽었으면 안 부른다: %r" % events)
    check_equal(code, 1, "1 로 끝난다")


def test_BOUNDARY_history_exit_table_says_the_pipeline_did_not_finish():
    check("merged_core.csv" in orch.HISTORY_EXIT_MEANING[1][0],
          orch.HISTORY_EXIT_MEANING[1][0])
    check(2 not in orch.HISTORY_EXIT_MEANING, "부분 실패라는 것이 없다")
    ok = {c for c, (_, good) in orch.HISTORY_EXIT_MEANING.items() if good}
    check_equal(ok, {0}, "성공은 0 뿐: %r" % ok)


def test_BOUNDARY_every_stage_in_the_table_fails_the_run():
    """**표에 있는 단계는 전부 종료 코드에 반영된다** — 새로 더한 단계도 자동으로.

    전에는 단계마다 배선을 손으로 적고 **마지막에 `stages` 목록에도 또 적었다.**
    목록에 적는 것을 빠뜨리면 그 단계가 실패해도 종료 코드가 `0` 이 된다 — 화면에는
    "실패했습니다" 가 찍히는데 자동화는 성공으로 읽는다. 터지지도 멈추지도 않는다.

    이 테스트는 `STAGES` 를 **돌면서** 확인하므로, 표에 한 줄을 더하면 검사도 같이
    늘어난다. 새 단계를 배선에서 빠뜨릴 자리가 없다.
    """
    for index, (script, name, _meanings, _timeout, _kept) in enumerate(orch.STAGES):
        home = temp_dir()
        events = []
        broken = orch.Result(site=name, code=1, log="",
                             meanings=orch.FILTER_EXIT_MEANING)
        fine = orch.Result(site=name, code=0, log="",
                           meanings=orch.FILTER_EXIT_MEANING)

        def run_stage(target, label, meanings, timeout=orch.TIMEOUT_SECONDS,
                      _script=script):
            events.append(target.name)
            return broken if target.name == _script.name else fine

        saved = (orch._run_one, orch._run_stage, orch.ROOT_DIR, orch.OUTPUT)
        orch._run_one = lambda site, path: _fakes_with_csvs()[site]
        orch._run_stage = run_stage
        orch.ROOT_DIR, orch.OUTPUT = home, home / "csv" / "merged.csv"
        noise = io.StringIO()
        try:
            with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
                code = orch.main()
        finally:
            (orch._run_one, orch._run_stage, orch.ROOT_DIR, orch.OUTPUT) = saved

        check_equal(code, 1, "%s 가 실패하면 종료 코드 1: %d" % (name, code))
        check_equal(len(events), index + 1,
                    "%s 에서 멈춰야 한다 — 뒤를 부르면 지난 실행 파일을 다듬는다: %r"
                    % (name, events))
        check("%s 단계가 실패했습니다" % name in noise.getvalue(),
              "**어느 단계가 죽었는지 이름으로 말해야 한다**: %s" % name)


def test_BOUNDARY_each_stage_names_the_file_that_did_not_change():
    """실패 메시지는 **무엇이 안 바뀌었나**를 말한다 — 사람이 다음에 뭘 할지 정하는 재료다.

    앞 단계가 남긴 파일 이름을 대야 "그럼 그것부터 다시" 를 판단할 수 있다. 표의
    다섯째 칸이 그 자리이고, 비어 있으면 메시지가 반쪽이 된다.
    """
    for _script, name, _meanings, _timeout, kept in orch.STAGES:
        check(kept.strip(), "%s 에 앞 단계 산출물이 적혀 있어야 한다" % name)
