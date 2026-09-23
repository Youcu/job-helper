"""낱말 뉘앙스 판정 — **같은 낱말이 정반대를 뜻한다.**

거르기가 낱말만 보고 자르던 것을 여기로 옮겼다. 실측(2026-09-22)으로 오탐이
실제로 있었다 — `단순 SI가 **아닌** 자사 플랫폼` · `2,000개 이상의 **고객사**를
유치` · `※ 산업기능요원 **보충역** 지원 가능합니다`.

**이 단계가 뚫리는 두 방향이 값이 다르다.**

    너무 넓게 자른다   멀쩡한 공고가 사라진다. 보고 CSV 에 남지만 사람이 열어 봐야 한다
    너무 좁게 자른다   SI 공고가 목록에 남는다. 사람이 보고 넘기면 그만이다

그래서 여기 테스트는 **"안 지워야 할 것을 지키는가"** 쪽이 더 많다. 특히 못 물어본
것을 결격으로 읽지 않는가 — 그게 뚫리면 모델이 잠깐 막힌 날 목록이 통째로 준다.
"""
from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

import nuance
from _common.store import COLUMNS

from .helpers import check, check_equal


def _row(**fields) -> dict:
    row = {c: "" for c in COLUMNS}
    row.update({"기업명": "회사", "공고명": "백엔드 개발자", "사이트명": "saramin",
                "URL": "https://x/1", "최초수집일": "2026-09-01",
                "최종확인일": "2026-09-22"})
    row.update(fields)
    return row


def _csv(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in COLUMNS})
    return path


def _bodies(path: Path, texts: dict[str, str]) -> Path:
    path.write_text("".join(
        json.dumps({"URL": url, "본문": text}, ensure_ascii=False) + "\n"
        for url, text in texts.items()), encoding="utf-8")
    return path


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _run(home: Path, rows: list[dict], texts: dict, ask) -> tuple[list, list]:
    code = nuance._run(_csv(home / "in.csv", rows),
                       _bodies(home / "bodies.jsonl", texts),
                       home / "out.csv", home / "report.csv", home / "cache.json",
                       ask=ask, have_claude=True, assume_yes=True)
    assert code == 0, code
    return _read(home / "out.csv"), _read(home / "report.csv")


# ── 일반 ────────────────────────────────────────────────────────────────

def test_NORMAL_a_word_in_a_column_is_a_candidate():
    hits = nuance.hits_of(_row(지원자격="SI 프로젝트 경험"))
    check_equal([(n, w) for n, w, _ in hits], [("SI", "공고 칸")], "%r" % hits)


def test_NORMAL_a_word_only_in_the_body_is_also_a_candidate():
    """**거르기는 본문을 안 본다.** 그래서 회사소개의 SI 가 안 걸렸다.

    실측 — 최종 46행 중 11행이 본문에만 금칙어를 가졌고, 그중 제타럭스시스템은
    `GIS, Digital Twin, XR 기반의 SI 및 통합 솔루션 서비스를 제공하는 IT기업` 이라고
    스스로 적는다.
    """
    hits = nuance.hits_of(_row(), "GIS 기반의 SI 및 통합 솔루션을 제공하는 IT기업입니다")
    check_equal([(n, w) for n, w, _ in hits], [("SI", "본문")], "%r" % hits)


def test_NORMAL_the_model_decides_not_the_word():
    """**낱말이 같아도 판정이 갈린다.**

    회사를 다르게 둔다 — 같은 회사면 회사 판단이 퍼져서 둘 다 빠진다(그건 의도한
    동작이고 따로 시험한다).
    """
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        out, report = _run(
            home,
            [_row(URL="https://x/1", 기업명="가회사", 지원자격="SI 프로젝트 경험"),
             _row(URL="https://x/2", 기업명="나회사", 지원자격="SI 프로젝트 경험")],
            {},
            ask=lambda row, hits, body: (row["URL"].endswith("1"), False, False, "판정"))
        check_equal([r["URL"] for r in out], ["https://x/2"], "모델이 가른다")
        check_equal({r["URL"]: r["판정"] for r in report},
                    {"https://x/1": "제외 · 피할 자리",
                     "https://x/2": "남김 · 결격 아님"}, "%r" % report)


# ── 예외 ────────────────────────────────────────────────────────────────

