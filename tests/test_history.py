"""이력 쌓기와 뒷정리.

**이 단계는 파일을 지운다.** 그것도 사이트가 걷어 온 원본을. 그래서 여기 테스트는
"잘 지우는가" 보다 **"지우기 전에 이력이 제대로 쌓였는가"** 와 **"지우면 안 되는 것을
안 지키는가"** 를 굳힌다.

이력이 하는 일의 절반은 `최초수집일` 을 살려 두는 것이다. 그것이 틀리면 CSV 는 멀쩡해
보이는데 **"오늘 새로 뜬 공고" 가 전부 거짓**이 된다 — 눈으로는 못 잡는다.
"""
from __future__ import annotations

import csv as _csv

import history as hist
from _common.store import COLUMNS

from .helpers import check, check_equal, read_csv, temp_dir, write_csv


def _row(**fields) -> dict:
    row = {c: "" for c in COLUMNS}
    row.update({"기업명": "회사", "공고명": "백엔드", "사이트명": "wanted",
                "URL": "https://ex/1", "최초수집일": "2026-09-01",
                "최종확인일": "2026-09-01"})
    row.update(fields)
    return row


def _stage(home, rows=None, reports=True):
    """`csv/` 를 흉내 낸다. 파이프라인이 끝난 뒤의 모양."""
    csv_dir = home / "csv"
    rows = rows if rows is not None else [_row()]
    write_csv(csv_dir / "merged_read.csv", rows, COLUMNS)
    write_csv(csv_dir / "merged_career.csv", rows[:1], COLUMNS)
    if reports:
        for name, columns, line in (
                ("filter_report.csv", ("기업명", "공고명", "사이트명", "URL", "판정",
                                       "걸린낱말", "근거"),
                 {"URL": "https://ex/9", "판정": "제외 · 낱말", "걸린낱말": "SI",
                  "근거": "SI 프로젝트", "기업명": "나쁜회사", "공고명": "A", "사이트명": "saramin"}),
                ("rating_report.csv", ("기업명", "공고명", "사이트명", "URL", "판정", "평점",
                                       "잡플래닛이름", "회사id", "찾은방법"),
                 {"URL": "https://ex/8", "판정": "제외 · 평점 2.0", "평점": "2.0",
                  "잡플래닛이름": "(주)나쁜회사", "회사id": "7", "찾은방법": "원문",
                  "기업명": "나쁜회사", "공고명": "B", "사이트명": "wanted"}),
                ("core_stack_report.csv", ("기업명", "공고명", "사이트명", "URL", "판정",
                                           "기술스택"),
                 {"URL": "https://ex/7", "판정": "제외 · 핵심 기술 없음",
                  "기술스택": "Node.js", "기업명": "다른회사", "공고명": "C",
                  "사이트명": "jumpit"})):
            _write(csv_dir / name, columns, [line])
    return csv_dir


