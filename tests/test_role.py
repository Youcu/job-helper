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
from _common.sections import VALUES_HEADING

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
    assert "같은 부문 블록" in prompt, "네 칸이 한 부문에서 나와야 한다는 규칙이 없다"


def test_BOUNDARY_the_prompt_forbids_mixing_two_parts():
    """**실측으로 겪었다** (2026-09-18, rec_idx=55013189).

    모델이 부문은 `백엔드 엔지니어(Node.js/NestJS)` 를 골라 놓고 지원자격은
    **품질보증 부문 것**(`ISO 9001` · `AS9100` · `품질 보증 경력 3년`)을 가져왔다.
    근거에 "직무명과 불일치한다" 고 스스로 적고도 그대로 냈다.

    읽는 사람은 그것을 내 직군의 조건으로 믿는다. 그래서 **비는 편이 낫다** 를
    프롬프트에 못 박는다.
    """
    prompt = role.build_prompt({"공고명": "가"}, "본문", ["백엔드"])
    assert "같은 부문 블록" in prompt
    assert "빈 문자열로 둬라" in prompt, "못 찾으면 비우라는 지시가 없다"
    assert "지어내지 마라" in prompt, "경력을 지어내지 말라는 지시가 없다"
    assert "부문원문" in prompt, "사람이 확인할 자리가 없다"


def test_BOUNDARY_a_kept_posting_is_also_in_the_report():
    """**덮어쓰는 단계라 오판이 조용하다.** 무엇을 어느 부문 것으로 갈아 끼웠는지
    못 되짚으면 고칠 수가 없다."""
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        source = home / "in.csv"
        _csv(source, [_row(공고명="각 부문별 채용")])
        role._run(source, _bodies(home, {"https://x/1": "본문"}), **_out(home),
                  ask=lambda *a: {"해당": True, "기술스택": "Spring",
                                  "부문": "백엔드 개발자", "부문원문": "기술부문 백엔드 개발자"},
                  have_claude=True, assume_yes=True)
        report = _read(home / "report.csv")
        assert report[0]["판정"] == "남김 · 부문 골라 덮어씀", report
        assert report[0]["부문원문"] == "기술부문 백엔드 개발자"


def test_BOUNDARY_a_part_whose_body_is_missing_is_not_overwritten():
    """**머리말만 있고 내용이 없는 부문이 있다.**

    실측 `rec_idx=55013189` — 사람인이 `기술 부문 22개 포지션` 이라 적어 놓고
    본문에는 일부 패널만 싣는다. `NestJS` 가 본문 17,447자 전체에서 **머리말 한
    곳에만** 나오고, 그 아래 글은 옆 포지션(품질보증)의 것이었다.

    모델은 가진 재료로 답을 냈고 그게 틀렸다 — `품질 보증 경력 3년` 이 백엔드
    지원자격으로 실렸다. 덮어쓰면 **조용히** 틀린다. 안 덮고 리포트에 적는다.
    """
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        source = home / "in.csv"
        _csv(source, [_row(공고명="각 부문별 채용", 지원자격="원래 자격",
                           기술스택="Java, React")])
        role._run(source, _bodies(home, {"https://x/1": "본문"}), **_out(home),
                  ask=lambda *a: {"해당": True, "내용확실": False,
                                  "부문": "백엔드 엔지니어",
                                  "지원자격": "품질 보증 경력 3년",
                                  "기술스택": "Node.js"},
                  have_claude=True, assume_yes=True)
        got = _read(home / "out.csv")[0]
        assert got["지원자격"] == "원래 자격", "확실하지 않은데 덮어썼다"
        assert got["기술스택"] == "Java, React"
        report = _read(home / "report.csv")
        assert report[0]["판정"] == "남김 · 부문 내용 없음", report


