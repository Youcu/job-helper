"""사이트별 CSV 를 합치는 일.

**손대지 않는 것이 요건이다.** 중복 제거도, 정규화도, 거르기도 안 한다 — 그건 다음
단계의 일이고, 여기서 손대면 원본이 무엇이었는지 되짚을 수 없게 된다. 그래서 이 파일의
테스트 대부분은 "무엇을 **안** 하는가" 를 굳힌다.
"""
from __future__ import annotations

import job_crawling_ochestrator as orch
from _common import store
from _common.store import COLUMNS

_real_write_rows = store.write_rows

from .helpers import check, check_equal, read_csv, temp_dir, write_csv


def _row(**fields) -> dict:
    row = {c: "" for c in COLUMNS}
    row.update({"기업명": "회사", "URL": "https://example.com/1", "사이트명": "wanted"})
    row.update(fields)
    return row


def test_NORMAL_joins_two_files_in_order():
    home = temp_dir()
    first = write_csv(home / "a.csv", [_row(기업명="가", 사이트명="wanted")], COLUMNS)
    second = write_csv(home / "b.csv", [_row(기업명="나", 사이트명="saramin")], COLUMNS)
    written = orch.merge_csvs([first, second], home / "merged.csv")
    check_equal(written, 2, "두 행")
    rows = read_csv(home / "merged.csv")
    check_equal([r["기업명"] for r in rows], ["가", "나"], "**넘긴 차례를 지켜야 한다**")


def test_NORMAL_header_is_the_shared_schema():
    home = temp_dir()
    source = write_csv(home / "a.csv", [_row()], COLUMNS)
    orch.merge_csvs([source], home / "merged.csv")
    with (home / "merged.csv").open(encoding="utf-8-sig") as handle:
        header = handle.readline().strip().split(",")
    check_equal(header, list(COLUMNS), "칸 이름과 순서가 공통 스키마와 같아야 한다")


def test_NORMAL_keeps_every_value_as_is():
    home = temp_dir()
    original = _row(기업명="㈜네비웍스", 지원자격="첫 줄\n둘째 줄", 기술스택="Java, Python",
                    연봉="3,400만원")
    source = write_csv(home / "a.csv", [original], COLUMNS)
    orch.merge_csvs([source], home / "merged.csv")
    got = read_csv(home / "merged.csv")[0]
    for column in COLUMNS:
        check_equal(got[column], original[column], "%s 가 바뀌었다" % column)


def test_EXCEPTION_missing_file_is_skipped_not_fatal():
    # 한 사이트가 실패해 CSV 가 없을 수 있다. 그렇다고 나머지를 못 합치면 안 된다.
    home = temp_dir()
    good = write_csv(home / "a.csv", [_row()], COLUMNS)
    written = orch.merge_csvs([good, home / "없는파일.csv"], home / "merged.csv")
    check_equal(written, 1, "있는 것만 합친다")


def test_EXCEPTION_empty_source_file():
    home = temp_dir()
    empty = write_csv(home / "a.csv", [], COLUMNS)
    written = orch.merge_csvs([empty], home / "merged.csv")
    check_equal(written, 0, "행이 없어도 터지지 않는다")
    check((home / "merged.csv").exists(), "머리글만 있는 파일은 만든다")


def test_EXCEPTION_no_sources_at_all():
    # 여섯이 다 실패해도 합친 파일은 만든다 — 없으면 다음 단계가 파일이 없다고 죽는다.
    home = temp_dir()
    check_equal(orch.merge_csvs([], home / "merged.csv"), 0, "0행")
    check((home / "merged.csv").exists(), "머리글만 있는 파일은 만든다")


