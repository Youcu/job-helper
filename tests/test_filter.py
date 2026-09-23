"""거르기 단계 — 중복 제거와 낱말 제외.

**이 단계는 행을 지운다.** 그래서 여기 테스트는 "잘 지우는가" 보다 **"안 지워야 할 것을
지키는가"** 를 더 많이 굳힌다. 낱말표가 조금 넓어지면 멀쩡한 공고가 조용히 사라지는데,
CSV 행 수만 보고는 알 수 없다.

**말 규칙 자체는 `tests/test_filter_words.py` 에 있다** — 낱말 경계와 중복 키다.
여기는 그 규칙을 **파일에 적용하는 절차**를 본다: 읽고, 묶고, 쓰고, 보고한다.
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


def _env(home, value="PHP, jQuery"):
    """**테스트는 진짜 `.env` 를 안 탄다.** CI 에는 그 파일이 없다."""
    path = home / ".env"
    path.write_text("EXCLUDE_TECH_STACKS=%s\n" % value, encoding="utf-8")
    return path


# ── 일반 ────────────────────────────────────────────────────────────────

def test_NORMAL_same_posting_on_two_sites_becomes_one():
    rows = [_row(기업명="(주)안랩", 사이트명="saramin", URL="s/1", 지원자격="가나다"),
            _row(기업명="㈜안랩", 사이트명="jobkorea", URL="j/1", 지원자격="가")]
    kept, dropped = flt.dedup(rows)
    check_equal(len(kept), 1, "법인 표기만 다른 같은 공고는 한 행이어야 한다")
    check_equal(kept[0]["URL"], "s/1", "본문이 긴 쪽이 남아야 한다")
    check_equal(len(dropped), 1, "뺀 행은 보고에 남길 수 있게 돌려줘야 한다")


def test_NORMAL_a_banned_word_is_no_longer_dropped_here():
    """**낱말로는 이 단계가 안 자른다** (2026-09-22 사용자).

    같은 낱말이 정반대를 뜻한다 — `단순 SI가 **아닌**` · `2,000개 이상의 고객사를
    **유치**` · `보충역 **지원 가능합니다**`. 여기서 자르면 그 오탐이 조용히
    삭제가 된다. 탐지는 `filter_words` 가 하고 **판정은 `nuance.py` 가 모델에게
    묻는다.** 낱말 검사 자체는 `tests/test_nuance.py` 에 있다.
    """
    for column in ("공고명", "지원자격", "우대사항"):
        kept, dropped = flt.screen([_row(**{column: "SI 프로젝트 경험"})])
        check_equal(len(kept), 1, "%s 에 낱말이 있어도 남긴다" % column)
        check_equal(dropped, [], "뺀 것이 없다")


def test_NORMAL_report_holds_every_dropped_row():
    home = temp_dir()
    rows = [_row(기업명="가", 공고명="A", 사이트명="wanted", URL="w/1"),
            _row(기업명="가", 공고명="A", 사이트명="saramin", URL="s/1"),
            _row(기업명="나", 공고명="B", URL="w/2", 경력="경력 5년 이상"),
            _row(기업명="다", 공고명="C", URL="w/3", 기술스택="PHP")]
    write_csv(home / "in.csv", rows, COLUMNS)
    flt._run(home / "in.csv", home / "out.csv", home / "report.csv", _env(home))
    check_equal(len(read_csv(home / "out.csv")), 1, "남는 것은 한 행")
    report = read_csv(home / "report.csv")
    check_equal(len(report), 3, "**뺀 행은 하나도 빠짐없이 보고에 있어야 한다**")
    check_equal({r["판정"] for r in report},
                {"제외 · 중복", "제외 · 경력직", "제외 · 낱말"}, "판정 세 갈래")


def test_NORMAL_output_keeps_the_thirteen_column_schema():
    home = temp_dir()
    write_csv(home / "in.csv", [_row()], COLUMNS)
    flt._run(home / "in.csv", home / "out.csv", home / "report.csv", _env(home))
    with (home / "out.csv").open(encoding="utf-8-sig") as handle:
        header = handle.readline().strip().split(",")
    check_equal(header, list(COLUMNS), "산출물도 공통 스키마를 지켜야 한다")


# ── 예외 ────────────────────────────────────────────────────────────────

def test_EXCEPTION_missing_input_stops_with_one():
    home = temp_dir()
    check_equal(flt._run(home / "없다.csv", home / "out.csv", home / "r.csv", _env(home)), 1,
                "입력이 없으면 1 로 멈춰야 한다 — 0 을 내면 자동화가 성공으로 읽는다")


def test_EXCEPTION_missing_input_writes_nothing():
    # 결함: 없는 입력에도 빈 산출물을 쓰면, 다음 단계가 **어제 결과가 사라진 것**을
    # 정상으로 읽는다.
    home = temp_dir()
    flt._run(home / "없다.csv", home / "out.csv", home / "r.csv", _env(home))
    check(not (home / "out.csv").exists(), "입력이 없으면 산출물을 만들면 안 된다")


def test_EXCEPTION_empty_input_is_not_a_failure():
    home = temp_dir()
    write_csv(home / "in.csv", [], COLUMNS)
    check_equal(flt._run(home / "in.csv", home / "out.csv", home / "r.csv", _env(home)), 0,
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
    """순서가 뒤집히면 사본마다 따로 판정돼, 본문이 짧은 쪽만 살아남는 일이 생긴다."""
    home = temp_dir()
    rows = [_row(기업명="가", 공고명="A", 사이트명="wanted", URL="w/1",
                 기술스택="PHP, Java"),
            _row(기업명="가", 공고명="A", 사이트명="saramin", URL="s/1", 기술스택="")]
    write_csv(home / "in.csv", rows, COLUMNS)
    flt._run(home / "in.csv", home / "out.csv", home / "report.csv", _env(home))
    check_equal(read_csv(home / "out.csv"), [],
                "먼저 묶어 **가장 온전한 본문 하나로** 판정해야 한다")


def test_NORMAL_tech_stack_exclusion_from_env():
    """`.env` 의 `EXCLUDE_TECH_STACKS` 가 **기술스택 칸**에서 뺀다.

    `CORE_TECH_STACKS`(남길 것)의 반대다. 사람이 실제 목록을 보고 고치는 값이라
    코드가 아니라 `.env` 에 둔다 (2026-09-14 사용자).
    """
    rules = filter_words.build_excluded(["PHP", "jQuery"])
    kept, dropped = flt.screen([_row(기술스택="Java, jQuery, Spring"),
                                _row(기술스택="Java, Spring", URL="u/2")], rules)
    check_equal(len(kept), 1, "걸린 것만 빠진다")
    check_equal(kept[0]["URL"], "u/2", "멀쩡한 행은 남는다")
    check_equal(dropped[0][1][0], ("jQuery", "기술스택"),
                "**어느 칸에서 걸렸는지** 보고에 남아야 한다: %r" % (dropped[0][1],))


def test_EXCEPTION_an_empty_setting_excludes_nothing():
    """비면 **아무것도 안 뺀다.** 화면에 그렇게 적는다 — 안 적으면 걸렀다고 믿는다."""
    home = temp_dir()
    write_csv(home / "in.csv", [_row(기술스택="PHP, jQuery")], COLUMNS)
    code = flt._run(home / "in.csv", home / "out.csv", home / "r.csv",
                    _env(home, ""))
    check_equal(code, 0, "빈 설정은 오류가 아니다")
    check_equal(len(read_csv(home / "out.csv")), 1, "안 뺀다")


def test_BOUNDARY_tech_names_are_matched_as_words():
    """`PHP` 는 `PHPStorm` 이 아니고 `jQuery` 는 `Query` 가 아니다.

    부분문자열로 보면 멀쩡한 공고가 사라지는데, **지워진 공고는 흔적이 안 남는다.**
    """
    rules = filter_words.build_excluded(["PHP", "jQuery"])
    for stack in ("PHPStorm, Query", "GraphQL, Queryable", "phpMyAdmin설정"):
        check_equal(filter_words.excluded_techs({"기술스택": stack}, rules), [],
                    "낱말이 아니다: %r" % stack)
    for stack in ("Java, jQuery, Spring", "php, MySQL", "PHP/Laravel"):
        check(filter_words.excluded_techs({"기술스택": stack}, rules),
              "낱말이다: %r" % stack)


def test_BOUNDARY_prose_mentions_of_the_tech_do_not_count():
    """**기술스택 칸만 본다.** 산문에서 보면 "PHP 경험 있으면 좋지만 필수 아님" 도 걸린다."""
    rules = filter_words.build_excluded(["PHP"])
    row = _row(기술스택="Java, Spring", 우대사항="PHP 경험이 있으면 좋지만 필수는 아닙니다")
    check_equal(filter_words.excluded_techs(row, rules), [], "산문은 안 본다")


def test_BOUNDARY_tests_never_read_the_real_env():
    """**진짜 `.env` 를 타면 CI 에서 깨진다.** 그 파일은 저장소에 없다.

    실제로 그랬다 — `_run` 에 `env_path` 를 안 넘겼더니 `.env` 를 숨긴 상태에서
    다섯 건이 실패했다.
    """
    import inspect
    source = inspect.getsource(flt._run)
    check("env_path" in source, "`_run` 이 경로를 인자로 받아야 한다")


# ── 경력직 제외 ──────────────────────────────────────────────────────────
#
# 말 규칙은 `tests/test_career_words.py` 에 있다. 여기는 그것이 **이 단계에 실제로
# 꽂혀 있고 보고에 갈라 적히는가** 를 본다. 규칙을 만들어 놓고 안 부르면 화면에는
# "경력직이라 뺌 0행" 만 찍히는데, 그것과 "정말 없다" 는 구별이 안 된다.

def test_NORMAL_a_career_only_posting_is_dropped_here():
    rows = [_row(경력="경력 3년이상", URL="https://example.com/경력"),
            _row(경력="신입·경력", URL="https://example.com/신입")]
    kept, dropped = flt.screen(rows)
    check_equal([r["URL"] for r in kept], ["https://example.com/신입"], "신입 쪽만 남는다")
    check_equal(len(dropped), 1, "경력직 한 행이 빠진다")


def test_NORMAL_the_report_tells_career_apart_from_banned_words():
    home = temp_dir()
    source = home / "csv" / "merged_role.csv"
    write_csv(source, [
        _row(경력="경력 3년이상", URL="https://example.com/경력"),
        _row(기술스택="PHP", URL="https://example.com/낱말"),
        _row(경력="신입", URL="https://example.com/남김"),
    ], list(COLUMNS))
    out, report = home / "csv" / "out.csv", home / "csv" / "report.csv"
    check_equal(flt._run(source, out, report, env_path=_env(home), assume_yes=True),
                0, "정상 종료")
    verdicts = {r["URL"]: r["판정"] for r in read_csv(report)}
    check_equal(verdicts.get("https://example.com/경력"), "제외 · 경력직",
                "경력직은 그렇게 적힌다")
    check_equal(verdicts.get("https://example.com/낱말"), "제외 · 낱말",
                "낱말은 그대로다")
    check_equal([r["URL"] for r in read_csv(out)], ["https://example.com/남김"],
                "신입 공고만 남는다")


def test_EXCEPTION_a_blank_career_column_is_not_dropped():
    """**빈 경력 칸으로는 아무도 안 뺀다.** 실측 20행이 이 상태다.

    수집이 본문을 못 가져온 것과 회사가 경력직이라고 말한 것은 다른 일이다.
    """
    kept, dropped = flt.screen([_row(경력=""), _row(경력="   ")])
    check_equal(len(kept), 2, "둘 다 남는다")
    check_equal(dropped, [], "뺀 것이 없다")
