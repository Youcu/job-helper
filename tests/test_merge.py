"""사이트별 CSV 를 합치는 일.

**손대지 않는 것이 요건이다.** 중복 제거도, 정규화도, 거르기도 안 한다 — 그건 다음
단계의 일이고, 여기서 손대면 원본이 무엇이었는지 되짚을 수 없게 된다. 그래서 이 파일의
테스트 대부분은 "무엇을 **안** 하는가" 를 굳힌다.
"""
from __future__ import annotations

import job_crawling_ochestrator as orch
from _common.store import COLUMNS

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