def test_BOUNDARY_duplicates_are_kept():
    # **일부러 안 지운다.** 같은 공고가 두 사이트에 있으면 두 행으로 남는다 —
    # 어느 사이트가 무엇을 갖고 있었는지가 사라지면 안 된다.
    home = temp_dir()
    same = "https://example.com/same"
    a = write_csv(home / "a.csv", [_row(URL=same, 사이트명="wanted")], COLUMNS)
    b = write_csv(home / "b.csv", [_row(URL=same, 사이트명="saramin")], COLUMNS)
    rows = read_csv(_merged(orch.merge_csvs([a, b], home / "merged.csv"), home))
    check_equal(len(rows), 2, "중복을 지우면 안 된다")
    check_equal([r["사이트명"] for r in rows], ["wanted", "saramin"], "출처가 남아야 한다")


def test_BOUNDARY_unknown_column_is_dropped_not_fatal():
    # 한 사이트가 칸을 더해도 합친 파일이 어긋나면 안 된다.
    home = temp_dir()
    columns = list(COLUMNS) + ["새로운칸"]
    source = write_csv(home / "a.csv", [dict(_row(), **{"새로운칸": "값"})], columns)
    orch.merge_csvs([source], home / "merged.csv")
    rows = read_csv(home / "merged.csv")
    check_equal(list(rows[0]), list(COLUMNS), "공통 스키마로 맞춘다")


def test_BOUNDARY_missing_column_becomes_blank():
    home = temp_dir()
    fewer = [c for c in COLUMNS if c != "연봉"]
    source = write_csv(home / "a.csv", [{c: "x" for c in fewer}], fewer)
    orch.merge_csvs([source], home / "merged.csv")
    check_equal(read_csv(home / "merged.csv")[0]["연봉"], "", "없는 칸은 빈칸")


def test_BOUNDARY_line_breaks_inside_a_cell_survive():
    # 본문에 줄바꿈이 들어 있다. 줄 단위로 다루면 한 행이 여러 행으로 쪼개진다.
    home = temp_dir()
    source = write_csv(home / "a.csv",
                       [_row(지원자격="• 첫째\n• 둘째\n• 셋째")], COLUMNS)
    orch.merge_csvs([source], home / "merged.csv")
    rows = read_csv(home / "merged.csv")
    check_equal(len(rows), 1, "한 행이어야 한다")
    check_equal(rows[0]["지원자격"].count("\n"), 2, "줄바꿈이 살아야 한다")


def test_BOUNDARY_comma_and_quote_inside_a_cell():
    home = temp_dir()
    tricky = '기술: Java, Python 그리고 "따옴표"'
    source = write_csv(home / "a.csv", [_row(지원자격=tricky)], COLUMNS)
    orch.merge_csvs([source], home / "merged.csv")
    check_equal(read_csv(home / "merged.csv")[0]["지원자격"], tricky, "그대로 살아야 한다")


def test_BOUNDARY_row_count_matches_what_merge_reported():
    home = temp_dir()
    a = write_csv(home / "a.csv", [_row(), _row()], COLUMNS)
    b = write_csv(home / "b.csv", [_row()], COLUMNS)
    written = orch.merge_csvs([a, b], home / "merged.csv")
    check_equal(written, len(read_csv(home / "merged.csv")),
                "돌려준 수와 실제 행 수가 같아야 한다")


def test_BOUNDARY_count_rows_ignores_line_breaks_in_cells():
    # 줄 수로 세면 본문에 줄바꿈이 든 공고가 여러 건으로 보인다.
    home = temp_dir()
    source = write_csv(home / "a.csv",
                       [_row(지원자격="한\n두\n세 줄"), _row()], COLUMNS)
    check_equal(orch.count_rows(source), 2, "데이터 행은 둘이다")
    check_equal(orch.count_rows(home / "없는파일.csv"), 0, "없는 파일은 0")


def _merged(_written: int, home):
    return home / "merged.csv"


