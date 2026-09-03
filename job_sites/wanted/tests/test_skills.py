"""기술 이름 찾기와 표기 통일."""
from __future__ import annotations

import tempfile
from pathlib import Path

from _common import dictionaries
from _common.normalize import canonical, kind_of
from lib.skills import clear_caches, find_skills_in_text, normalize_tag
from lib.record import extract_skills
from tests.helpers import assert_raises


def test_BOUNDARY_normalization_is_never_fuzzy():
    """편집거리로 붙이면 REST→Rust, Apache Kafka→Apache Spark 가 된다 (실측).

    사전에 없는 이름은 억지로 가까운 것에 붙이지 않고 그대로 둔다.
    """
    for name, expected in [
        ("REST", "REST API"), ("Rust", "Rust"),
        ("Apache Kafka", "Kafka"), ("Apache Spark", "Spark"),
        ("MSSQL", "SQL Server"), ("MySQL", "MySQL"),
        ("OpenCL", "OpenCL"), ("OpenCV", "OpenCV"),
        ("Quarkus", "Quarkus"),          # 사전에 없다 — 그대로 둔다
    ]:
        assert canonical(name) == expected, f"{name} -> {canonical(name)} (기대 {expected})"
    assert kind_of("Quarkus") is None


def test_BOUNDARY_skill_longest_match_wins():
    """`Spring Boot` 가 `Spring` 에 먹히면 안 된다."""
    found = find_skills_in_text("Spring Boot 와 Spring Framework")
    assert "Spring Boot" in found
    assert find_skills_in_text("ASP.NET Core 로 개발") == [".NET"] or "ASP.NET Core" in find_skills_in_text("ASP.NET Core 로 개발")


def test_BOUNDARY_skill_name_not_starting_with_alnum():
    """결함: `.NET` 은 산문에서 영영 못 찾았다 (첫 글자가 영숫자가 아니라서)."""
    assert ".NET" in find_skills_in_text(".NET 으로 개발")


def test_BOUNDARY_skill_not_matched_inside_a_longer_token():
    """`Java` 가 `JavaScript` 안에서 잡히면 안 된다."""
    found = find_skills_in_text("JavaScript 만 씁니다")
    assert "JavaScript" in found and "Java" not in found


def test_BOUNDARY_skill_short_names():
    """1~2글자는 대개 오탐(IR·SD·PC)이지만 C·R·Go 는 진짜 언어다."""
    found = find_skills_in_text("C 와 Go 로 개발. R 로 분석. IR 담당 아님. SD카드 아님")
    assert "C" in found and "Go" in found and "R" in found
    assert "IR" not in found and "SD" not in found


def test_BOUNDARY_skill_version_suffix():
    """`Python3` 은 Python 이다. 다만 짧은 이름에 숫자가 붙으면 다른 것일 수 있다."""
    assert "Python" in find_skills_in_text("Python3 경험")
    assert "Vue.js" in find_skills_in_text("Vue3 로 프론트")
    assert "C++" in find_skills_in_text("C++11 표준")
    assert find_skills_in_text("C9 클라우드 IDE") == []       # C 로 붙지 않는다


def test_BOUNDARY_skills_merge_keeps_tag_first_and_dedupes():
    job = {
        "id": 1,
        "skill_tags": [{"tag_type_id": 1533, "text": "C#"}],
        "detail": {"requirements": "Kubernetes 와 Terraform", "preferred_points": "C# 도 함"},
    }
    skills = extract_skills(job)
    assert skills[0] == "C#"                       # 회사가 체크한 것이 앞
    assert skills.count("C#") == 1                 # 양쪽에 있어도 한 번
    assert "Kubernetes" in skills and "Terraform" in skills
    assert all(s == canonical(s) for s in skills)  # 전부 표준 표기


def test_EXCEPTION_canonical_rejects_non_string():
    """결함: 숫자를 넣으면 AttributeError 로 죽었다. 빈 문자열로 삼켜도 안 된다."""
    assert_raises(TypeError, canonical, 123)
    assert canonical(None) == ""


def test_EXCEPTION_corpus_general_nouns_never_match():
    """corpus 에는 '운영' '감사' '보증' 같은 일반명사가 한글 스킬로 들어 있다."""
    assert find_skills_in_text("운영 경험, 감사 대응, 보증 업무, 디자인 관리") == []




def test_EXCEPTION_skill_tag_without_usable_name_is_dropped():
    assert extract_skills({"skill_tags": [{"tag_type_id": None, "text": ""}, {"text": "   "}]}) == []