def _write(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = _csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _sites(home, names=("wanted", "saramin")):
    sites = home / "job_sites"
    for name in names:
        path = sites / name / "csv" / ("%s_post.csv" % name)
        write_csv(path, [_row(사이트명=name)], COLUMNS)
    return sites


def _read_any(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(_csv.DictReader(handle))


# ── 일반 ────────────────────────────────────────────────────────────────

def test_NORMAL_accumulates_read_and_core():
    home = temp_dir()
    code = hist._run(_stage(home), home / "history", _sites(home), today="2026-09-12")
    check_equal(code, 0, "정상 종료")
    check_equal(len(read_csv(home / "history" / "history_read.csv")), 1, "전처리 이전")
    check_equal(len(read_csv(home / "history" / "history_final.csv")), 1, "최종본")


def test_NORMAL_three_reports_become_one_file():
    """세 리포트를 한 파일로 쌓는다 — "이 공고가 왜 빠졌나" 를 URL 하나로 찾게."""
    home = temp_dir()
    hist._run(_stage(home), home / "history", _sites(home), today="2026-09-12")
    dropped = _read_any(home / "history" / hist.DROPPED)
    check_equal(len(dropped), 3, "세 리포트에서 한 줄씩")
    check_equal({r["단계"] for r in dropped}, {"거르기", "평점", "핵심기술"}, "단계가 남는다")
    check(all(r["기록일"] == "2026-09-12" for r in dropped), "언제 빠졌는지도 남는다")
    rating = [r for r in dropped if r["단계"] == "평점"][0]
    check("평점=2.0" in rating["근거"], "칸이 달라도 근거로 들어간다: %r" % rating["근거"])


def test_NORMAL_site_csvs_are_swept():
    home = temp_dir()
    sites = _sites(home)
    check_equal(len(hist.site_csvs(sites)), 2, "지우기 전에는 둘")
    hist._run(_stage(home), home / "history", sites, today="2026-09-12")
    check_equal(hist.site_csvs(sites), [], "**사이트별 수집본만 지운다**")


def test_NORMAL_the_csv_dir_is_left_alone():
    """`./csv` 는 **안 건드린다.** 사용자가 분석용·점검용으로 어떻게 쓸지 모른다."""
    home = temp_dir()
    csv_dir = _stage(home)
    before = sorted(p.name for p in csv_dir.iterdir())
    hist._run(csv_dir, home / "history", _sites(home), today="2026-09-12")
    check_equal(sorted(p.name for p in csv_dir.iterdir()), before,
                "중간 산출물도 리포트도 그대로 있어야 한다")


# ── 예외 ────────────────────────────────────────────────────────────────

def test_EXCEPTION_missing_final_output_stops_and_sweeps_nothing():
    """**파이프라인이 안 끝났으면 아무것도 안 한다.**

    반쪽 결과를 이력에 섞으면 나중에 "그때 이 공고가 없었다" 를 거짓으로 읽는다.
    그리고 사이트 CSV 를 지워 버리면 **다시 걷는 수밖에 없다.**
    """
    home = temp_dir()
    csv_dir = home / "csv"
    write_csv(csv_dir / "merged_read.csv", [_row()], COLUMNS)   # 최종본이 없다
    sites = _sites(home)
    check_equal(hist._run(csv_dir, home / "history", sites, today="2026-09-12"), 1,
                "1 로 멈춘다")
    check_equal(len(hist.site_csvs(sites)), 2, "**사이트 CSV 를 지우면 안 된다**")
    check(not (home / "history").exists(), "이력도 안 만든다")


def test_EXCEPTION_missing_reports_are_not_a_failure():
    # 뺀 행이 하나도 없으면 리포트가 비거나 없을 수 있다.
    home = temp_dir()
    check_equal(hist._run(_stage(home, reports=False), home / "history", _sites(home),
                          today="2026-09-12"), 0, "리포트가 없어도 정상")


def test_EXCEPTION_no_site_csvs_to_sweep():
    home = temp_dir()
    check_equal(hist._run(_stage(home), home / "history", home / "job_sites",
                          today="2026-09-12"), 0, "지울 것이 없어도 정상")


# ── 경계 ────────────────────────────────────────────────────────────────

def test_BOUNDARY_first_seen_survives_the_first_accumulation():
    """**결함이었다.** `store.merge()` 는 처음 보는 행의 `최초수집일` 을 오늘로 덮는다.

    스크래퍼는 날짜 없이 행을 주므로 그쪽에서는 맞다. 그런데 이력에 들어오는 행은
    `./csv` 에서 오므로 **이미 진짜 날짜를 갖고 있다.** 그대로 두면 이력을 처음
    만드는 날 **전부 오늘로 뭉개진다** — 실제로 그랬다.
    """
    home = temp_dir()
    rows = [_row(URL="u/1", 최초수집일="2026-09-01"),
            _row(URL="u/2", 최초수집일="2026-09-05")]
    hist._run(_stage(home, rows), home / "history", _sites(home), today="2026-09-12")
    got = {r["URL"]: r["최초수집일"] for r in read_csv(home / "history" / "history_read.csv")}
    check_equal(got, {"u/1": "2026-09-01", "u/2": "2026-09-05"},
                "**들어온 날짜를 지켜야 한다** — 오늘로 덮으면 안 된다")


def test_BOUNDARY_second_run_keeps_the_earlier_date():
    home = temp_dir()
    hist._run(_stage(home, [_row(URL="u/1", 최초수집일="2026-09-01")]),
              home / "history", _sites(home), today="2026-09-12")
    # 다음 실행에서 같은 공고가 늦은 날짜로 들어와도
    hist._run(_stage(home, [_row(URL="u/1", 최초수집일="2026-09-12")]),
              home / "history", _sites(home), today="2026-09-13")
    got = read_csv(home / "history" / "history_read.csv")
    check_equal(len(got), 1, "같은 URL 은 한 행")
    check_equal(got[0]["최초수집일"], "2026-09-01", "**이른 쪽이 이긴다**")


def test_BOUNDARY_dropped_keeps_the_latest_verdict_per_stage():
    # 같은 공고가 같은 단계에서 다시 빠지면 최신 판정이 맞다. 단계가 다르면 둘 다 남는다.
    home = temp_dir()
    history = home / "history"
    hist._run(_stage(home), history, _sites(home), today="2026-09-12")
    hist._run(_stage(home), history, _sites(home), today="2026-09-13")
    dropped = _read_any(history / hist.DROPPED)
    check_equal(len(dropped), 3, "세 줄 그대로 — 쌓이면 안 된다: %d" % len(dropped))
    check(all(r["기록일"] == "2026-09-13" for r in dropped), "최신 기록일")


def test_BOUNDARY_same_names_accumulate_by_company_and_id():
    home = temp_dir()
    csv_dir = _stage(home)
    columns = ("기업명", "질의", "회사id", "잡플래닛이름", "평점")
    _write(csv_dir / "same_names.csv", columns,
           [{"기업명": "제일산업", "질의": "제일산업", "회사id": "1",
             "잡플래닛이름": "제일산업(주)", "평점": "2.6"},
            {"기업명": "제일산업", "질의": "제일산업", "회사id": "2",
             "잡플래닛이름": "제일산업", "평점": "1.8"}])
    hist._run(csv_dir, home / "history", _sites(home), today="2026-09-12")
    got = _read_any(home / "history" / "history_same_names.csv")
    check_equal(len(got), 2, "회사id 가 다르면 다른 후보다")


def test_BOUNDARY_sweep_can_be_turned_off():
    # 이력만 쌓고 싶을 때가 있다 — 사람이 손으로 다시 돌려 볼 때.
    home = temp_dir()
    sites = _sites(home)
    hist._run(_stage(home), home / "history", sites, today="2026-09-12", sweep=False)
    check_equal(len(hist.site_csvs(sites)), 2, "안 지운다")


def test_BOUNDARY_only_post_csvs_are_swept():
    """사이트 폴더의 **다른 파일은 안 건드린다.**

    `ai_processed.csv` 같은 사본이 같은 폴더에 있을 수 있다. 통째로 비우면 그것까지
    사라지는데, 그건 이 단계가 만든 것이 아니다.
    """
    home = temp_dir()
    sites = _sites(home)
    other = sites / "wanted" / "csv" / "ai_processed.csv"
    other.write_text("남겨야 한다", encoding="utf-8")
    hist._run(_stage(home), home / "history", sites, today="2026-09-12")
    check(other.exists(), "`*_post.csv` 가 아닌 것은 지우면 안 된다")
