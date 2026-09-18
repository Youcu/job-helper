"""여러 직군이 섞인 공고에서 **내 직군 부문만** 남기는 단계.

그물도 모델도 안 탄다 — 판정은 `ask` 로 갈아 끼우고, 경로와 `.env` 는 전부 인자로
받는다. 진짜 `csv/` 도 진짜 `.env` 도 안 건드린다.
"""
from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

import role

COLUMNS = ["기업명", "공고명", "마감일", "지원자격", "우대사항", "경력", "URL",
           "연봉", "기술스택", "근무지", "사이트명", "평점", "최초수집일", "최종확인일"]


def _row(**kwargs) -> dict:
    base = {"기업명": "회사", "공고명": "백엔드 개발자", "URL": "https://x/1",
            "기술스택": "Java, Spring", "사이트명": "saramin", "지원자격": "자격",
            "우대사항": "우대", "경력": "신입", "마감일": "상시채용", "연봉": "",
            "근무지": "서울", "평점": "3.4", "최초수집일": "2026-09-01",
            "최종확인일": "2026-09-18"}
    base.update(kwargs)
    return base


def _csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in COLUMNS})


def _env(home: Path, value: str = "백엔드,웹") -> Path:
    """**테스트는 진짜 `.env` 를 안 탄다.** CI 에는 그 파일이 없다."""
    path = home / ".env"
    path.write_text("JOB_ROLES=%s\n" % value, encoding="utf-8")
    return path


def _bodies(home: Path, texts: dict[str, str]) -> Path:
    path = home / "bodies.jsonl"
    path.write_text("".join(
        json.dumps({"URL": url, "본문": text}, ensure_ascii=False) + "\n"
        for url, text in texts.items()), encoding="utf-8")
    return path


def _out(home: Path) -> dict:
    return {"output": home / "out.csv", "report": home / "report.csv",
            "cache_path": home / "cache.json", "env_path": _env(home)}


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


# ── 일반 ────────────────────────────────────────────────────────────────

def test_NORMAL_an_ordinary_posting_is_never_asked():
    """후보가 아닌 공고는 모델을 안 탄다. **92% 가 여기로 빠진다.**"""
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        source = home / "in.csv"
        _csv(source, [_row()])
        asked = []
        code = role._run(source, _bodies(home, {}), **_out(home),
                         ask=lambda *a: asked.append(a) or {}, have_claude=True,
                         assume_yes=True)
        assert code == 0
        assert asked == [], "후보가 아닌데 물어봤다"
        assert len(_read(home / "out.csv")) == 1


def test_NORMAL_the_wanted_part_overwrites_the_four_columns():
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        source = home / "in.csv"
        _csv(source, [_row(공고명="각 부문별 채용", 기술스택="React, Verilog, Spring",
                           지원자격="PM 요건", 우대사항="PM 우대", 경력="경력 3년")])
        answer = {"해당": True, "부문": "백엔드 개발자",
                  "기술스택": "Spring, JPA", "지원자격": "백엔드 요건",
                  "우대사항": "백엔드 우대", "경력": "신입", "근거": "골랐다"}
        role._run(source, _bodies(home, {"https://x/1": "본문"}), **_out(home),
                  ask=lambda *a: answer, have_claude=True, assume_yes=True)
        got = _read(home / "out.csv")[0]
        assert got["기술스택"] == "Spring, JPA"
        assert got["지원자격"] == "백엔드 요건"
        assert got["경력"] == "신입"
        assert got["기업명"] == "회사", "공고 전체의 칸은 안 건드린다"


def test_NORMAL_a_posting_without_my_role_is_dropped_with_a_reason():
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        source = home / "in.csv"
        _csv(source, [_row(공고명="각 부문별 채용")])
        role._run(source, _bodies(home, {"https://x/1": "본문"}), **_out(home),
                  ask=lambda *a: {"해당": False, "부문": "", "근거": "전부 영업 부문이다"},
                  have_claude=True, assume_yes=True)
        assert _read(home / "out.csv") == []
        report = _read(home / "report.csv")
        assert report[0]["판정"] == "제외 · 내 직군 없음"
        assert report[0]["근거"] == "전부 영업 부문이다"
        assert "제목" in report[0]["걸린신호"], report[0]


# ── 경계 ────────────────────────────────────────────────────────────────

def test_BOUNDARY_no_body_is_not_silently_judged_by_the_columns():
    """**본문이 없으면 칸으로 대신하지 않는다.**

    칸은 절로 자를 때 **첫 부문 것만** 남은 것이라, 그것으로 판정하면 다른 부문의
    요건을 내 직군 것으로 읽는다. 걸렀다고 믿는데 안 걸린 결과가 나오고 아무 데도
    안 드러난다. 그래서 남기되 **리포트에 적는다.**
    """
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        source = home / "in.csv"
        _csv(source, [_row(공고명="각 부문별 채용")])
        asked = []
        role._run(source, _bodies(home, {}), **_out(home),
                  ask=lambda *a: asked.append(a) or {"해당": False},
                  have_claude=True, assume_yes=True)
        assert asked == [], "본문이 없는데 물어봤다"
        assert len(_read(home / "out.csv")) == 1, "남겨야 한다"
        report = _read(home / "report.csv")
        assert report and report[0]["판정"] == "남김 · 본문 없음", report