def test_NORMAL_common_canonical():
    assert canonical("Apache Kafka") == "Kafka"
    assert canonical("GCP") == "Google Cloud"
    assert canonical("Spring Framework") == "Spring"
    assert canonical("MSSQL") == "SQL Server"
    assert kind_of("Kafka") == "tool"
    assert kind_of("Python") == "language"
    assert {canonical(n) for n in ("REST", "Restful API", "REST API")} == {"REST API"}


def test_NORMAL_skill_detection_from_prose():
    found = find_skills_in_text("Java(Kotlin) Spring 기반, Docker/K8s, Kafka. Python3 경험")
    for expected in ("Java", "Kotlin", "Spring", "Docker", "Kubernetes", "Kafka", "Python"):
        assert expected in found, f"{expected} 를 못 찾았다: {found}"


def test_NORMAL_tag_normalized_by_id():
    assert normalize_tag({"tag_type_id": 1554, "text": "Python"}) == "Python"
    assert normalize_tag({"tag_type_id": 5735, "text": "Apache Kafka"}) == "Kafka"


# ----------------------------------------------------------------------
# 한글 낱말 경계 — 목록이 아니라 규칙으로 판정한다
# ----------------------------------------------------------------------


def test_EXCEPTION_korean_term_inside_a_longer_word():
    """결함이었던 것: '가상화폐 거래소' 에서 '가상화' 가 잡혔다.

    전에는 충돌하는 복합어를 파일에 적어 막았다. 그건 **열린 집합**이라 관측한 것만
    막고 다음 것은 그대로 통과시킨다. 지금은 뒤에 오는 것이 조사·접미사인지로 판정한다.
    """
    assert find_skills_in_text("가상화폐 거래소 백엔드") == []
    assert find_skills_in_text("컨테이너선 화물 관리") == []
    # 진짜 기술어는 그대로 잡혀야 한다
    assert "가상화" in find_skills_in_text("서버 가상화 운영")
    assert "컨테이너" in find_skills_in_text("컨테이너 오케스트레이션 경험")


def test_BOUNDARY_korean_rule_generalizes_to_unlisted_collisions():
    """**한 번도 적어 둔 적 없는 복합어**로 규칙이 실제로 일반화하는지 본다.

    목록 방식이었다면 전부 통과시켰을 것들이다 — 그게 이 규칙을 도입한 이유다.
    """
    never_listed = [
        ("가상화학 실험실 소프트웨어", "가상화"),      # 가상화 + 학
        ("컨테이너박스 재고 관리", "컨테이너"),        # 컨테이너 + 박스
        ("임베디드형 장비", "임베디드"),               # '형' 은 접미사라 통과하지만
        ("머신러닝머신 판매", "머신러닝"),             # 머신러닝 + 머신
        ("딥러닝쿠키 브랜드", "딥러닝"),               # 딥러닝 + 쿠키
    ]
    rejected = [text for text, term in never_listed if term not in find_skills_in_text(text)]
    # '임베디드형' 은 접미사 '형' 이라 통과가 맞다. 나머지 넷은 다른 낱말이므로 거부돼야 한다
    assert len(rejected) == 4, f"거부된 것: {rejected}"
    assert "임베디드" in find_skills_in_text("임베디드형 장비")


def test_BOUNDARY_korean_particles_and_suffixes_pass():
    """조사·어미·접미사 뒤는 낱말이 끝난 것이다. 문법이 정한 닫힌 부류다."""
    for sentence in (
        "컨테이너를 쓴다", "컨테이너가 뜬다", "컨테이너에 담는다", "컨테이너와 함께",
        "컨테이너로 배포", "컨테이너의 수명", "컨테이너화 경험", "컨테이너 기반",
    ):
        assert "컨테이너" in find_skills_in_text(sentence), sentence


def test_BOUNDARY_korean_term_at_the_very_end():
    """글 끝에서 끝나면 낱말도 끝난 것이다."""
    assert "컨테이너" in find_skills_in_text("우리가 쓰는 것은 컨테이너")
    assert "마이크로서비스" in find_skills_in_text("전환 대상: 마이크로서비스")


def test_BOUNDARY_korean_term_followed_by_punctuation_or_ascii():
    assert "컨테이너" in find_skills_in_text("컨테이너, 쿠버네티스")
    assert "컨테이너" in find_skills_in_text("컨테이너(Docker)")
    assert "딥러닝" in find_skills_in_text("딥러닝 PyTorch 경험")
