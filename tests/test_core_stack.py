"""핵심 기술로 거르는 일.

**이 단계도 행을 지운다.** 그리고 지우는 기준이 `.env` 한 줄이라, 규칙이 조금만
넓거나 좁아도 결과가 크게 흔들린다. 그래서 여기 테스트는 두 방향을 다 굳힌다.

- 너무 넓으면 → `Java` 를 적었는데 `JavaScript` 공고가 남는다 (**틀린 이유로 남음**)
- 너무 좁으면 → `Spring` 을 적었는데 `Spring Boot` 공고가 사라진다 (**멀쩡한 자리가 사라짐**)

그물도 `.env` 도 안 탄다 — 경로를 인자로 넣는다.
"""
from __future__ import annotations

import core_stack as cs
from _common.store import COLUMNS

from .helpers import check, check_equal, read_csv, temp_dir, write_csv


def _row(**fields) -> dict:
    row = {c: "" for c in COLUMNS}
    row.update({"기업명": "회사", "공고명": "백엔드", "사이트명": "wanted",
                "URL": "https://ex/1"})
    row.update(fields)
    return row


def _keeps(wanted, **fields) -> bool:
    return bool(cs.hits(_row(**fields), cs.build(wanted)))


def _env(home, value="Spring, FastAPI"):
    path = home / ".env"
    path.write_text("CORE_TECH_STACKS=%s\n" % value, encoding="utf-8")
    return path


# ── 일반 ────────────────────────────────────────────────────────────────

def test_NORMAL_kept_when_the_stack_column_has_it():
    check(_keeps(["Spring"], 기술스택="Java, Spring, MySQL"), "기술스택 칸")


def test_NORMAL_kept_when_only_the_prose_has_it():
    """**사이트 검색 조건에는 안 잡히는데 본문에는 적혀 있는 공고가 있다.**

    이것이 세 칸을 다 보는 이유다 (2026-09-11 사용자 지적). 기술스택 칸만 보면
    그런 공고가 통째로 사라진다.
    """
    check(_keeps(["Spring"], 기술스택="Java, MySQL", 지원자격="Spring 기반 개발 경험"),
          "지원자격에만 있어도 남아야 한다")
    check(_keeps(["FastAPI"], 기술스택="Python", 우대사항="FastAPI 경험자 우대"),
          "우대사항에만 있어도 남아야 한다")


def test_NORMAL_dropped_when_no_column_has_it():
    check(not _keeps(["Spring", "FastAPI"],
                     기술스택="Node.js, React", 지원자격="TypeScript 경험", 우대사항="AWS"),
          "셋 중 아무 데도 없으면 뺀다")


def test_NORMAL_run_writes_both_files():
    home = temp_dir()
    write_csv(home / "in.csv", [_row(기술스택="Spring", URL="u/1"),
                               _row(기술스택="Node.js", URL="u/2")], COLUMNS)
    code = cs._run(home / "in.csv", home / "out.csv", home / "report.csv", _env(home))
    check_equal(code, 0, "정상 종료")
    check_equal([r["URL"] for r in read_csv(home / "out.csv")], ["u/1"], "남는 한 행")
    report = read_csv(home / "report.csv")
    check_equal(len(report), 1, "**뺀 행은 전량 보고에 남는다**")
    check("핵심 기술 없음" in report[0]["판정"], report[0]["판정"])


# ── 예외 ────────────────────────────────────────────────────────────────

def test_EXCEPTION_missing_input_stops_with_one():
    home = temp_dir()
    check_equal(cs._run(home / "없다.csv", home / "o.csv", home / "r.csv", _env(home)), 1,
                "입력이 없으면 1")


def test_EXCEPTION_empty_setting_stops_instead_of_keeping_everything():
    """`CORE_TECH_STACKS` 가 비면 **멈춘다.**

    결함이 될 뻔한 곳: 빈 목록을 "조건 없음" 으로 읽으면 전부 통과시킨다. 그러면
    사람은 걸렀다고 믿는데 실제로는 아무것도 안 걸린 파일을 받는다 — 조용히 틀린다.
    """
    home = temp_dir()
    write_csv(home / "in.csv", [_row(기술스택="Spring")], COLUMNS)
    check_equal(cs._run(home / "in.csv", home / "out.csv", home / "r.csv",
                        _env(home, "")), 1, "비면 1 로 멈춘다")
    check(not (home / "out.csv").exists(), "산출물을 만들면 안 된다")


def test_EXCEPTION_missing_env_file_stops_with_one():
    home = temp_dir()
    write_csv(home / "in.csv", [_row()], COLUMNS)
    check_equal(cs._run(home / "in.csv", home / "o.csv", home / "r.csv",
                        home / "없는.env"), 1, ".env 가 없으면 1")


def test_EXCEPTION_empty_input_is_not_a_failure():
    home = temp_dir()
    write_csv(home / "in.csv", [], COLUMNS)
    check_equal(cs._run(home / "in.csv", home / "out.csv", home / "r.csv", _env(home)), 0,
                "행이 0개인 것과 파일이 없는 것은 다르다")


def test_EXCEPTION_blank_columns_do_not_crash():
    check(not _keeps(["Spring"]), "세 칸이 다 비어도 터지지 않는다")
    check(not cs.hits({}, cs.build(["Spring"])), "칸이 아예 없는 행도 마찬가지")