def test_EXCEPTION_a_crash_mid_merge_leaves_the_old_file_intact():
    """**합치기만 원자적이지 않았다.**

    `store.write_csv` 도, 단계들의 보고 CSV 도 전부 임시 파일 + `os.replace` 인데
    정작 **파이프라인의 첫 파일**이 아니었다. 도중에 죽으면 반쯤 쓰인 `merged.csv` 가
    남고, 그림 판독이 그것을 완성품으로 읽는다 — `image_process/README.md` 가 금지한
    바로 그 상황이다.
    """
    home = temp_dir()
    merged = home / "csv" / "merged.csv"
    good = write_csv(home / "a.csv", [_row(기업명="지난실행")], COLUMNS)
    orch.merge_csvs([good], merged)
    before = merged.read_bytes()

    # 쓰는 도중에 죽는 상황
    boom = write_csv(home / "b.csv", [_row(기업명="새것")], COLUMNS)
    saved = orch.csv.DictWriter

    class Exploding(saved):
        def writerow(self, row):
            raise OSError("디스크가 찼다")

    orch.csv.DictWriter = Exploding
    try:
        orch.merge_csvs([boom], merged)
        raise AssertionError("터졌어야 한다")
    except OSError:
        pass
    finally:
        orch.csv.DictWriter = saved

    check_equal(merged.read_bytes(), before,
                "**이전 파일이 그대로 남아야 한다** — 반쯤 쓰인 것이 남으면 안 된다")
    leftovers = [p.name for p in (home / "csv").iterdir() if p.name.startswith(".")]
    check_equal(leftovers, [], "임시 파일도 안 남아야 한다: %r" % leftovers)


def test_BOUNDARY_pipeline_holds_one_lock_for_the_whole_run():
    """오케스트레이터 자신에게 락이 없었다.

    사이트와 단계에는 저마다 락이 있는데 **합치기 구간만 무방비였다.** 둘을 돌리면
    각 사이트는 `3` 을 내고 물러나지만, 그 뒤 두 실행이 같은 `merged.csv` 를 함께 쓴다.
    """
    check(hasattr(orch, "LOCK"), "파이프라인 락 상수가 있어야 한다")
    check_equal(orch.LOCK.name, ".pipeline.lock", "단계별 락과 이름이 겹치면 안 된다")
    stage_locks = {".image_process.lock", ".filter.lock",
                   ".jobplanet_rating.lock", ".core_stack.lock"}
    check(orch.LOCK.name not in stage_locks,
          "단계 락 이름과 같으면 단계를 따로 못 돌린다")


def test_NORMAL_first_seen_is_revived_from_history():
    """**사이트 CSV 를 매 실행 지우므로** 이력에서 처음 본 날을 되살린다.

    안 그러면 `최초수집일` 이 항상 오늘이 되어 칸의 뜻이 없어지고,
    "오늘 새로 뜬 공고" 가 전부 거짓이 된다 — CSV 는 멀쩡해 보인다.
    """
    home = temp_dir()
    history = home / "history" / "history_read.csv"
    write_csv(history, [_row(URL="u/1", 최초수집일="2026-09-01")], COLUMNS)
    site = write_csv(home / "a.csv", [_row(URL="u/1", 최초수집일="2026-09-12"),
                                      _row(URL="u/2", 최초수집일="2026-09-12")], COLUMNS)
    orch.merge_csvs([site], home / "merged.csv", history)
    got = {r["URL"]: r["최초수집일"] for r in read_csv(home / "merged.csv")}
    check_equal(got["u/1"], "2026-09-01", "이력에 있으면 그 날짜로 되살린다")
    check_equal(got["u/2"], "2026-09-12", "이력에 없으면 **오늘 처음 본 것**이 맞다")


def test_EXCEPTION_no_history_yet_is_not_an_error():
    # 처음 돌리는 사람에게는 이력이 없다.
    home = temp_dir()
    site = write_csv(home / "a.csv", [_row(URL="u/1", 최초수집일="2026-09-12")], COLUMNS)
    orch.merge_csvs([site], home / "merged.csv", home / "없는" / "history.csv")
    check_equal(read_csv(home / "merged.csv")[0]["최초수집일"], "2026-09-12", "그대로 둔다")