def test_BOUNDARY_certainty_missing_is_treated_as_certain():
    """옛 캐시나 답이 그 칸을 안 줄 수 있다. **없다고 못 믿을 이유는 없다** —
    `False` 라고 명시했을 때만 안 덮는다."""
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        source = home / "in.csv"
        _csv(source, [_row(공고명="각 부문별 채용")])
        role._run(source, _bodies(home, {"https://x/1": "본문"}), **_out(home),
                  ask=lambda *a: {"해당": True, "기술스택": "Spring"},
                  have_claude=True, assume_yes=True)
        assert _read(home / "out.csv")[0]["기술스택"] == "Spring"


def test_BOUNDARY_the_prompt_warns_about_headings_without_bodies():
    prompt = role.build_prompt({"공고명": "가"}, "본문", ["백엔드"])
    assert "내용확실" in prompt
    assert "링크 너머" in prompt, "왜 내용이 빌 수 있는지 안 알려 준다"


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


def test_BOUNDARY_web_covers_back_front_and_full_stack():
    """**`웹` 의 범위는 사용자가 정한 것이다** (2026-09-18) — 백엔드 · 프론트엔드 ·
    풀스택을 다 포함한다.

    처음 판정에서 `프론트엔드 (Front-end) 개발` 이 `JOB_ROLES=백엔드,웹` 인데도
    빠졌다. `roles.json` 의 설명이 "웹 전반. 사이트에 따라 백엔드·프론트와 겹친다"
    라 모델이 좁게 읽었기 때문이다. 그 설명은 **프롬프트에 그대로 실리므로**
    말이 흐리면 판정이 흔들린다.
    """
    from _common import roles

    said = roles.describe("웹")
    for word in ("백엔드", "프론트엔드", "풀스택"):
        assert word in said, "`웹` 설명에 %s 가 없습니다: %r" % (word, said)
    assert "웹" in role.build_prompt({"공고명": "가"}, "본문", ["웹"])
    assert "프론트엔드" in role.build_prompt({"공고명": "가"}, "본문", ["웹"]), \
        "프롬프트에 `웹` 의 범위가 안 실렸다"


def test_BOUNDARY_the_model_output_passes_the_corpus():
    """**이 단계는 기술 이름이 들어오는 다섯 번째 길이다.**

    앞의 넷(수집·태그 / 수집·산문 / 그림 판독 / 후보 해석)은 걸러지는데 여기만
    안 걸러졌다 — 모델이 낸 글을 그대로 칸에 썼다. 최종본 48행에 막아야 할 이름이
    26가지·47번 되돌아왔다 (2026-09-18 실측).
    """
    got = role.clean_techs("Java, 풀스택, Spring, DevOps, ORM, 컨테이너, Redis")
    assert got == "Java, Spring, Redis", got


def test_BOUNDARY_a_black_list_is_not_enough():
    """**모르는 말은 무한하다.** 차단 목록만 지나게 했더니 본문에서 잘라 온 말이
    그대로 들어왔다 — 넷 다 공고 본문에 실제로 적힌 말이라 "지어냈다" 도 아니다
    (2026-09-18 실측).

    하나 볼 때마다 목록에 한 줄 더하는 것은 끝이 없다. **아는 이름만 통과시킨다.**
    """
    got = role.clean_techs("Java, AI 기반 개발도구, OpenAI API 등 LLM API, "
                           "데이터베이스 쿼리, OGC 표준, Spring")
    assert got == "Java, Spring", got


def test_BOUNDARY_a_parenthesis_does_not_smuggle_a_blocked_name():
    """`MSA` 는 막혀 있는데 `MSA(마이크로서비스 아키텍처)` 로 빠져나갔다.
    흰 목록에서는 이 구멍이 아예 안 생긴다 — 그 표기가 corpus 에 없기 때문이다."""
    assert role.clean_techs("MSA(마이크로서비스 아키텍처), Spring") == "Spring"


def test_BOUNDARY_an_alias_becomes_the_standard_name():
    """흰 목록은 별칭도 안다 — 버리지 않고 표준 표기로 모은다."""
    assert role.clean_techs("GCP, Spring") == "Google Cloud, Spring"


