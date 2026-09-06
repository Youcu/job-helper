"""조건 → 검색 파라미터.

세 함정을 여기서 막는다 — 셋 다 **예외가 안 나고 결과도 나온다.**

    직무 대분류      → 필터가 통째로 무시돼 전체가 나온다
    구가 있는 시     → `성남시` 라는 코드가 아예 없다
    못 옮긴 근무지   → 조용히 빼면 전국을 긁는다
"""
from __future__ import annotations

from _common.env import ConfigError
from lib.config import Config
from lib.filters import (CAREER_ANY, CAREER_NEW, LocationError, ambiguous_names,
                         build_conditions, career_code, duty_value, resolve_locations)

from .helpers import check, check_equal, check_raises


def test_NORMAL_province_and_district():
    check_equal(resolve_locations(["서울"]), "I000", "시도")
    check("B150" in resolve_locations(["성남시 분당구"]).split(","), "구")


def test_NORMAL_duty_middle_codes_pass_through():
    check_equal(duty_value([1000229, 1000231]), "1000229,1000231", "중분류는 그대로")


def test_NORMAL_build_conditions_has_menucode():
    conditions = build_conditions(Config(job_ids=[1000229]))
    check_equal(conditions["menucode"], "duty", "직무 검색 화면임을 알린다")
    check_equal(conditions["duty"], "1000229", "직무")


def test_EXCEPTION_duty_group_code_is_refused():
    # 결함이 될 뻔한 곳: `duty=10031` 은 기준선과 같은 197,561건이 나온다. 에러가 안 난다.
    error = check_raises(ConfigError, lambda: duty_value([10031]), "대분류 코드")
    check("대분류" in str(error), "무엇이 문제인지 말해야 한다")
    check("무시" in str(error), "왜 위험한지 말해야 한다")


def test_EXCEPTION_unknown_duty_code():
    error = check_raises(ConfigError, lambda: duty_value([999999]), "코드표에 없는 값")
    check("jobkorea_duty.json" in str(error), "어디를 봐야 하는지 알려야 한다")


def test_EXCEPTION_unknown_location_stops_the_run():
    # 조용히 빼면 조건이 느슨해져 전국을 긁는다 — 결과가 늘어나는 방향이라 눈치채기 어렵다.
    error = check_raises(LocationError, lambda: resolve_locations(["판교시"]), "없는 지명")
    check("판교시" in str(error), "어느 이름이 문제인지 짚어야 한다")


def test_EXCEPTION_ambiguous_district_name_alone():
    names = ambiguous_names()
    check(bool(names), "여러 시도에 겹치는 구 이름이 있어야 한다")
    check_raises(LocationError, lambda: resolve_locations([names[0]]),
                 "%s 는 시도를 붙이지 않으면 못 정한다" % names[0])
    # 시도를 붙이면 풀린다.
    check(bool(resolve_locations(["대구 중구"])), "시도를 붙이면 풀려야 한다")


def test_BOUNDARY_city_with_districts_expands():
    # 결함이 될 뻔한 곳: 잡코리아에는 `성남시` 코드가 **없다.** 이름만 찾으면 못 찾는다.
    codes = resolve_locations(["성남시"]).split(",")
    check(len(codes) >= 3, "성남시는 구 셋으로 펼쳐져야 한다: %r" % codes)
    for city in ("수원시", "용인시", "화성시", "고양시", "안산시"):
        check(len(resolve_locations([city]).split(",")) >= 2,
              "%s 도 구로 펼쳐져야 한다" % city)


def test_BOUNDARY_nationwide_means_no_condition():
    check_equal(resolve_locations(["전국"]), "", "전국은 조건을 안 거는 것이다")
    check_equal(resolve_locations([]), "", "비어 있어도 조건 없음")


def test_BOUNDARY_duplicate_locations_collapse():
    once = resolve_locations(["성남시"])
    twice = resolve_locations(["성남시", "성남시 분당구"])
    check_equal(sorted(twice.split(",")), sorted(once.split(",")),
                "같은 코드를 두 번 넣지 않는다")


def test_BOUNDARY_whitespace_in_location_name():
    check_equal(resolve_locations(["  성남시  분당구 "]), resolve_locations(["성남시 분당구"]),
                "사람이 띄어쓰기를 흘려도 같은 결과여야 한다")


def test_BOUNDARY_career_bands():
    check_equal(career_code(-1), "", "전체는 조건 없음")
    check_equal(career_code(0), CAREER_NEW, "0년차는 신입")
    for yoe, expected in [(1, "2"), (3, "2"), (4, "3"), (6, "3"), (7, "4"),
                          (9, "4"), (10, "5"), (15, "5"), (16, "6"), (20, "6")]:
        check_equal(career_code(yoe), expected, "%d년차" % yoe)
    check_equal(career_code(99), "7", "구간을 넘으면 마지막 구간")
    check(CAREER_ANY not in (career_code(0), career_code(3)),
          "경력무관을 몰래 더하지 않는다 — 사람인에서 그러다 경력직이 섞였다")


def test_BOUNDARY_empty_values_are_dropped():
    # 빈 파라미터를 보내면 잡코리아가 조건으로 잘못 읽을 수 있고, 무엇이 걸렸는지도 흐려진다.
    conditions = build_conditions(Config(job_ids=[1000229], yoe=-1, education="",
                                         home_locations=[], employment_types=[]))
    check_equal(sorted(conditions), ["duty", "menucode"], "빈 값은 안 들어간다: %r" % conditions)


def test_BOUNDARY_all_conditions_together():
    conditions = build_conditions(Config(
        job_ids=[1000229, 1000231], yoe=0, education="대졸4",
        home_locations=["서울", "성남시"], employment_types=["regular", "intern"]))
    check_equal(conditions["career"], CAREER_NEW, "신입")
    check_equal(conditions["edu"], "5", "대졸4")
    check_equal(conditions["jobtype"], "1,3", "정규직·인턴은 콤마로 이어야 OR 다")
    check(conditions["local"].startswith("I000,"), "지역: %r" % conditions["local"])