# ── 경계 ────────────────────────────────────────────────────────────────

def test_BOUNDARY_spring_finds_spring_boot():
    # `.env` 에 `Spring` 만 적어 뒀는데 공고는 `Spring Boot` 라고 쓴다 (실측 43번).
    for written in ("Spring Boot", "Spring Framework", "Spring Cloud", "Spring Security",
                    "Spring Batch", "Spring boot", "Java/Spring", "(Spring)", "Spring기반"):
        check(_keeps(["Spring"], 기술스택=written), "«%s» 는 Spring 이다" % written)


def test_BOUNDARY_spring_boot_finds_bare_spring():
    """**반대 방향.** `.env` 에 `Spring Boot` 라고 적었어도 `Spring` 만 쓴 공고를 잡는다.

    적어 준 이름의 **첫 낱말로도 함께 찾아서** 된다 (2026-09-11 사용자 지시).
    """
    check(_keeps(["Spring Boot"], 기술스택="Java, Spring, MySQL"), "맨 Spring 도 잡는다")
    check(_keeps(["Spring Boot"], 기술스택="Spring Framework"), "Spring Framework 도")


def test_BOUNDARY_a_longer_word_is_not_the_stack():
    """**부분문자열의 함정.** 이것이 이 단계에서 가장 위험한 자리다.

    틀린 이유로 남은 공고는 사람이 알아볼 방법이 없다 — 뺀 것은 보고 CSV 에 남지만
    잘못 남은 것은 아무 표시가 없다.
    """
    check(not _keeps(["Java"], 기술스택="JavaScript, React"),
          "**Java 는 JavaScript 가 아니다**")
    check(not _keeps(["Spring"], 지원자격="offspring 이라는 낱말"), "offspring 은 Spring 이 아니다")
    check(not _keeps(["Spring"], 우대사항="Springfield 출신"), "Springfield 도 아니다")
    check(not _keeps(["C"], 기술스택="CSS, CUDA, CentOS"), "C 는 CSS 가 아니다")


def test_BOUNDARY_case_does_not_matter():
    for written in ("spring boot", "SPRING", "fastapi", "FastAPI"):
        wanted = ["Spring"] if "spring" in written.lower() else ["FastAPI"]
        check(_keeps(wanted, 기술스택=written), "«%s» 는 대소문자만 다르다" % written)


def test_BOUNDARY_camel_case_run_together_is_not_found():
    """`SpringBoot` 는 **못 잡는다.** 실측 230행에서 1번 나왔다.

    잡으려면 "뒤에 대문자가 오면 낱말이 끝난 것" 으로 봐야 하는데, 그러면 같은 규칙이
    `Java` → `JavaScript` 를 통과시킨다. **틀린 이유로 남는 쪽이 더 나쁘다** —
    빠진 것은 보고 CSV 에 남아 되짚을 수 있다.
    """
    check(not _keeps(["Spring"], 기술스택="SpringBoot"),
          "지금은 못 잡는다 — 위 docstring 의 맞바꿈을 보라")
    check(_keeps(["Spring"], 기술스택="SpringBoot, Spring"),
          "같은 칸에 띄어 쓴 것이 있으면 잡힌다")


def test_BOUNDARY_one_letter_head_is_not_used_as_a_query():
    # `C 언어` 를 적었다고 `C` 로 문서를 다 긁으면 거르는 것이 아니다.
    check_equal(cs.queries("C 언어"), ["C 언어"], "한 글자 첫 낱말은 안 쓴다")
    check_equal(cs.queries("Spring Boot"), ["Spring Boot", "Spring"], "두 글자 이상이면 쓴다")
    check_equal(cs.queries("FastAPI"), ["FastAPI"], "한 낱말이면 그것뿐")
    check_equal(cs.queries("  "), [], "빈 이름은 규칙을 안 만든다")


def test_BOUNDARY_only_the_three_named_columns_are_read():
    # 공고명·근무지에 걸면 회사 이름과 지역명이 이름을 품어 엉뚱한 것이 남는다.
    check_equal(cs.TEXT_COLUMNS, ("기술스택", "지원자격", "우대사항"), "사용자가 지정한 셋")
    check(not _keeps(["Spring"], 공고명="Spring 개발자", 근무지="Springfield"),
          "**지정한 세 칸 밖은 보지 않는다**")


def test_BOUNDARY_report_shows_where_it_was_found():
    found = cs.hits(_row(지원자격="여러 줄 중에\nSpring Boot 기반 개발 경험\n끝"),
                    cs.build(["Spring"]))
    check_equal([name for name, _where in found], ["Spring"], "걸린 이름")
    check("Spring Boot" in found[0][1],
          "**근거에 그 자리의 글이 있어야** 되짚을 수 있다: %r" % found[0][1])


def test_BOUNDARY_each_name_is_counted_once_per_row():
    # `Spring` 과 그 첫 낱말이 같은 행에서 둘 다 맞아도 이름 하나로 센다.
    found = cs.hits(_row(기술스택="Spring, Spring Boot"), cs.build(["Spring Boot"]))
    check_equal(len(found), 1, "한 행에서 같은 이름이 두 번 세어지면 안 된다: %r" % found)