def test_EXCEPTION_a_failed_judgement_keeps_the_row():
    """**못 물어본 것을 결격으로 읽으면 안 된다.**

    여기가 뚫리면 모델이 잠깐 막힌 날 목록이 통째로 준다. `career.py` 와 같은 규칙이다.
    """
    def fails(row, hits, body):
        raise nuance.JudgeError("막혔다")

    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        out, report = _run(home, [_row(지원자격="SI 프로젝트")], {}, ask=fails)
        check_equal(len(out), 1, "행이 살아 있어야 한다")
        check_equal(report[0]["판정"], "남김 · 판정 실패", "%r" % report[0])


def test_EXCEPTION_a_posting_without_any_word_is_never_asked():
    asked = []
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        out, report = _run(home, [_row(지원자격="Java 경험")], {},
                           ask=lambda *a: asked.append(a) or (True, False, False, ""))
        check_equal(asked, [], "후보가 아닌데 물어봤다")
        check_equal(len(out), 1, "그대로 남는다")
        check_equal(report, [], "적을 것도 없다")


def test_EXCEPTION_a_missing_body_does_not_crash():
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        out, _ = _run(home, [_row(지원자격="SI 프로젝트")], {},
                      ask=lambda row, hits, body: (False, False, False, "본문 없이도 판정했다"))
        check_equal(len(out), 1, "남는다")


# ── 경계 ────────────────────────────────────────────────────────────────

def test_BOUNDARY_a_kept_posting_is_still_written_to_the_report():
    """**남긴 것도 전량 적는다.**

    낱말이 걸렸는데 남겼다는 것은 사람이 되짚어야 할 판단이다. 안 적으면 왜
    남았는지 알 수 없고, 판정이 느슨해져도 드러나지 않는다.
    """
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        out, report = _run(home, [_row(지원자격="SI 프로젝트")], {},
                           ask=lambda row, hits, body: (False, False, False, "부정하는 문장이다"))
        check_equal(len(out), 1, "남는다")
        check_equal(len(report), 1, "남긴 것도 적힌다")
        check("부정하는" in report[0]["근거"], "근거가 실린다: %r" % report[0])


def test_BOUNDARY_the_prompt_carries_the_measured_false_positives():
    """**오탐 사례를 프롬프트에 못 박는다.**

    안 적으면 모델이 낱말이 있다는 이유만으로 결격이라 답한다 — 처음에 제가
    그렇게 읽었고 사용자가 바로잡았다.
    """
    prompt = nuance.build_prompt(_row(지원자격="SI"), [("SI", "공고 칸", "SI")], "")
    for phrase in ("아닌", "유치", "연동", "혜택 안내", "애매하면 false"):
        check(phrase in prompt, "프롬프트에 %r 가 있어야 한다" % phrase)


def test_BOUNDARY_the_prompt_says_a_benefit_notice_is_not_disqualifying():
    """엘리스 판정 — **일반 지원자도 지원할 수 있으면 피할 자리가 아니다**
    (2026-09-22 사용자)."""
    prompt = nuance.build_prompt(_row(), [("보충역", "본문", "지원 가능")], "")
    check("전용 공고만" in prompt, "전용만 피한다고 적혀 있어야 한다")
    check("일반 지원자도 그대로 지원할 수 있으면" in prompt, "%r" % prompt[-900:])


def test_BOUNDARY_a_column_hit_wins_over_a_body_hit_for_the_same_word():
    """같은 낱말이 칸과 본문 둘 다 있으면 **칸 쪽만 싣는다.**

    같은 낱말을 두 번 실으면 프롬프트가 길어지기만 하고, 무게가 큰 쪽은 칸이다 —
    자격요건의 `SI` 는 그 자리의 조건이고 회사소개의 `SI` 는 회사의 업이다.
    """
    hits = nuance.hits_of(_row(지원자격="SI 프로젝트"), "우리는 SI 기업입니다")
    check_equal([(n, w) for n, w, _ in hits], [("SI", "공고 칸")], "%r" % hits)


