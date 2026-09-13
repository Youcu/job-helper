"""경력 거르기 단계 — 모델 판정을 파일에 옮기는 절차.

**이 단계는 행을 지운다.** 그런데 지우는 판단을 모델이 한다. 그래서 여기 테스트는
**"모델이 말 안 한 것을 지우지 않는가"** 를 가장 많이 굳힌다 — 못 물어봤을 때,
답이 깨졌을 때, `claude` 가 아예 없을 때.

모델도 그물도 안 탄다 — 판정 함수를 인자로 넣는다 (`ask=`).
"""
from __future__ import annotations

import json

import career
from _common.store import COLUMNS

from .helpers import check, check_equal, read_csv, temp_dir, write_csv


def _row(**fields) -> dict:
    row = {c: "" for c in COLUMNS}
    row.update({"기업명": "회사", "공고명": "백엔드 개발자", "사이트명": "wanted",
                "URL": "https://ex/1", "경력": "신입 · 경력", "지원자격": "• Java 가능자"})
    row.update(fields)
    return row


def _bad(**fields) -> dict:
    """후보로 걸리는 행 — 신입 가능인데 자격에 연수 요구."""
    return _row(지원자격="• 웹서비스 개발 경력 4년 이상", **fields)


def _stage(home, rows, *, ask=None, book=None):
    source = home / "csv" / "merged_core.csv"
    write_csv(source, rows, COLUMNS)
    cache = home / "cache" / "career_judge.json"
    if book is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    code = career._run(source, home / "out.csv", home / "report.csv", cache,
                       ask=ask, have_claude=True, assume_yes=True)
    got = read_csv(home / "out.csv") if (home / "out.csv").exists() else []
    return code, got, cache


def _says(verdict, why="그래서"):
    return lambda row, line: (verdict, why)


# ── 일반 ────────────────────────────────────────────────────────────────

def test_NORMAL_a_contradicting_posting_is_removed():
    home = temp_dir()
    code, got, _ = _stage(home, [_row(URL="u/ok"), _bad(URL="u/bad")], ask=_says(True))
    check_equal(code, 0, "정상 종료")
    check_equal([r["URL"] for r in got], ["u/ok"], "모순인 것만 빠진다")


def test_NORMAL_a_non_candidate_never_reaches_the_model():
    """후보가 아니면 **묻지 않는다.** 물어보면 돈이고 시간이다."""
    asked = []
    home = temp_dir()
    _stage(home, [_row(), _row(경력="경력", 지원자격="• 경력 5년 이상")],
           ask=lambda row, line: asked.append(row) or (True, ""))
    check_equal(asked, [], "**경력만 받는 공고는 물어볼 일이 없다**")


def test_NORMAL_report_holds_the_line_and_the_reason():
    home = temp_dir()
    _stage(home, [_bad(URL="u/bad")], ask=_says(True, "재직 연수를 요구한다"))
    row = read_csv(home / "report.csv")[0]
    check("경력 4년 이상" in row["걸린줄"], "**어느 줄에서 걸렸는지** 남아야 한다")
    check("재직 연수" in row["근거"], "**모델이 든 근거**가 남아야 한다: %r" % row["근거"])


# ── 예외 ────────────────────────────────────────────────────────────────

def test_EXCEPTION_a_failed_judgment_keeps_the_row():
    """**못 물어본 것을 모순으로 읽으면 안 된다.**

    그림 판독이 "못 읽음" 과 "읽을 게 없음" 을 가르는 것과 같은 이유다. 우리가 못
    물어본 것을 제외로 바꾸면, 우리 사고로 멀쩡한 자리가 사라진다.
    """
    def boom(row, line):
        raise career.JudgeError("시간 초과")

    home = temp_dir()
    code, got, _ = _stage(home, [_bad(URL="u/bad")], ask=boom)
    check_equal(code, 0, "한 건 실패가 단계 실패는 아니다")
    check_equal([r["URL"] for r in got], ["u/bad"], "**남겨야 한다**")


def test_EXCEPTION_missing_input_stops_with_one():
    home = temp_dir()
    check_equal(career._run(home / "없다.csv", home / "out.csv", home / "r.csv",
                            home / "c.json", have_claude=True, assume_yes=True), 1,
                "입력이 없으면 1")
    check(not (home / "out.csv").exists(), "아무것도 안 쓴다")


