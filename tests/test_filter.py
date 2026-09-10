"""거르기 단계 — 중복 제거와 낱말 제외.

**이 단계는 행을 지운다.** 그래서 여기 테스트는 "잘 지우는가" 보다 **"안 지워야 할 것을
지키는가"** 를 더 많이 굳힌다. 낱말표가 조금 넓어지면 멀쩡한 공고가 조용히 사라지는데,
CSV 행 수만 보고는 알 수 없다.

낱말 경계 테스트에 쓰는 문자열은 **규칙을 만들 때 안 본 실측 사례**다 — 규칙을 만든
데이터로만 재면 일반화를 확인한 것이 아니다.
"""
from __future__ import annotations

import filter as flt
import filter_words
from _common.store import COLUMNS

from .helpers import check, check_equal, read_csv, temp_dir, write_csv


def _row(**fields) -> dict:
    row = {c: "" for c in COLUMNS}
    row.update({"기업명": "회사", "공고명": "백엔드 개발자", "사이트명": "wanted",
                "URL": "https://example.com/1", "최초수집일": "2026-09-01",
                "최종확인일": "2026-09-10"})
    row.update(fields)
    return row


def _text(row: dict) -> str:
    return filter_words.text_of(row)


# ── 일반 ────────────────────────────────────────────────────────────────

def test_NORMAL_same_posting_on_two_sites_becomes_one():
    rows = [_row(기업명="(주)안랩", 사이트명="saramin", URL="s/1", 지원자격="가나다"),
            _row(기업명="㈜안랩", 사이트명="jobkorea", URL="j/1", 지원자격="가")]
    kept, dropped = flt.dedup(rows)
    check_equal(len(kept), 1, "법인 표기만 다른 같은 공고는 한 행이어야 한다")
    check_equal(kept[0]["URL"], "s/1", "본문이 긴 쪽이 남아야 한다")
    check_equal(len(dropped), 1, "뺀 행은 보고에 남길 수 있게 돌려줘야 한다")


def test_NORMAL_banned_word_in_any_of_three_columns():
    for column in ("공고명", "지원자격", "우대사항"):
        kept, dropped = flt.screen([_row(**{column: "SI 프로젝트 경험"})])
        check_equal(len(kept), 0, "%s 에서도 걸려야 한다" % column)
        check_equal(dropped[0][1][0][0], "SI", "걸린 낱말 이름")


def test_NORMAL_report_holds_every_dropped_row():
    home = temp_dir()
    rows = [_row(기업명="가", 공고명="A", 사이트명="wanted", URL="w/1"),
            _row(기업명="가", 공고명="A", 사이트명="saramin", URL="s/1"),
            _row(기업명="나", 공고명="B", URL="w/2", 지원자격="고객사 상주")]
    write_csv(home / "in.csv", rows, COLUMNS)
    flt._run(home / "in.csv", home / "out.csv", home / "report.csv")
    check_equal(len(read_csv(home / "out.csv")), 1, "남는 것은 한 행")
    report = read_csv(home / "report.csv")
    check_equal(len(report), 2, "**뺀 행은 하나도 빠짐없이 보고에 있어야 한다**")
    check_equal({r["판정"] for r in report}, {"제외 · 중복", "제외 · 낱말"}, "판정 두 갈래")


def test_NORMAL_output_keeps_the_thirteen_column_schema():
    home = temp_dir()
    write_csv(home / "in.csv", [_row()], COLUMNS)
    flt._run(home / "in.csv", home / "out.csv", home / "report.csv")
    with (home / "out.csv").open(encoding="utf-8-sig") as handle:
        header = handle.readline().strip().split(",")
    check_equal(header, list(COLUMNS), "산출물도 공통 스키마를 지켜야 한다")


# ── 예외 ────────────────────────────────────────────────────────────────

def test_EXCEPTION_missing_input_stops_with_one():
    home = temp_dir()
    check_equal(flt._run(home / "없다.csv", home / "out.csv", home / "r.csv"), 1,
                "입력이 없으면 1 로 멈춰야 한다 — 0 을 내면 자동화가 성공으로 읽는다")


