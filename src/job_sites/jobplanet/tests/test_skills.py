"""기술스택 뽑기 (①구조화 ∪ ②산문).

`skills` 배열을 **그대로 쓰면 안 된다**는 것이 이 모듈의 요점이다. 실제 공고에서:

    ["java", "kotlin", "MYSQL", "JIRA", "spring boot", "mybatis",
     "backend", "slack", "confluence"]

표기가 흔들리고(`MYSQL`·`java`), 기술이 아닌 것이 섞인다(`backend`, `slack`, `백엔드 개발`).
코퍼스로 풀리는 것만 남기고, 못 푼 이름은 후보로 쌓아 사람이 보게 한다 (D-14).
"""
from __future__ import annotations

import json

from lib.skills import (extract_skills, find_skills_in_text, prose_text,
                        structured_skills)

from .helpers import check, check_equal, own_detail, relay_detail, temp_json


def test_NORMAL_structured_skills_are_normalised():
    got = structured_skills({"skills": ["java", "MYSQL", "spring boot"]},
                            candidates_file=temp_json())
    check_equal(got, ["Java", "MySQL", "Spring Boot"], "표준 표기로 바꾼다")


def test_NORMAL_real_own_posting_yields_skills():
    got = extract_skills(own_detail(), candidates_file=temp_json())
    check(len(got) >= 3, "자체 공고는 기술이 여럿 나와야 한다: %r" % got)


def test_NORMAL_prose_joins_the_body_fields():
    text = prose_text({"required_qualification": "Java 3년",
                       "preferred_skill": "Kotlin 우대",
                       "primary_responsibility": "서버 개발"})
    for word in ("Java", "Kotlin", "서버"):
        check(word in text, "%s 가 빠졌다: %r" % (word, text))


def test_NORMAL_union_of_both_sources():
    detail = {"skills": ["java"], "required_qualification": "Docker 로 배포합니다"}
    got = extract_skills(detail, candidates_file=temp_json())
    check("Java" in got and "Docker" in got, "①과 ② 를 합쳐야 한다: %r" % got)


def test_EXCEPTION_relay_posting_yields_nothing():
    # 잡코리아 중계 공고는 본문도 skills 도 비어 있다. 채워 넣지 않는다.
    check_equal(extract_skills(relay_detail(), candidates_file=temp_json()), [],
                "빈 공고에서 기술을 지어내지 않는다")


def test_EXCEPTION_empty_and_missing_fields():
    for detail in ({}, {"skills": None}, {"skills": []},
                   {"required_qualification": None}):
        check_equal(extract_skills(detail, candidates_file=temp_json()), [],
                    "빈 입력: %r" % detail)


def test_EXCEPTION_non_string_skill_entries():
    # 응답이 늘 문자열 배열이라는 보장이 없다. 터지면 그 공고 하나가 아니라 실행이 죽는다.
    got = extract_skills({"skills": ["java", None, 123, "  ", "docker"]},
                         candidates_file=temp_json())
    check("Java" in got and "Docker" in got, got)


def test_BOUNDARY_non_tech_entries_are_dropped():
    # 결함이 될 뻔한 곳: `skills` 를 그대로 쓰면 이런 것들이 기술스택 칸에 들어간다.
    got = structured_skills(
        {"skills": ["backend", "slack", "confluence", "백엔드 개발", "java"]},
        candidates_file=temp_json())
    check_equal(got, ["Java"], "기술이 아닌 것은 빠진다: %r" % got)


def test_BOUNDARY_unresolved_names_are_recorded_for_a_human():
    # 버리기만 하면 코퍼스가 늘 그대로다. 사람이 볼 수 있게 쌓아야 한다.
    path = temp_json()
    structured_skills({"skills": ["java", "백엔드 개발"]}, candidates_file=path)
    check(path.exists(), "후보 파일을 만들어야 한다")
    book = json.loads(path.read_text(encoding="utf-8")).get("후보", {})
    check("백엔드 개발" in book, "못 푼 이름이 쌓여야 한다: %r" % list(book))
    check("java" not in book and "Java" not in book, "푼 이름은 후보가 아니다")


def test_BOUNDARY_does_not_write_to_the_production_file():
    # 사람인에서 테스트가 진짜 corpus_candidates.json 을 더럽힌 적이 있다.
    path = temp_json()
    structured_skills({"skills": ["zzz알수없는이름zzz"]}, candidates_file=path)
    check(path.exists(), "지정한 파일에만 써야 한다")


def test_BOUNDARY_no_duplicates_across_sources():
    detail = {"skills": ["java"], "required_qualification": "Java 경험자"}
    got = extract_skills(detail, candidates_file=temp_json())
    check_equal(got.count("Java"), 1, "①과 ② 에 다 있어도 한 번만: %r" % got)


def test_BOUNDARY_word_boundary_in_prose():
    check("Go" not in find_skills_in_text("Google 에서 일했습니다"), "Google 안의 Go 는 아니다")


def test_BOUNDARY_is_pure():
    detail = {"skills": ["java"], "required_qualification": "Docker"}
    path = temp_json()
    check_equal(extract_skills(detail, candidates_file=path),
                extract_skills(detail, candidates_file=path), "같은 입력에 늘 같은 값")


def test_BOUNDARY_clear_caches_reloads_the_matcher():
    # 테스트가 사전을 갈아 끼울 때 쓴다. 캐시가 안 비면 앞 테스트의 어휘가 남는다.
    from lib.skills import clear_caches
    before = find_skills_in_text("Python 개발자")
    clear_caches()
    check_equal(find_skills_in_text("Python 개발자"), before, "비운 뒤에도 같은 값이어야 한다")