def test_EXCEPTION_no_claude_stops_instead_of_passing_everything():
    """**거르지 않고 통과시키면 안 된다.**

    통과시키면 사람은 걸렀다고 믿는데 실제로는 안 걸린 파일을 받는다. `core_stack` 이
    `.env` 가 비었을 때 멈추는 것과 같은 판단이다.
    """
    home = temp_dir()
    source = home / "csv" / "merged_core.csv"
    write_csv(source, [_bad()], COLUMNS)
    code = career._run(source, home / "out.csv", home / "r.csv", home / "c.json",
                       have_claude=False, assume_yes=True)
    check_equal(code, 1, "1 로 멈춘다")
    check(not (home / "out.csv").exists(), "**출력을 만들면 안 된다**")


def test_EXCEPTION_broken_model_output_is_a_judge_error():
    for text in ("", "그냥 말", '{"result": 3}', '{"result": "JSON 아님"}'):
        try:
            career.parse_output(text)
        except career.JudgeError:
            continue
        raise AssertionError("깨진 답을 통과시켰다: %r" % text)


def test_EXCEPTION_a_broken_cache_is_ignored_not_fatal():
    home = temp_dir()
    path = home / "cache" / "career_judge.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{깨짐", encoding="utf-8")
    check_equal(career.load_cache(path), {}, "버리고 새로 묻는다")


# ── 경계 ────────────────────────────────────────────────────────────────

def test_BOUNDARY_the_cache_answers_without_asking_again():
    """**같은 공고를 두 번 물으면 답이 달라질 수 있다.** 재현성이 걸려 있다."""
    asked = []
    home = temp_dir()
    code, got, _ = _stage(
        home, [_bad(URL="u/bad")],
        ask=lambda row, line: asked.append(row) or (False, ""),
        book={"u/bad": {"모순": True, "근거": "지난번 판정", "걸린줄": "경력 4년 이상"}})
    check_equal(asked, [], "**캐시에 있으면 안 묻는다**")
    check_equal(got, [], "지난번 판정대로 뺀다")


def test_BOUNDARY_a_new_judgment_is_written_to_the_cache():
    home = temp_dir()
    _code, _got, cache = _stage(home, [_bad(URL="u/bad")], ask=_says(True, "근거"))
    book = json.loads(cache.read_text(encoding="utf-8"))
    check("u/bad" in book, "캐시에 남아야 한다: %r" % book)
    check_equal(book["u/bad"]["모순"], True, "판정")
    check_equal(book["u/bad"]["근거"], "근거", "근거도 함께")


def test_BOUNDARY_ambiguous_stays_because_the_model_says_false():
    """**애매하면 남긴다** (2026-09-13 사용자). 프롬프트가 모델에게 그렇게 시킨다."""
    check("애매하면 false" in career.build_prompt(_bad(), "경력 4년 이상"),
          "프롬프트에 그 지시가 있어야 한다")
    home = temp_dir()
    _code, got, _ = _stage(home, [_bad(URL="u/bad")], ask=_says(False, "애매하다"))
    check_equal([r["URL"] for r in got], ["u/bad"], "남는다")


def test_BOUNDARY_the_prompt_teaches_the_difference():
    """프롬프트가 **"경험"과 "경력 연수"의 차이**를 말해야 한다.

    안 적으면 모델이 `개발 경험이 있으신 분` 을 경력 요구로 읽는다 — 처음에 제가
    그렇게 읽었고 사용자가 바로잡았다.
    """
    prompt = career.build_prompt(_bad(), "경력 4년 이상")
    for word in ("재직 연수", "역량", "신입 또는 경력", "애매하면 false"):
        check(word in prompt, "'%s' 가 프롬프트에 있어야 한다" % word)


def test_BOUNDARY_output_keeps_the_thirteen_column_schema():
    home = temp_dir()
    _code, got, _ = _stage(home, [_row(URL="u/ok")], ask=_says(True))
    check_equal(list(got[0].keys()), list(COLUMNS), "스키마는 그대로다")