def test_EXCEPTION_missing_input_writes_nothing():
    # 결함: 없는 입력에도 빈 산출물을 쓰면, 다음 단계가 **어제 결과가 사라진 것**을
    # 정상으로 읽는다.
    home = temp_dir()
    flt._run(home / "없다.csv", home / "out.csv", home / "r.csv")
    check(not (home / "out.csv").exists(), "입력이 없으면 산출물을 만들면 안 된다")


def test_EXCEPTION_empty_input_is_not_a_failure():
    home = temp_dir()
    write_csv(home / "in.csv", [], COLUMNS)
    check_equal(flt._run(home / "in.csv", home / "out.csv", home / "r.csv"), 0,
                "행이 0개인 것과 파일이 없는 것은 다르다")
    check_equal(read_csv(home / "out.csv"), [], "빈 산출물")


def test_EXCEPTION_blank_key_rows_are_never_merged():
    # 결함: 계약상 기업명·공고명은 빌 수 있다. 키가 둘 다 비면 `("", "")` 로 뭉쳐
    # **아무 상관 없는 공고들이 한 행이 된다.**
    rows = [_row(기업명="", 공고명="", 사이트명="wanted", URL="w/1"),
            _row(기업명="", 공고명="", 사이트명="saramin", URL="s/1")]
    kept, dropped = flt.dedup(rows)
    check_equal(len(kept), 2, "판단할 재료가 없으면 안 묶는다")
    check_equal(dropped, [], "뺀 것이 없어야 한다")


def test_EXCEPTION_missing_columns_do_not_crash():
    kept, dropped = flt.dedup([{"URL": "a"}, {"URL": "b"}])
    check_equal(len(kept), 2, "칸이 없는 행도 터지지 않고 남아야 한다")


# ── 경계 ────────────────────────────────────────────────────────────────

def test_BOUNDARY_SI_inside_an_english_word_is_not_SI():
    # 실측 오탐 후보. 이것들이 걸리면 멀쩡한 공고가 사라진다.
    for word in ("SIEMENS", "SIEM", "SIMPAC", "ASIC", "SSIM", "VLSI설계", "WSI",
                 "Vision", "Design", "Business", "assignment", "Ansible"):
        check_equal(filter_words.banned_words("우대 %s 경험" % word), [],
                    "%s 는 SI 가 아니다" % word)


def test_BOUNDARY_SM_inside_an_english_word_is_not_SM():
    for word in ("ISMS", "HSM", "SMS", "Smart", "Prisma", "LangSmith", "smoothing"):
        check_equal(filter_words.banned_words("우대 %s 경험" % word), [],
                    "%s 는 SM 이 아니다" % word)


def test_BOUNDARY_hangul_glued_to_SI_still_counts():
    # 파이썬의 `\b` 는 한글도 낱말 문자로 봐서 이것들을 **놓친다.** 그래서 안 쓴다.
    for text in ("SI프로젝트 수행", "SI업체 경력자 우대", "SM사업부 3명", "ㆍSI & 차세대"):
        hits = [name for name, _ in filter_words.banned_words(text)]
        check(hits, "«%s» 는 걸려야 한다" % text)


def test_BOUNDARY_lowercase_si_is_not_a_hit():
    # 대소문자를 무시하면 vision·design·business 까지 걸려 실측 110행이 사라졌다.
    check_equal(filter_words.banned_words("si 는 소문자다"), [], "소문자는 안 잡는다")


def test_BOUNDARY_banned_words_are_not_looked_for_in_other_columns():
    # 회사 이름과 지역명이 낱말을 품는다 — `에스아이알소프트`·`넥스에스아이`.
    row = _row(기업명="넥스에스아이(주) SI", 근무지="파견로 3", 기술스택="SI")
    check_equal(filter_words.banned_words(_text(row)), [],
                "**지정한 세 칸 밖은 보지 않는다**")


def test_BOUNDARY_military_spelling_actually_used():
    check(filter_words.banned_words("병역 특례 대상자"), "띄어 써도 걸려야 한다")
    check(filter_words.banned_words("전문 연구 요원 편입"), "전문연구요원도 마찬가지")
    check_equal(filter_words.banned_words("병영 생활관 관리"), [],
                "`병영` 은 `병역` 이 아니다 — 붙잡으면 엉뚱한 공고가 사라진다")


