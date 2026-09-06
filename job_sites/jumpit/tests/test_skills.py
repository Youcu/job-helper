"""기술스택 뽑기 (①구조화 ∪ ②산문).

이 사이트의 `techStacks` 는 **목록과 상세의 모양이 다르다.**

    목록  ["Git", "Next.js", "React"]                     문자열 배열
    상세  [{"stack": "Git", "imagePath": "…"}, …]          객체 배열

하나만 가정하면 한쪽에서 조용히 빈 목록이 나온다. 그리고 **사이트가 붙인 딱지와 본문이
어긋나는 것이 이 사이트의 특징**이라(`Spring Boot` 딱지가 없는 공고의 본문이
`Spring Framework` 를 요구한다) ② 산문 매칭이 특히 중요하다.
"""
from __future__ import annotations

import json

from lib.skills import (extract_skills, find_skills_in_text, prose_text,
                        raw_stacks, structured_skills)

from .helpers import check, check_equal, detail, position, temp_json


def test_NORMAL_raw_stacks_reads_the_listing_shape():
    check_equal(raw_stacks({"techStacks": ["Git", "React"]}), ["Git", "React"], "문자열 배열")


def test_NORMAL_raw_stacks_reads_the_detail_shape():
    check_equal(raw_stacks({"techStacks": [{"stack": "Git", "imagePath": "x"},
                                           {"stack": "React"}]}),
                ["Git", "React"], "객체 배열")


def test_NORMAL_real_position_and_detail_both_yield_stacks():
    check(raw_stacks(position()), "목록에서 나와야 한다: %r" % raw_stacks(position()))
    check(raw_stacks(detail()), "상세에서도 나와야 한다: %r" % raw_stacks(detail()))


def test_NORMAL_structured_skills_are_normalised():
    got = structured_skills({}, {"techStacks": [{"stack": "java"}, {"stack": "MYSQL"}]},
                            candidates_file=temp_json())
    check_equal(got, ["Java", "MySQL"], "표준 표기로 바꾼다")


def test_NORMAL_union_of_both_sources():
    got = extract_skills({"techStacks": ["java"]},
                         {"qualifications": "Docker 로 배포합니다"},
                         candidates_file=temp_json())
    check("Java" in got and "Docker" in got, "①과 ② 를 합쳐야 한다: %r" % got)


def test_NORMAL_real_detail_yields_several():
    got = extract_skills(position(), detail(), candidates_file=temp_json())
    check(len(got) >= 3, "실제 공고는 기술이 여럿 나와야 한다: %r" % got)


def test_EXCEPTION_empty_and_missing_fields():
    for pos, det in (({}, {}), ({"techStacks": None}, {"techStacks": []}),
                     ({}, {"qualifications": None})):
        check_equal(extract_skills(pos, det, candidates_file=temp_json()), [],
                    "빈 입력에 이름을 지어내지 않는다: %r %r" % (pos, det))


def test_EXCEPTION_broken_stack_entries():
    # 응답이 늘 온전하다는 보장이 없다. 터지면 그 공고 하나가 아니라 실행이 죽는다.
    got = extract_skills({}, {"techStacks": [{"stack": "java"}, {}, None, "docker", 123,
                                             {"stack": "  "}]},
                         candidates_file=temp_json())
    check("Java" in got and "Docker" in got, got)


def test_BOUNDARY_listing_and_detail_are_merged():
    # 둘이 어긋날 때 넓은 쪽을 쓴다 — 목록에만 있는 이름을 잃으면 안 된다.
    got = structured_skills({"techStacks": ["python"]}, {"techStacks": [{"stack": "java"}]},
                            candidates_file=temp_json())
    check("Java" in got and "Python" in got, "둘 다 살아야 한다: %r" % got)


def test_BOUNDARY_unresolved_names_are_recorded_for_a_human():
    path = temp_json()
    structured_skills({}, {"techStacks": [{"stack": "java"},
                                          {"stack": "zzz알수없는이름zzz"}]},
                      candidates_file=path)
    check(path.exists(), "후보 파일을 만들어야 한다")
    book = json.loads(path.read_text(encoding="utf-8")).get("후보", {})
    check("zzz알수없는이름zzz" in book, "못 푼 이름이 쌓여야 한다: %r" % list(book))


def test_BOUNDARY_prose_covers_the_three_body_fields():
    text = prose_text({"qualifications": "Java", "preferredRequirements": "Kotlin",
                       "responsibility": "서버 개발"})
    for word in ("Java", "Kotlin", "서버"):
        check(word in text, "%s 가 빠졌다: %r" % (word, text))


def test_BOUNDARY_prose_finds_what_the_tag_missed():
    # 이 사이트의 핵심 문제 — 딱지에 없는 것이 본문에 있다.
    got = extract_skills({"techStacks": []},
                         {"qualifications": "Spring Framework 기반 개발 경험"},
                         candidates_file=temp_json())
    check(any("Spring" in name for name in got), "본문에서 찾아야 한다: %r" % got)


def test_BOUNDARY_no_duplicates_across_sources():
    got = extract_skills({"techStacks": ["java"]}, {"qualifications": "Java 경험자"},
                         candidates_file=temp_json())
    check_equal(got.count("Java"), 1, "①과 ② 에 다 있어도 한 번만: %r" % got)


def test_BOUNDARY_word_boundary_in_prose():
    check("Go" not in find_skills_in_text("Google 에서 일했습니다"), "Google 안의 Go 는 아니다")


def test_BOUNDARY_is_pure():
    path = temp_json()
    a = extract_skills(position(), detail(), candidates_file=path)
    b = extract_skills(position(), detail(), candidates_file=path)
    check_equal(a, b, "같은 입력에 늘 같은 값")


def test_BOUNDARY_clear_caches_reloads_the_matcher():
    # 테스트가 사전을 갈아 끼울 때 쓴다. 캐시가 안 비면 앞 테스트의 어휘가 남는다.
    from lib.skills import clear_caches
    before = find_skills_in_text("Python 개발자")
    clear_caches()
    check_equal(find_skills_in_text("Python 개발자"), before, "비운 뒤에도 같은 값")
