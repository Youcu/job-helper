"""기술스택 뽑기 (①구조화 ∪ ②산문).

**`기술스택` 칸에 직무가 섞여 있다** — `Backend`, `Frontend`, `Software Engineering`.
이 사이트가 직무와 기술을 한 칸에 쓰기 때문이다. 공통 코퍼스로 풀리는 것만 남기면
그 대부분은 저절로 빠지고, 못 푼 것은 후보로 쌓여 사람이 본다 (D-14).

**`필수 기술`·`우대 기술` 칸은 쓰지 않는다** — 이름과 달리 자격 문장이다.
"""
from __future__ import annotations

import json

from lib.skills import extract_skills, find_skills_in_text, raw_stacks, structured_skills

from .helpers import check, check_equal, detail_text, temp_json


def test_NORMAL_raw_stacks_merges_listing_and_detail():
    got = raw_stacks({"기술": "Python, React"}, "- 기술스택: Java, Python\n")
    check_equal(got, ["Java", "Python", "React"], "둘을 합치고 중복은 뺀다")


def test_NORMAL_real_detail_yields_stacks():
    got = extract_skills({"기술": ""}, detail_text(), candidates_file=temp_json())
    check(len(got) >= 3, "실제 공고는 기술이 여럿 나와야 한다: %r" % got)


def test_NORMAL_structured_skills_are_normalised():
    got = structured_skills({}, "- 기술스택: java, MYSQL, spring boot\n",
                            candidates_file=temp_json())
    check_equal(got, ["Java", "MySQL", "Spring Boot"], "표준 표기로 바꾼다")


def test_NORMAL_union_of_both_sources():
    detail = "- 기술스택: java\n[상세 내용]\nDocker 로 배포합니다\n"
    got = extract_skills({}, detail, candidates_file=temp_json())
    check("Java" in got and "Docker" in got, "①과 ② 를 합쳐야 한다: %r" % got)


def test_EXCEPTION_empty_and_missing_fields():
    for listing, detail in (({}, ""), ({"기술": ""}, "- 기술스택: \n"), ({}, "아무것도 없음")):
        check_equal(extract_skills(listing, detail, candidates_file=temp_json()), [],
                    "빈 입력에 이름을 지어내지 않는다: %r %r" % (listing, detail))


def test_BOUNDARY_role_names_are_dropped_by_the_corpus():
    # 결함이 될 뻔한 곳: `기술스택` 칸을 그대로 쓰면 직무가 기술스택 칸에 들어간다.
    got = structured_skills({}, "- 기술스택: Backend, Frontend, Software Engineering, java\n",
                            candidates_file=temp_json())
    check("Java" in got, got)
    check("Software Engineering" not in got, "직무는 기술이 아니다: %r" % got)


def test_BOUNDARY_does_not_read_the_required_skills_field():
    # `필수 기술` 은 자격 문장이다. 여기서 읽으면 `Python 개발 유경험자` 가 기술이 된다.
    detail = "- 필수 기술: Python 개발 유경험자, Linux 서버 활용 가능자\n- 기술스택: java\n"
    check_equal(raw_stacks({}, detail), ["java"], "기술스택 칸만 읽는다")


def test_BOUNDARY_unresolved_names_are_recorded_for_a_human():
    path = temp_json()
    structured_skills({}, "- 기술스택: java, zzz알수없는이름zzz\n", candidates_file=path)
    check(path.exists(), "후보 파일을 만들어야 한다")
    book = json.loads(path.read_text(encoding="utf-8")).get("후보", {})
    check("zzz알수없는이름zzz" in book, "못 푼 이름이 쌓여야 한다: %r" % list(book))


def test_BOUNDARY_no_duplicates_across_sources():
    detail = "- 기술스택: java\n[상세 내용]\nJava 경험자\n"
    got = extract_skills({}, detail, candidates_file=temp_json())
    check_equal(got.count("Java"), 1, "①과 ② 에 다 있어도 한 번만: %r" % got)


def test_BOUNDARY_word_boundary_in_prose():
    check("Go" not in find_skills_in_text("Google 에서 일했습니다"), "Google 안의 Go 는 아니다")


def test_BOUNDARY_is_pure():
    path = temp_json()
    detail = "- 기술스택: java\n[상세 내용]\nDocker\n"
    check_equal(extract_skills({}, detail, candidates_file=path),
                extract_skills({}, detail, candidates_file=path), "같은 입력에 늘 같은 값")


def test_BOUNDARY_clear_caches_reloads_the_matcher():
    from lib.skills import clear_caches
    before = find_skills_in_text("Python 개발자")
    clear_caches()
    check_equal(find_skills_in_text("Python 개발자"), before, "비운 뒤에도 같은 값")