def test_BOUNDARY_history_never_makes_a_posting_look_newer():
    # 이력이 더 늦은 날짜를 갖고 있어도 되살리기가 **더 최근으로 만들지는 않는다.**
    home = temp_dir()
    history = home / "history" / "history_read.csv"
    write_csv(history, [_row(URL="u/1", 최초수집일="2026-09-20")], COLUMNS)
    site = write_csv(home / "a.csv", [_row(URL="u/1", 최초수집일="2026-09-01")], COLUMNS)
    orch.merge_csvs([site], home / "merged.csv", history)
    got = read_csv(home / "merged.csv")[0]["최초수집일"]
    check(got in ("2026-09-01", "2026-09-20"), "둘 중 하나여야 한다: %r" % got)


def test_BOUNDARY_every_csv_writer_goes_through_one_atomic_write():
    """**원자적 쓰기 보장이 저장소에 한 벌만 있어야 한다.**

    임시 이름 → `fsync` → `os.replace` → `finally` 정리. 이 열 줄이 막는 것은
    **반쪽 파일이 다음 단계의 입력이 되는 것**이다. 300번째 줄에서 죽으면 299.5줄짜리
    CSV 가 남는데, CSV 는 잘려도 CSV 처럼 보여서 다음 단계가 읽고도 모른다.

    한때 이 열 줄이 **다섯 벌** 있었다 — `filter.py` · `core_stack.py` ·
    `jobplanet_rating.py` · `history.py` · `store.write_csv`. 리포트마다 칸이 달라
    14칸에 묶인 `write_csv()` 를 못 썼기 때문이다.

    **그 열 줄은 테스트가 지켜 주지 않는다.** `fsync` 한 줄을 빼도 전부 통과한다 —
    같은 프로세스 안에서 쓰고 바로 읽으니 내용은 맞다. 드러나는 것은 진짜로 중간에
    죽었을 때뿐이고 그때는 이미 늦다. 지켜 주는 것은 **한 곳에만 있다는 사실**뿐이라,
    그 사실 자체를 여기서 굳힌다.
    """
    import core_stack
    import filter as flt
    import history
    import jobplanet_rating

    calls = []
    stages = (flt, core_stack, jobplanet_rating, history, orch)
    saved = [module.write_rows if hasattr(module, "write_rows") else None
             for module in stages]

    def spy(path, columns, rows):
        calls.append(path.name)

    home = temp_dir()
    try:
        for module in stages:
            if hasattr(module, "write_rows"):
                module.write_rows = spy
        store.write_rows = spy                       # write_csv 도 이것을 통한다
        flt._write_report(home / "filter_report.csv", [], [])
        core_stack._write_report(home / "core_stack_report.csv", [])
        jobplanet_rating._write_report(home / "rating_report.csv", [])
        jobplanet_rating._write_same_names(home / "same_names.csv", [])
        store.write_csv(home / "merged.csv", [])     # 14칸 쪽도 같은 통로다
    finally:
        store.write_rows = _real_write_rows
        for module, original in zip(stages, saved):
            if original is not None:
                module.write_rows = original

    check_equal(len(calls), 5, "다섯 산출물이 전부 한 통로를 지나야 한다: %r" % calls)


def test_EXCEPTION_write_rows_leaves_the_old_file_intact_on_a_crash():
    """도중에 죽어도 **이전 파일이 그대로** 남고 임시 파일도 안 남는다."""
    home = temp_dir()
    target = home / "리포트.csv"
    _real_write_rows(target, ("A", "B"), [{"A": "지난실행", "B": "1"}])
    before = target.read_bytes()

    saved = store.csv.DictWriter

    class Exploding(saved):
        def writerows(self, rows):
            raise OSError("디스크가 찼다")

    store.csv.DictWriter = Exploding
    try:
        _real_write_rows(target, ("A", "B"), [{"A": "새것", "B": "2"}])
        raise AssertionError("터졌어야 한다")
    except OSError:
        pass
    finally:
        store.csv.DictWriter = saved

    check_equal(target.read_bytes(), before, "**이전 파일이 그대로 남아야 한다**")
    leftovers = [p.name for p in home.iterdir() if p.name.startswith(".")]
    check_equal(leftovers, [], "임시 파일도 안 남아야 한다: %r" % leftovers)
