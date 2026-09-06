"""조건 → 검색 파라미터.

세 함정을 여기서 막는다 — **셋 다 예외가 안 나고 결과도 나온다.**

    대분류를 같이 보냄    → 중분류가 무시돼 그 대분류 전체가 나온다
    경력을 값 하나로      → 필터가 통째로 무시돼 기준선이 나온다
    못 옮긴 근무지        → 조용히 빼면 전국을 긁는다
"""
from __future__ import annotations

from _common.env import ConfigError
from lib.config import Config
from lib.filters import (LocationError, build_params, city_names,
                         experience_range, occupation_value, resolve_cities)

from .helpers import check, check_equal, check_raises


def test_NORMAL_occupation_middle_codes_pass_through():
    check_equal(occupation_value([11904, 11905]), "11904,11905", "중분류는 그대로")


def test_NORMAL_province_names():
    check_equal(resolve_cities(["서울"]), "1", "서울")
    check_equal(resolve_cities(["서울", "경기"]), "1,2", "둘은 콤마로 이어야 OR 다")


def test_NORMAL_build_params():
    params = build_params(Config(job_ids=[11904], yoe=0, home_locations=["서울"],
                                 employment_types=["regular"]))
    check_equal(params["occupation_level2"], "11904", "직무")
    check_equal(params["city"], "1", "지역")
    check_equal(params["job_type"], "3", "정규직")
    check_equal(params["years_of_experience"], "0,0", "신입")


def test_EXCEPTION_occupation_group_code_is_refused():
    # 결함이 될 뻔한 곳: `level1=11600` 을 같이 보내면 중분류가 무시돼 2,779건이 나온다.
    error = check_raises(ConfigError, lambda: occupation_value([11600]), "대분류 코드")
    check("대분류" in str(error), "무엇이 문제인지 말해야 한다")
    check("무시" in str(error), "왜 위험한지 말해야 한다")


def test_EXCEPTION_unknown_occupation_code():
    error = check_raises(ConfigError, lambda: occupation_value([999999]), "코드표에 없는 값")
    check("jobplanet_occupation.json" in str(error), "어디를 봐야 하는지 알려야 한다")


def test_EXCEPTION_unknown_location_stops_the_run():
    error = check_raises(LocationError, lambda: resolve_cities(["뉴욕"]), "없는 지명")
    check("뉴욕" in str(error), "어느 이름이 문제인지 짚어야 한다")
    check("시도까지만" in str(error), "왜 좁은 이름을 못 쓰는지 알려야 한다")


def test_BOUNDARY_narrow_place_widens_to_its_province():
    # 잡플래닛 지역 코드에는 구·시가 없다. `성남시` 는 `경기`(2)로 올라가고,
    # 실제로 성남인지는 `record.matches_locations` 가 근무지 글로 다시 본다.
    check_equal(resolve_cities(["성남시"]), "2", "성남시 → 경기")
    check_equal(resolve_cities(["강남구"]), "1", "강남구 → 서울")
    check_equal(resolve_cities(["성남시 분당구"]), "2", "시·구를 함께 적어도 경기")


def test_BOUNDARY_duplicate_provinces_collapse():
    check_equal(resolve_cities(["성남시", "수원시", "용인시"]), "2",
                "같은 시도로 올라가면 코드는 하나다")
    check_equal(resolve_cities(["서울", "강남구"]), "1", "서울과 강남구는 같은 코드")


def test_BOUNDARY_nationwide_means_no_condition():
    check_equal(resolve_cities(["전국"]), "", "전국은 조건을 안 거는 것이다")
    check_equal(resolve_cities([]), "", "비어 있어도 조건 없음")


def test_BOUNDARY_whitespace_in_location_name():
    check_equal(resolve_cities(["  성남시  분당구 "]), resolve_cities(["성남시 분당구"]),
                "사람이 띄어쓰기를 흘려도 같은 결과여야 한다")


def test_BOUNDARY_experience_is_a_range_not_a_single_value():
    # 결함이 될 뻔한 곳: `years_of_experience=0` 은 기준선 34,813건 그대로가 나온다.
    # 범위 필터라 두 값이 있어야 걸린다 — `0,0` 은 22,508건.
    check_equal(experience_range(0), "0,0", "신입은 0,0")
    check_equal(experience_range(3), "0,3", "3년차는 그 아래를 포함한다")
    check_equal(experience_range(-1), "", "전체는 조건 없음")
    check("," in experience_range(0), "값 하나만 보내면 조용히 무시된다")


def test_BOUNDARY_experience_ceiling():
    check_equal(experience_range(11), "0,11", "코드표 위쪽 끝")
    check_equal(experience_range(99), "0,11", "넘으면 위쪽 끝으로 붙인다")


def test_BOUNDARY_empty_values_are_dropped():
    params = build_params(Config(job_ids=[11904], yoe=-1, home_locations=[],
                                 employment_types=[]))
    check_equal(sorted(params), ["occupation_level2"], "빈 값은 안 들어간다: %r" % params)


def test_BOUNDARY_education_is_never_a_parameter():
    # 자체 공고 84%가 '학력무관' 이라 걸면 사라진다 (실측 37→6건).
    params = build_params(Config(job_ids=[11904], education="대졸4"))
    check("education_level_id" not in params, "학력은 파라미터로 안 나간다: %r" % params)


def test_BOUNDARY_city_table_has_no_district():
    # 이 사실이 설계 전체를 좌우한다 — 시·구를 서버에 못 걸어서 받은 뒤 거른다.
    names = city_names()
    check(len(names) >= 17, "시도 목록: %r" % names)
    for narrow in ("강남구", "성남시", "분당구"):
        check(narrow not in names, "%s 는 코드표에 없어야 한다" % narrow)