def test_BOUNDARY_a_failed_judgement_keeps_the_posting():
    """**못 물어본 것을 "내 직군 아님" 으로 읽으면 안 된다.**"""
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        source = home / "in.csv"
        _csv(source, [_row(공고명="각 부문별 채용")])

        def broken(*args):
            raise role.JudgeError("모델이 죽었다")

        role._run(source, _bodies(home, {"https://x/1": "본문"}), **_out(home),
                  ask=broken, have_claude=True, assume_yes=True)
        assert len(_read(home / "out.csv")) == 1, "판정 못 했으면 남긴다"
        assert _read(home / "report.csv")[0]["판정"] == "남김 · 판정 실패"


def test_BOUNDARY_an_empty_field_does_not_erase_what_was_there():
    """모델이 못 채운 칸은 **모르는 것**이지 *없는 것*이 아니다."""
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        source = home / "in.csv"
        _csv(source, [_row(공고명="각 부문별 채용", 우대사항="원래 우대")])
        role._run(source, _bodies(home, {"https://x/1": "본문"}), **_out(home),
                  ask=lambda *a: {"해당": True, "기술스택": "Spring", "우대사항": ""},
                  have_claude=True, assume_yes=True)
        got = _read(home / "out.csv")[0]
        assert got["우대사항"] == "원래 우대", got
        assert got["기술스택"] == "Spring"


def test_BOUNDARY_the_cache_answers_without_asking_again():
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        source = home / "in.csv"
        _csv(source, [_row(공고명="각 부문별 채용")])
        paths = _out(home)
        asked = []

        def once(*args):
            asked.append(args)
            return {"해당": True, "기술스택": "Spring"}

        body = _bodies(home, {"https://x/1": "본문"})
        role._run(source, body, **paths, ask=once, have_claude=True, assume_yes=True)
        role._run(source, body, **paths, ask=once, have_claude=True, assume_yes=True)
        assert len(asked) == 1, "두 번 물었다"


def test_BOUNDARY_an_old_rules_version_is_asked_again():
    """**규칙을 고쳐도 캐시가 옛 답을 내면 고침이 영영 안 먹는다.** career.py 에서 겪었다."""
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        source = home / "in.csv"
        _csv(source, [_row(공고명="각 부문별 채용")])
        paths = _out(home)
        paths["cache_path"].write_text(json.dumps(
            {"https://x/1": {"답": {"해당": False}, "규칙판": role.RULES_VERSION - 1}},
            ensure_ascii=False), encoding="utf-8")
        asked = []
        role._run(source, _bodies(home, {"https://x/1": "본문"}), **paths,
                  ask=lambda *a: asked.append(a) or {"해당": True},
                  have_claude=True, assume_yes=True)
        assert len(asked) == 1, "옛 규칙판인데 안 물었다"


def test_BOUNDARY_a_cache_entry_without_a_version_is_asked_again():
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        source = home / "in.csv"
        _csv(source, [_row(공고명="각 부문별 채용")])
        paths = _out(home)
        paths["cache_path"].write_text(
            json.dumps({"https://x/1": {"답": {"해당": False}}}, ensure_ascii=False),
            encoding="utf-8")
        asked = []
        role._run(source, _bodies(home, {"https://x/1": "본문"}), **paths,
                  ask=lambda *a: asked.append(a) or {"해당": True},
                  have_claude=True, assume_yes=True)
        assert len(asked) == 1


def test_BOUNDARY_the_prompt_carries_what_my_roles_mean():
    """**이름만 주면 모델이 `웹` 을 프론트로도 읽는다.** 설명이 그 자리를 메운다."""
    prompt = role.build_prompt({"공고명": "가"}, "본문", ["백엔드"])
    assert "백엔드" in prompt
    assert "서버" in prompt, "roles.json 의 설명이 안 실렸다"
    assert "다른 부문의 내용을 섞지 마라" in prompt


def test_BOUNDARY_the_role_is_not_hardcoded():
    """`.env` 를 바꾸면 코드가 따라와야 한다 — 박아 두면 안 따라온다 (사용자 지적)."""
    source = Path(role.__file__).read_text(encoding="utf-8")
    body = source.split('"""', 2)[-1]          # 머리말 설명은 뺀다
    assert '"백엔드"' not in body and "'백엔드'" not in body, \
        "role.py 코드에 직군 이름이 박혀 있습니다"


# ── 예외 ────────────────────────────────────────────────────────────────

def test_EXCEPTION_no_input_says_so_and_stops():
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        assert role._run(home / "없다.csv", home / "b.jsonl", **_out(home),
                         have_claude=True, assume_yes=True) == 1


def test_EXCEPTION_no_claude_stops_instead_of_passing_everything():
    """**통과시키면 걸렀다고 믿는데 안 걸린 파일을 받는다.**"""
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        source = home / "in.csv"
        _csv(source, [_row()])
        paths = _out(home)
        assert role._run(source, _bodies(home, {}), **paths,
                         have_claude=False, assume_yes=True) == 1
        assert not paths["output"].exists(), "멈췄는데 파일을 썼다"


def test_EXCEPTION_an_empty_job_roles_stops():
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        source = home / "in.csv"
        _csv(source, [_row()])
        paths = _out(home)
        paths["env_path"] = _env(home, value="")
        assert role._run(source, _bodies(home, {}), **paths,
                         have_claude=True, assume_yes=True) == 1


def test_EXCEPTION_an_unknown_role_name_stops():
    """조용히 빼면 조건이 통째로 사라진다 — `_common/roles.py` 의 규칙 그대로다."""
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        source = home / "in.csv"
        _csv(source, [_row()])
        paths = _out(home)
        paths["env_path"] = _env(home, value="없는직군")
        assert role._run(source, _bodies(home, {}), **paths,
                         have_claude=True, assume_yes=True) == 1