def test_BOUNDARY_same_site_twice_is_two_postings():
    rows = [_row(기업명="가", 공고명="각 부문별 채용", 사이트명="saramin", URL="s/1"),
            _row(기업명="가", 공고명="각 부문별 채용", 사이트명="saramin", URL="s/2")]
    kept, _ = flt.dedup(rows)
    check_equal(len(kept), 2, "한 사이트가 두 번 올렸으면 대개 다른 자리다")


def test_BOUNDARY_bracket_prefix_makes_a_different_posting():
    rows = [_row(기업명="가", 공고명="[인턴] Backend Engineer", 사이트명="wanted", URL="w/1"),
            _row(기업명="가", 공고명="Backend Engineer", 사이트명="saramin", URL="s/1")]
    kept, _ = flt.dedup(rows)
    check_equal(len(kept), 2, "**대괄호를 떼면 없는 중복을 만든다**")


def test_BOUNDARY_different_companies_sharing_a_title_both_survive():
    rows = [_row(기업명="비햅틱스", 공고명="SW Engineer", 사이트명="wanted", URL="w/1"),
            _row(기업명="퀄리타스반도체", 공고명="SW Engineer", 사이트명="saramin", URL="s/1")]
    kept, _ = flt.dedup(rows)
    check_equal(len(kept), 2, "제목만 같은 다른 회사 공고를 지우면 안 된다")


def test_BOUNDARY_merge_fills_blanks_but_never_overwrites():
    rows = [_row(기업명="가", 공고명="A", 사이트명="wanted", URL="w/1",
                 지원자격="길게 쓴 본문", 연봉=""),
            _row(기업명="가", 공고명="A", 사이트명="saramin", URL="s/1",
                 지원자격="짧다", 연봉="3400만원")]
    kept, _ = flt.dedup(rows)
    check_equal(kept[0]["지원자격"], "길게 쓴 본문", "있는 값은 안 덮는다")
    check_equal(kept[0]["연봉"], "3400만원", "빈 칸은 채운다")


def test_BOUNDARY_dates_stretch_to_the_widest_span():
    rows = [_row(기업명="가", 공고명="A", 사이트명="wanted", URL="w/1",
                 최초수집일="2026-09-05", 최종확인일="2026-09-08", 지원자격="길다"),
            _row(기업명="가", 공고명="A", 사이트명="saramin", URL="s/1",
                 최초수집일="2026-09-01", 최종확인일="2026-09-10")]
    kept, _ = flt.dedup(rows)
    check_equal(kept[0]["최초수집일"], "2026-09-01", "처음 본 날은 가장 이른 것")
    check_equal(kept[0]["최종확인일"], "2026-09-10", "마지막으로 본 날은 가장 늦은 것")


def test_BOUNDARY_dedup_runs_before_screening():
    # 순서가 뒤집히면 사본마다 따로 판정돼, 본문이 짧은 쪽만 살아남는 일이 생긴다.
    home = temp_dir()
    rows = [_row(기업명="가", 공고명="A", 사이트명="wanted", URL="w/1",
                 지원자격="고객사 상주가 필요합니다"),
            _row(기업명="가", 공고명="A", 사이트명="saramin", URL="s/1", 지원자격="짧다")]
    write_csv(home / "in.csv", rows, COLUMNS)
    flt._run(home / "in.csv", home / "out.csv", home / "report.csv")
    check_equal(read_csv(home / "out.csv"), [],
                "먼저 묶어 **가장 온전한 본문 하나로** 판정해야 한다")


def test_BOUNDARY_report_records_where_the_word_was_found():
    home = temp_dir()
    write_csv(home / "in.csv",
              [_row(지원자격="여러 줄 중에\n고객사 상주 근무가 있습니다\n끝")], COLUMNS)
    flt._run(home / "in.csv", home / "out.csv", home / "report.csv")
    why = read_csv(home / "report.csv")[0]["근거"]
    check("고객사" in why, "**근거에 그 자리의 글이 있어야** 오탐을 되짚을 수 있다: %r" % why)