def test_BOUNDARY_the_cache_is_keyed_by_rules_version():
    """**판정 규칙을 고치면 옛 판정을 버린다.**

    안 버리면 프롬프트를 고쳐도 이미 판정된 공고가 캐시에서 그대로 나온다 —
    `career.py` 에서 실제로 겪었다.
    """
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        rows = [_row(지원자격="SI 프로젝트")]
        _run(home, rows, {}, ask=lambda *a: (True, False, False, "첫 판정"))
        book = json.loads((home / "cache.json").read_text(encoding="utf-8"))
        check_equal(book["https://x/1"]["규칙판"], nuance.RULES_VERSION, "%r" % book)

        book["https://x/1"]["규칙판"] = nuance.RULES_VERSION - 1
        (home / "cache.json").write_text(json.dumps(book, ensure_ascii=False),
                                         encoding="utf-8")
        again = []
        _run(home, rows, {}, ask=lambda *a: again.append(a) or (False, False, False, "다시 판정"))
        check_equal(len(again), 1, "옛 규칙판이면 다시 묻는다")


# ── 회사 판단은 그 회사의 모든 공고에 같다 ───────────────────────────────
#
# 회사가 SI 업체인가는 **공고마다 달라질 수 없다.** 그런데 사이트마다 본문에 실린
# 글이 달라 한쪽은 회사소개를 갖고 한쪽은 안 갖는다. 실측(2026-09-22):
#
#     (주)클릭비 프론트엔드 개발자 채용 (자사/SI)  → 결격 아님
#     (주)클릭비 프론트엔드 개발자 채용            → 피할 자리   ← 거꾸로다
#
# 풀링포레스트·마드라스체크도 같은 모양으로 갈렸다.

def test_NORMAL_a_company_verdict_spreads_to_its_other_postings():
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        rows = [_row(URL="https://x/1", 공고명="프론트엔드 (자사/SI)", 지원자격="SI 프로젝트"),
                _row(URL="https://x/2", 공고명="프론트엔드", 지원자격="SI 프로젝트")]
        out, report = _run(home, rows, {},
                           ask=lambda row, hits, body: (row["URL"].endswith("1"),
                                                        False, False, "판정"))
        check_equal(out, [], "둘 다 빠진다 — 회사가 SI 라면 그 회사 공고는 다 그렇다")
        spread = [r for r in report if "같은 회사" in r["빠진이유"]]
        check_equal(len(spread), 1, "물려받았다고 적는다: %r" % [r["빠진이유"] for r in report])


def test_NORMAL_a_legal_form_does_not_split_a_company():
    """`(주)클릭비` 와 `㈜클릭비` 는 같은 회사다 — 중복 묶기와 같은 자를 쓴다."""
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        rows = [_row(URL="https://x/1", 기업명="(주)클릭비", 지원자격="SI 프로젝트"),
                _row(URL="https://x/2", 기업명="㈜클릭비", 지원자격="SI 프로젝트")]
        out, _ = _run(home, rows, {},
                      ask=lambda row, hits, body: (row["URL"].endswith("1"), False, False, "판정"))
        check_equal(out, [], "법인 표기가 달라도 같은 회사다")


def test_EXCEPTION_a_posting_level_verdict_does_not_spread():
    """**자리 판단(상주·파견)은 안 퍼뜨린다.** 그건 공고마다 다르다.

    버즈빌처럼 한 자리만 제휴사 오피스로 출근하는 경우가 있다. 그것을 회사 전체에
    적용하면 멀쩡한 자리가 같이 사라진다.
    """
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        rows = [_row(URL="https://x/1", 지원자격="SI 프로젝트"),
                _row(URL="https://x/2", 지원자격="SI 프로젝트")]
        out, _ = _run(home, rows, {},
                      ask=lambda row, hits, body: (False, row["URL"].endswith("1"), False, "상주"))
        check_equal([r["URL"] for r in out], ["https://x/2"], "한 자리만 빠진다")


def test_BOUNDARY_the_report_tells_the_reason_apart_from_the_word():
    """**빠진 이유가 걸린 낱말과 다를 수 있다.**

    실측 — 버즈빌이 `전문연구요원` 으로 걸렸는데 빠진 이유는 `제휴사 오피스로 출근`
    이었다. 두 칸을 갈라 적어야 사람이 그 차이를 본다.
    """
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        out, report = _run(home, [_row(지원자격="전문연구요원 편입 가능")], {},
                           ask=lambda row, hits, body: (False, True, False, "제휴사 오피스로 출근"))
        check_equal(out, [], "빠진다")
        check_equal(report[0]["걸린낱말"], "전문연구요원", "%r" % report[0])
        check_equal(report[0]["빠진이유"], "상주·파견", "%r" % report[0])


