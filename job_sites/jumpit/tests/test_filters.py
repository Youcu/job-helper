"""조건 → 검색 파라미터.

**이 사이트는 앞선 셋과 반대로 도는 것이 둘 있다.** 순한 편인데, 그 순함을 믿고
넘어가면 다른 사이트에서 배운 대비를 엉뚱하게 적용하게 된다.

    같은 이름을 두 번 보내도 **둘 다 먹는다** (1&2 → 189건 = 1,2 → 189건)
    시 코드가 **구를 포함한다** (성남시 단독 118건 = 성남시+구 셋 118건)

그래서 여기서는 펼치지 않는다. 그 사실을 테스트로 굳혀 둔다 — 나중에 누가 사람인 코드를
베껴 와 "성남시를 구로 펼쳐야지" 하고 고치지 못하게.
"""
from __future__ import annotations

from _common.env import ConfigError
from lib.config import Config
from lib.filters import (LocationError, ambiguous_names, build_params,
                         category_codes, resolve_locations)

from .helpers import check, check_equal, check_raises


def test_NORMAL_category_codes_pass_through():
    check_equal(category_codes([1, 3]), ["1", "3"], "직무 코드는 그대로")


def test_NORMAL_province_and_district():
    check_equal(resolve_locations(["서울"]), ["101000"], "시도")
    check_equal(resolve_locations(["서울 강남구"]), ["101010"], "구")
    check_equal(resolve_locations(["성남시"]), ["102180"], "시")


def test_NORMAL_build_params_has_sort():
    params = build_params(Config(job_ids=[1]))
    check_equal(params["sort"], "popular", "화면과 같은 정렬")
    check_equal(params["jobCategory"], ["1"], "직무")


def test_NORMAL_all_three_conditions():
    params = build_params(Config(job_ids=[1, 3], yoe=0,
                                 home_locations=["서울", "성남시"]))
    check_equal(params["jobCategory"], ["1", "3"], "직무 둘")
    check_equal(params["locationTag"], ["101000", "102180"], "지역 둘")
    check_equal(params["career"], "0", "신입")


def test_EXCEPTION_unknown_category_code():
    error = check_raises(ConfigError, lambda: category_codes([999]), "코드표에 없는 값")
    check("jumpit_job_category.json" in str(error), "어디를 봐야 하는지 알려야 한다")


def test_EXCEPTION_category_14_is_not_in_the_table():
    # 코드 14 는 스캔에서 공고가 하나도 안 나와 표에 안 넣었다. 넣으라고 하면 멈춘다.
    check_raises(ConfigError, lambda: category_codes([14]), "빈 코드")


def test_EXCEPTION_unknown_location_stops_the_run():
    # 조용히 빼면 조건이 느슨해져 전국을 긁는다 — 결과가 늘어나는 방향이라 눈치채기 어렵다.
    error = check_raises(LocationError, lambda: resolve_locations(["뉴욕"]), "없는 지명")
    check("뉴욕" in str(error), "어느 이름이 문제인지 짚어야 한다")


def test_EXCEPTION_ambiguous_district_name_alone():
    names = ambiguous_names()
    check(bool(names), "여러 시도에 겹치는 이름이 있어야 한다")
    check_raises(LocationError, lambda: resolve_locations([names[0]]),
                 "%s 는 시도를 붙이지 않으면 못 정한다" % names[0])


def test_BOUNDARY_city_code_is_not_expanded():
    # **여기가 사람인과 반대다.** 사람인은 시 코드가 구를 안 잡아서 펼쳐야 했는데,
    # 점핏은 시 코드 하나가 구를 포함한다 (성남시 단독 118건 = 성남시+구 셋 118건).
    for city in ("성남시", "수원시", "용인시", "화성시", "고양시"):
        codes = resolve_locations([city])
        check_equal(len(codes), 1, "%s 는 코드 하나여야 한다 (펼치면 안 된다): %r" % (city, codes))


def test_BOUNDARY_nationwide_means_no_condition():
    check_equal(resolve_locations(["전국"]), [], "전국은 조건을 안 거는 것이다")
    check_equal(resolve_locations([]), [], "비어 있어도 조건 없음")
    check("locationTag" not in build_params(Config(job_ids=[1])), "빈 값은 안 실린다")


def test_BOUNDARY_duplicate_locations_collapse():
    check_equal(resolve_locations(["서울", "서울"]), ["101000"], "같은 코드를 두 번 넣지 않는다")


def test_BOUNDARY_whitespace_in_location_name():
    check_equal(resolve_locations(["  서울  강남구 "]), resolve_locations(["서울 강남구"]),
                "사람이 띄어쓰기를 흘려도 같은 결과여야 한다")


def test_BOUNDARY_yoe_zero_is_a_condition_not_emptiness():
    # `0` 을 거짓으로 다루면 신입 조건이 조용히 사라져 전체가 걷힌다.
    check_equal(build_params(Config(job_ids=[1], yoe=0))["career"], "0", "신입은 조건이다")
    check("career" not in build_params(Config(job_ids=[1], yoe=-1)), "전체는 조건 없음")


def test_BOUNDARY_career_is_a_single_value_not_a_range():
    # `career=N` 은 **N년차가 지원할 수 있는 공고**다 (`minCareer <= N <= maxCareer`).
    # 잡플래닛처럼 범위로 보내면 안 된다.
    value = build_params(Config(job_ids=[1], yoe=3))["career"]
    check_equal(value, "3", "값 하나다: %r" % value)
    check("," not in value, "범위가 아니다")


def test_BOUNDARY_tech_stacks_never_becomes_a_parameter():
    # 이 사이트의 기술 필터는 본문과 어긋난다 — `Spring Boot` 를 고르면 아무것도 안 나오는데
    # 그 필터를 풀고 열면 본문이 `Spring Framework` 를 요구한다.
    params = build_params(Config(job_ids=[1], tech_stacks=["Spring Boot", "Python"]))
    joined = str(params)
    check("Spring" not in joined and "tech" not in joined.lower(),
          "기술은 파라미터로 안 나간다: %r" % params)


def test_BOUNDARY_education_and_employment_never_become_parameters():
    params = build_params(Config(job_ids=[1], education="대졸4",
                                 employment_types=["regular", "intern"]))
    check_equal(sorted(params), ["jobCategory", "sort"], "그 둘은 안 실린다: %r" % params)
