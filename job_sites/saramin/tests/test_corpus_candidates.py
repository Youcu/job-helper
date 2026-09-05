"""`_common/corpus_candidates.py` — 못 푼 이름을 사람이 볼 수 있게 남기는가.

여기서 노리는 결함은 하나로 모인다: **이 파일이 조용히 비면 누락을 영영 모른다.**
버려진 이름은 CSV 에 흔적이 없기 때문이다. 그래서

- 코퍼스에 있는 이름을 후보로 올리면 → 사람이 볼 양만 늘어 진짜 후보가 묻힌다
- 코퍼스에 없는 이름을 안 올리면 → 그 기술은 영영 안 들어온다

두 방향을 다 찌른다. 파일은 임시 디렉터리에 쓴다 — 진짜 후보 파일을 건드리지 않는다.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from _common import corpus_candidates
from tests.helpers import check, check_equal


def _temp_path() -> Path:
    return Path(tempfile.mkdtemp()) / "corpus_candidates.json"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["후보"]


# 후보 시험용 대역 이름. **실재하는 기술 이름을 쓰면 안 된다** —
# 실제로 `VxWorks` 를 대역으로 썼다가, 그것이 corpus 에 채택되자 테스트가 통째로 깨졌다.
# 테스트가 사전 내용에 매달리면 사전을 손볼 때마다 테스트를 손봐야 한다.
UNKNOWN = "그런기술없음ZZ"
UNKNOWN2 = "그런기술도없음ZZ"


# ─────────────────────────────── 일반 ───────────────────────────────

def test_NORMAL_unknown_name_is_recorded_with_evidence():
    path = _temp_path()
    corpus_candidates.record([UNKNOWN], site="saramin",
                             source_url="https://example.test/1", path=path)
    entry = _read(path)[UNKNOWN]
    check_equal(entry["관측"], 1, "관측 횟수")
    check_equal(entry["사이트"], ["saramin"], "어느 사이트에서 나왔나")
    check_equal(entry["예시"], ["https://example.test/1"], "확인할 수 있는 주소")
    check("처음본날" in entry and "마지막본날" in entry, "언제 봤는지 남아야 한다")


def test_NORMAL_known_name_is_not_a_candidate():
    path = _temp_path()
    check_equal(corpus_candidates.record(["Java"], site="saramin", path=path), [],
                "코퍼스에 있는 이름은 후보가 아니다")
    check(not path.exists(), "올릴 게 없으면 파일도 안 만든다")


def test_NORMAL_alias_resolves_and_is_not_a_candidate():
    path = _temp_path()
    check_equal(corpus_candidates.record(["ReactJS"], site="saramin", path=path), [],
                "별칭으로 풀리면 후보가 아니다")


def test_NORMAL_resolved_returns_standard_spelling():
    check_equal(corpus_candidates.resolved(["ReactJS", "SpringBoot", "Pytorch"]),
                ["React", "Spring Boot", "PyTorch"], "표준 표기로 모아야 한다")


def test_NORMAL_repeated_sightings_accumulate():
    path = _temp_path()
    for url in ("https://example.test/1", "https://example.test/2"):
        corpus_candidates.record([UNKNOWN], site="saramin", source_url=url, path=path)
    entry = _read(path)[UNKNOWN]
    check_equal(entry["관측"], 2, "볼 때마다 세야 자주 나오는 것이 위로 온다")
    check_equal(len(entry["예시"]), 2, "예시가 쌓여야 한다")


# ─────────────────────────────── 예외 ───────────────────────────────

def test_EXCEPTION_corrupt_candidate_file_does_not_stop_collection():
    # 후보 파일이 깨졌다고 수집이 멈추면 안 된다. 다시 쌓으면 되는 종류의 자료다.
    path = _temp_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ 깨진 JSON", encoding="utf-8")
    check_equal(corpus_candidates.record([UNKNOWN], site="saramin", path=path),
                [UNKNOWN], "깨진 파일은 버리고 새로 쓴다")
    check(UNKNOWN in _read(path), "새로 쓴 파일은 읽혀야 한다")


def test_EXCEPTION_empty_and_blank_names_are_ignored():
    path = _temp_path()
    check_equal(corpus_candidates.record(["", "   "], site="saramin", path=path), [],
                "빈 이름은 후보가 아니다")


def test_EXCEPTION_resolved_drops_unknown_names():
    check_equal(corpus_candidates.resolved(["Java", UNKNOWN, UNKNOWN2]), ["Java"],
                "코퍼스로 안 풀리는 이름은 결과에 넣지 않는다")


# ─────────────────────────────── 경계 ───────────────────────────────

def test_BOUNDARY_examples_are_capped():
    path = _temp_path()
    for index in range(corpus_candidates.MAX_EXAMPLES + 3):
        corpus_candidates.record([UNKNOWN], site="saramin",
                                 source_url="https://example.test/%d" % index, path=path)
    entry = _read(path)[UNKNOWN]
    check_equal(len(entry["예시"]), corpus_candidates.MAX_EXAMPLES,
                "예시는 판단에 필요한 만큼만 — 더 쌓으면 읽을 양만 는다")
    check_equal(entry["관측"], corpus_candidates.MAX_EXAMPLES + 3,
                "예시는 잘라도 횟수는 다 세야 한다")


def test_BOUNDARY_same_name_from_two_sites_merges():
    path = _temp_path()
    corpus_candidates.record([UNKNOWN], site="saramin", path=path)
    corpus_candidates.record([UNKNOWN], site="wanted", path=path)
    check_equal(_read(path)[UNKNOWN]["사이트"], ["saramin", "wanted"],
                "여러 사이트에서 나오면 그만큼 진짜 기술일 가능성이 높다")


def test_BOUNDARY_duplicate_names_in_one_call_count_once():
    path = _temp_path()
    corpus_candidates.record([UNKNOWN, UNKNOWN], site="saramin", path=path)
    check_equal(_read(path)[UNKNOWN]["관측"], 1, "한 번 부른 것은 한 번이다")


def test_BOUNDARY_similar_names_are_warned_not_applied():
    # `REST`→`Rust` 같은 오인을 자동으로 붙이지 않는다. 눈에 띄게만 한다.
    path = _temp_path()
    corpus_candidates.record(["Pythonn"], site="saramin", path=path)
    entry = _read(path)["Pythonn"]
    check("Python" in entry["비슷한_표준이름"], "닮은 표준 이름을 보여 줘야 한다")
    check_equal(corpus_candidates.resolved(["Pythonn"]), [],
                "닮았다고 자동으로 바꾸면 안 된다")


def test_BOUNDARY_sorted_by_sighting_count():
    path = _temp_path()
    corpus_candidates.record(["Rare"], site="saramin", path=path)
    for _ in range(3):
        corpus_candidates.record(["Common"], site="saramin", path=path)
    check_equal(list(_read(path))[0], "Common", "자주 나온 것이 위에 와야 먼저 읽힌다")


# ────────────────── 기각 목록 · 붙어 나온 토큰 ──────────────────

def test_NORMAL_rejected_name_is_neither_kept_nor_proposed():
    # "툴이지 기술스택이 아니다" 로 사람이 판단한 것. 매 실행 다시 올라오면
    # 진짜 후보가 그 속에 묻힌다.
    for name in ("Claude Code", "Cursor", "Notion", "LLM"):
        check_equal(corpus_candidates.resolved([name]), [], "%s 는 결과에 안 넣는다" % name)
        check(not corpus_candidates.is_unresolved(name),
              "%s 는 후보로도 안 올린다" % name)


def test_NORMAL_rejected_is_case_insensitive():
    check(corpus_candidates.is_rejected("cursor"), "대소문자를 가리지 않는다")
    check(corpus_candidates.is_rejected("  Cursor  "), "앞뒤 공백을 무시한다")


def test_NORMAL_glued_token_is_split_when_every_part_resolves():
    # 모델이 `C/C++` `Java-Spring` 처럼 붙여서 뱉는다. 버리면 진짜 기술 둘을 잃는다.
    check_equal(corpus_candidates.resolved(["C/C++"]), ["C", "C++"], "슬래시로 붙은 것")
    check_equal(corpus_candidates.resolved(["Java-Spring"]), ["Java", "Spring"], "붙임표")


def test_EXCEPTION_whole_name_wins_over_splitting():
    # 결함이 될 뻔한 곳: 무조건 쪼개면 `HTML/CSS` 가 두 개로 갈리고
    # `React-Native` 가 `React` 로 줄어든다. 통째로 먼저 시도해야 한다.
    check_equal(corpus_candidates.resolved(["HTML/CSS"]), ["HTML/CSS"],
                "그 자체가 표준 이름이면 쪼개지 않는다")
    check_equal(corpus_candidates.resolved(["React-Native"]), ["React Native"],
                "별칭으로 풀리면 쪼개지 않는다")


def test_BOUNDARY_split_needs_every_part_to_resolve():
    # `Node` 는 풀리지만 `RED` 는 아니다. 반쪽만 받으면 없는 기술이 생긴다.
    check_equal(corpus_candidates.resolved(["Node-RED"]), [],
                "조각 하나라도 안 풀리면 쪼개지 않는다")
    check_equal(corpus_candidates.resolved(["A/B"]), [], "둘 다 기술이 아니면 버린다")