def test_BOUNDARY_a_broken_answer_is_asked_once_more():
    """**한 번만 다시 묻는다.** 실측 154건 중 1건이 JSON 깨짐이었다(넥스비원).

    못 물어본 것은 남기므로 공고가 사라지지는 않지만, 그러면 **SI 업체가 목록에
    남는다** — 넥스비원이 딱 그 모양이었다(ERP 운영·유지보수).
    """
    calls = []

    def flaky(command, timeout):
        calls.append(1)
        if len(calls) == 1:
            return "이건 JSON 이 아니다"
        return json.dumps({"result": json.dumps(
            {"회사가SI": True, "자리가상주": False, "병역특례전용": False, "근거": "ok"}, ensure_ascii=False)})

    got = nuance.judge(_row(지원자격="SI"), [("SI", "공고 칸", "SI")], "", runner=flaky)
    check_equal(got, (True, False, False, "ok"), "두 번째에 통과한다")
    check_equal(len(calls), 2, "두 번만 묻는다")


# ── 병역특례 전용은 따로 묻는다 ──────────────────────────────────────────
#
# **물음을 갈랐다가 이 깃발을 통째로 빠뜨렸던 적이 있다** (2026-09-22, RULES_VERSION 2).
# `회사가SI`·`자리가상주` 둘만 물으니 모델이 병역을 답할 이유가 없어졌고, 병역 낱말로
# 걸린 41건 중 **병역 때문에 빠진 것이 0건**이 됐다. 남긴 39건 중 27건은 근거에
# 병역 얘기조차 없었다 — 제목에 `[병역특례 현역/보충역]` 이 박힌 공고까지 살아남았다.
#
# 그래서 **셋을 다 묻는지**와 **셋 다 뺄 수 있는지**를 여기서 굳힌다.

def test_NORMAL_a_military_only_posting_is_cut():
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        out, report = _run(home, [_row(지원자격="전문연구요원 자격 보유자만 지원 가능")], {},
                           ask=lambda row, hits, body: (False, False, True, "전용 공고"))
        check_equal(out, [], "빠진다")
        check_equal(report[0]["빠진이유"], "병역특례 전용", "%r" % report[0])


def test_NORMAL_the_prompt_asks_all_three():
    """**셋을 다 묻는지 프롬프트에서 확인한다.** 하나가 빠지면 조용히 안 걸러진다."""
    prompt = nuance.build_prompt(_row(), [("전문연구요원", "공고 칸", "x")], "")
    for flag in ("회사가SI", "자리가상주", "병역특례전용"):
        check(flag in prompt, "프롬프트가 %s 를 묻지 않는다" % flag)
    check("셋 중 하나라도" in prompt, "셋 다 뺌 사유라고 적혀 있어야 한다")


def test_EXCEPTION_a_military_verdict_does_not_spread_to_the_company():
    """**병역특례 전용은 회사 단위가 아니다.**

    같은 회사가 전용 공고와 일반 공고를 함께 내는 일이 흔하다 — 실측으로
    파이오링크·메디인테크가 그랬다. 회사에 퍼뜨리면 멀쩡한 자리가 같이 사라진다.
    """
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        rows = [_row(URL="https://x/1", 지원자격="전문연구요원 전용"),
                _row(URL="https://x/2", 지원자격="전문연구요원 가능")]
        out, _ = _run(home, rows, {},
                      ask=lambda row, hits, body: (False, False,
                                                   row["URL"].endswith("1"), "판정"))
        check_equal([r["URL"] for r in out], ["https://x/2"], "한 자리만 빠진다")


def test_BOUNDARY_the_prompt_says_a_product_company_is_not_si():
    """플로우 판정 — **자사 제품을 만들어 파는 회사는 SI 업체가 아니다**
    (2026-09-22 사용자). 그 제품을 고객 환경에 설치하는 자리라도 그렇다.

    가르는 선은 **여러 고객의 서로 다른 시스템인가, 하나의 자사 제품인가** 다.
    """
    prompt = nuance.build_prompt(_row(), [("고객사", "본문", "고객사 구축")], "")
    check("자사 제품을 만들어 파는 회사는 SI 업체가 아니다" in prompt, "%r" % prompt[-1400:])
    check("서로 다른" in prompt, "가르는 선이 적혀 있어야 한다")