def test_BOUNDARY_an_unknown_name_is_kept_as_a_candidate():
    """**corpus 에 없다고 기술이 아닌 것은 아니다.** 새 기술은 늘 나온다.
    버리되 사람이 보고 올릴 수 있게 쌓아 둔다 — 수집기들이 이미 그렇게 한다."""
    import tempfile
    from pathlib import Path

    from _common import corpus_candidates

    with tempfile.TemporaryDirectory() as home:
        target = Path(home) / "candidates.json"
        got = corpus_candidates.record(["듣도보도못한DB", "Java"], site="role",
                                       path=target)
        assert "듣도보도못한DB" in got, got
        assert "Java" not in got, "이미 아는 이름은 후보가 아니다"


def test_BOUNDARY_the_same_name_twice_is_kept_once():
    assert role.clean_techs("Java, java, JAVA, Spring") == "Java, Spring"


def test_BOUNDARY_a_long_real_name_survives():
    """자르는 규칙이 진짜 이름을 죽이면 안 된다."""
    assert "Naver Cloud Platform" in role.clean_techs("Naver Cloud Platform, Spring")


def test_BOUNDARY_overwriting_runs_the_tech_column_through_the_filter():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        source = home / "in.csv"
        _csv(source, [_row(공고명="각 부문별 채용")])
        role._run(source, _bodies(home, {"https://x/1": "본문"}), **_out(home),
                  ask=lambda *a: {"해당": True, "기술스택": "Java, 풀스택, Spring"},
                  have_claude=True, assume_yes=True)
        assert _read(home / "out.csv")[0]["기술스택"] == "Java, Spring"


# ── 인재상 표기를 지킨다 ─────────────────────────────────────────────────
#
# 이 단계는 `지원자격` 을 통째로 덮어쓴다. 그림 판독이 붙여 둔 인재상 대목이 거기
# 들어 있어서, 그냥 두면 **바로 앞 단계가 한 일을 여기서 지운다.**
#
# 프롬프트에도 지키라고 적었지만 실측으로 안 지켜졌다 (2026-09-22, 274행 중 10행).
# 둘은 내용까지 잃었고 나머지는 머리말 없이 요건에 섞였다. **그래서 코드가 되붙인다** —
# 인재상은 부문을 안 가리므로 모델의 부문 고르기를 거칠 이유가 없다.

def test_NORMAL_the_values_block_comes_back_after_an_overwrite():
    before = "• 고졸 이상\n• 경력 무관\n%s\n• 도전을 좋아하시는 분" % VALUES_HEADING
    got = role.apply(_row(지원자격=before), {"지원자격": "고졸 이상, 경력 무관"})
    assert VALUES_HEADING in got["지원자격"], "머리말이 돌아와야 한다"
    assert "도전을 좋아하시는 분" in got["지원자격"], "내용도 돌아와야 한다"
    assert got["지원자격"].startswith("고졸 이상, 경력 무관"), \
        "모델이 고른 부문의 자격요건이 앞에 와야 한다"


def test_NORMAL_a_block_the_model_kept_is_not_doubled():
    before = "• 고졸 이상\n%s\n• 도전을 좋아하시는 분" % VALUES_HEADING
    got = role.apply(_row(지원자격=before), {"지원자격": before})
    assert got["지원자격"].count(VALUES_HEADING) == 1, "머리말은 한 번뿐이어야 한다"


def test_EXCEPTION_no_values_before_means_nothing_is_added():
    """**없던 것을 만들지 않는다.** 그림 공고가 아닌 행이 대부분이다."""
    got = role.apply(_row(지원자격="• 고졸 이상"), {"지원자격": "고졸 이상"})
    assert VALUES_HEADING not in got["지원자격"], "머리말이 생기면 안 된다"


def test_BOUNDARY_an_empty_answer_does_not_lose_the_values():
    """모델이 `지원자격` 을 못 채우면 원래 칸이 그대로 남는다 — 그때도 인재상이 산다."""
    before = "• 고졸 이상\n%s\n• 도전을 좋아하시는 분" % VALUES_HEADING
    got = role.apply(_row(지원자격=before), {"지원자격": ""})
    assert got["지원자격"] == before, "아무것도 안 바뀌어야 한다"
