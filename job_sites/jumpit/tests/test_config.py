""".env 읽기.

이 사이트는 **필터가 셋뿐**이다 (지역·경력·직무). 기술스택·고용형태·학력은 못 걸거나
걸면 안 되는데, 조용히 무시하면 다른 사이트와 결과가 어긋난 이유를 나중에 못 찾는다.
그래서 "무시하되 무엇을 무시했는지 남기는가" 를 여기서 본다.
"""
from __future__ import annotations

from _common.env import ConfigError
from lib.config import EDUCATION_NAMES, KNOWN_ELSEWHERE, YOE_ALL, load_config

from .helpers import check, check_equal, check_raises, env_file


def test_NORMAL_reads_every_field():
    config = load_config(env_file(
        "JOB_ROLES=백엔드\nYOE=0\nEDUCATION=대졸4\n"
        "HOME_LOCATIONS=서울,성남시\nEMPLOYMENT_TYPES=regular\n"
        "TECH_STACKS=Python\nHOPE_ANNUAL_SALARY=3300\n"))
    check_equal(config.job_ids, [1], "직무 (백엔드는 코드 하나)")
    check_equal(config.yoe, 0, "신입")
    check_equal(config.home_locations, ["서울", "성남시"], "근무지")
    check_equal(config.tech_stacks, ["Python"], "기술은 읽기는 한다 (거는 것은 filters 가 안 한다)")


def test_NORMAL_defaults():
    config = load_config(env_file("JOB_ROLES=백엔드\n"))
    check_equal(config.yoe, YOE_ALL, "년차 기본값은 전체")
    check_equal(config.home_locations, [], "근무지 기본값은 전국")
    check_equal(config.employment_types, [], "고용형태 기본값 없음")


def test_NORMAL_employment_types_are_all_unsupported_here():
    # 점핏은 고용형태 필터가 아예 없다. 멀쩡한 값이라 멈추지 않되 남긴다.
    config = load_config(env_file(
        "JOB_ROLES=백엔드\nEMPLOYMENT_TYPES=regular,intern\n"))
    check_equal(config.unsupported_employment_types, ["regular", "intern"],
                "둘 다 못 걸었다고 남겨야 한다")



def test_EXCEPTION_typo_in_employment_type_stops():
    # `intern` 은 통과시키지만 오타는 멈춰야 한다. 둘을 가르는 것이 이 검사의 전부다.
    error = check_raises(ConfigError, lambda: load_config(env_file(
        "JOB_ROLES=백엔드\nEMPLOYMENT_TYPES=regular,정규직\n")), "오타")
    check("정규직" in str(error), "어느 값이 문제인지 짚어야 한다")


def test_EXCEPTION_unknown_education():
    error = check_raises(ConfigError, lambda: load_config(env_file(
        "JOB_ROLES=백엔드\nEDUCATION=학사\n")), "모르는 학력")
    check("대졸4" in str(error), "쓸 수 있는 이름을 알려야 한다")



def test_BOUNDARY_yoe_zero_is_new_grad_not_missing():
    check_equal(load_config(env_file("JOB_ROLES=백엔드\nYOE=0\n")).yoe, 0,
                "YOE=0 은 신입이지 미지정이 아니다")


def test_BOUNDARY_yoe_out_of_range():
    check_raises(ConfigError, lambda: load_config(env_file("JOB_ROLES=백엔드\nYOE=99\n")),
                 "범위 밖")
    check_raises(ConfigError, lambda: load_config(env_file("JOB_ROLES=백엔드\nYOE=-2\n")),
                 "-1 보다 작은 값")


def test_BOUNDARY_every_education_name_is_reachable():
    for name in EDUCATION_NAMES:
        config = load_config(env_file("JOB_ROLES=백엔드\nEDUCATION=%s\n" % name))
        check_equal(config.education, name, "학력 %s" % name)


def test_BOUNDARY_every_known_employment_type_is_accepted():
    for name in KNOWN_ELSEWHERE:
        config = load_config(env_file("JOB_ROLES=백엔드\nEMPLOYMENT_TYPES=%s\n" % name))
        check_equal(config.employment_types, [name], "%s 는 멈추지 않아야 한다" % name)
        check_equal(config.unsupported_employment_types, [name], "다만 못 걸었다고 남긴다")
