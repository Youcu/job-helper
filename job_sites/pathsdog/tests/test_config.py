""".env 읽기.

이 사이트는 **직무를 숫자 코드가 아니라 이름으로 받는다** — 직무와 기술을 한 칸에
섞어 쓰기 때문이다 (MCP 문서: "신입 백엔드" → `skills: ["Backend"]`).
그리고 년차를 서버가 아는 구간 이름(`신입`·`주니어`·`미들`·`시니어`)으로 옮긴다.
"""
from __future__ import annotations

from _common.env import ConfigError
from lib.config import (EMPLOYMENT_TYPE_NAMES, KNOWN_ELSEWHERE, YOE_ALL, Config,
                        load_config)

from .helpers import check, check_equal, check_raises, env_file


def test_NORMAL_reads_every_field():
    config = load_config(env_file(
        "PATHSDOG_JOB_IDS=Backend,Fullstack\nYOE=0\nEDUCATION=대졸4\n"
        "HOME_LOCATIONS=서울,판교\nEMPLOYMENT_TYPES=regular,intern\n"
        "TECH_STACKS=Python\nHOPE_ANNUAL_SALARY=3300\n"))
    check_equal(config.job_ids, ["Backend", "Fullstack"], "역할 이름 그대로")
    check_equal(config.yoe, 0, "신입")
    check_equal(config.home_locations, ["서울", "판교"], "근무지")
    check_equal(config.employment_names, ["정규직", "인턴"], "고용형태 이름")


def test_NORMAL_defaults():
    config = load_config(env_file("PATHSDOG_JOB_IDS=Backend\n"))
    check_equal(config.yoe, YOE_ALL, "년차 기본값은 전체")
    check_equal(config.home_locations, [], "근무지 기본값은 전국")
    check_equal(config.employment_types, [], "고용형태 기본값 없음")


def test_EXCEPTION_job_ids_required():
    error = check_raises(ConfigError, lambda: load_config(env_file("YOE=0\n")),
                         "역할 없이 돌면 전체를 긁는다")
    check("PATHSDOG_JOB_IDS" in str(error), "무엇을 채워야 하는지 알려야 한다")
    check("이름" in str(error), "숫자가 아니라 이름이라는 것을 알려야 한다")


def test_EXCEPTION_does_not_fall_back_to_unprefixed_name():
    check_raises(ConfigError, lambda: load_config(env_file("JOB_IDS=Backend\n")),
                 "접두사 없는 JOB_IDS 는 Pathsdog 것이 아니다")


def test_EXCEPTION_typo_in_employment_type_stops():
    error = check_raises(ConfigError, lambda: load_config(env_file(
        "PATHSDOG_JOB_IDS=Backend\nEMPLOYMENT_TYPES=regular,정규직\n")), "오타")
    check("정규직" in str(error), "어느 값이 문제인지 짚어야 한다")


def test_EXCEPTION_yoe_out_of_range():
    check_raises(ConfigError, lambda: load_config(env_file(
        "PATHSDOG_JOB_IDS=Backend\nYOE=99\n")), "범위 밖")
    check_raises(ConfigError, lambda: load_config(env_file(
        "PATHSDOG_JOB_IDS=Backend\nYOE=-2\n")), "-1 보다 작은 값")


def test_BOUNDARY_experience_bands():
    # 서버가 정한 구간을 그대로 쓴다. **주니어는 1~3년 + 신입**이라 신입을 포함한다.
    for yoe, expected in [(0, "신입"), (1, "주니어"), (3, "주니어"),
                          (4, "미들"), (5, "미들"), (6, "시니어"), (30, "시니어")]:
        check_equal(Config(yoe=yoe).experience_filter, expected, "%d년차" % yoe)
    check_equal(Config(yoe=-1).experience_filter, "", "전체는 조건 없음")


def test_BOUNDARY_yoe_zero_is_a_condition_not_emptiness():
    # `0` 을 거짓으로 다루면 신입 조건이 조용히 사라져 전체가 걷힌다.
    check_equal(load_config(env_file("PATHSDOG_JOB_IDS=Backend\nYOE=0\n")).yoe, 0,
                "YOE=0 은 신입이다")
    check_equal(Config(yoe=0).experience_filter, "신입", "조건으로도 살아야 한다")


def test_BOUNDARY_unsupported_employment_types_are_reported():
    # `dispatch`(파견) 는 다른 사이트에는 있고 여기는 없다. 멈추지는 않되 남긴다.
    config = load_config(env_file(
        "PATHSDOG_JOB_IDS=Backend\nEMPLOYMENT_TYPES=regular,dispatch\n"))
    check_equal(config.employment_names, ["정규직"], "걸 수 있는 것만")
    check_equal(config.unsupported_employment_types, ["dispatch"], "못 건 것을 남긴다")


def test_BOUNDARY_every_known_employment_type_is_accepted():
    for name in set(EMPLOYMENT_TYPE_NAMES) | KNOWN_ELSEWHERE:
        config = load_config(env_file(
            "PATHSDOG_JOB_IDS=Backend\nEMPLOYMENT_TYPES=%s\n" % name))
        check_equal(config.employment_types, [name], "%s 는 멈추지 않아야 한다" % name)
