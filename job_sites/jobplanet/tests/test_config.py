"""`.env` 읽기.

이 사이트는 **같은 `.env` 항목이 다르게 쓰인다.** 학력은 안 걸고, 인턴은 못 걸고,
근무지는 시도까지만 건다. 그래서 여기서 볼 것은 "무시하되 조용하지 않은가" 다 —
`unsupported_employment_types` 가 무엇을 못 걸었는지 남겨야 실행 화면에 찍을 수 있다.
"""
from __future__ import annotations

from _common.env import ConfigError
from lib.config import (DEFAULT_EMPLOYMENT_TYPES, EDUCATION_CODES,
                        EMPLOYMENT_TYPE_CODES, YOE_ALL, load_config)

from .helpers import check, check_equal, check_raises, env_file


def test_NORMAL_reads_every_field():
    config = load_config(env_file(
        "JOBPLANET_JOB_IDS=11904,11905\n"
        "EMPLOYMENT_TYPES=regular\n"
        "YOE=3\n"
        "EDUCATION=대졸4\n"
        "HOME_LOCATIONS=서울,성남시\n"
        "TECH_STACKS=Python,Django\n"
        "HOPE_ANNUAL_SALARY=3300\n"))
    check_equal(config.job_ids, [11904, 11905], "직무 코드")
    check_equal(config.yoe, 3, "년차")
    check_equal(config.education, "대졸4", "학력은 읽기는 한다 (거는 것은 filters 가 안 한다)")
    check_equal(config.home_locations, ["서울", "성남시"], "근무지")
    check_equal(config.employment_type_codes, ["3"], "정규직 코드")


def test_NORMAL_defaults():
    config = load_config(env_file("JOBPLANET_JOB_IDS=11904\n"))
    check_equal(config.employment_types, DEFAULT_EMPLOYMENT_TYPES, "기본은 정규직")
    check_equal(config.yoe, YOE_ALL, "년차 기본값은 전체")
    check_equal(config.education, "", "학력 기본값 없음")


def test_NORMAL_intern_is_accepted_but_reported_as_unsupported():
    # 인턴은 멀쩡한 값이라 멈추면 안 된다. 다만 **못 걸었다는 사실을 남겨야** 한다 —
    # 조용히 무시하면 다른 사이트와 결과가 어긋난 이유를 나중에 못 찾는다.
    config = load_config(env_file(
        "JOBPLANET_JOB_IDS=11904\nEMPLOYMENT_TYPES=regular,intern\n"))
    check_equal(config.employment_type_codes, ["3"], "코드는 정규직만")
    check_equal(config.unsupported_employment_types, ["intern"], "못 건 것을 남긴다")


def test_EXCEPTION_job_ids_required():
    error = check_raises(ConfigError, lambda: load_config(env_file("YOE=0\n")),
                         "직무 코드 없이 돌면 전체를 긁는다")
    check("JOBPLANET_JOB_IDS" in str(error), "무엇을 채워야 하는지 이름을 알려야 한다")
    check("중분류" in str(error), "대분류 함정을 미리 알려야 한다")


def test_EXCEPTION_does_not_fall_back_to_unprefixed_name():
    # 결함이 될 뻔한 곳: `JOB_IDS` 로 물러서면 남의 사이트 코드로 잡플래닛을 긁는다.
    check_raises(ConfigError, lambda: load_config(env_file("JOB_IDS=11904\n")),
                 "접두사 없는 JOB_IDS 는 잡플래닛 것이 아니다")


def test_EXCEPTION_typo_in_employment_type_stops():
    # `intern` 은 통과시키지만 오타는 멈춰야 한다. 둘을 가르는 것이 이 검사의 전부다.
    error = check_raises(ConfigError, lambda: load_config(env_file(
        "JOBPLANET_JOB_IDS=11904\nEMPLOYMENT_TYPES=regular,정규직\n")), "오타")
    check("정규직" in str(error), "어느 값이 문제인지 짚어야 한다")


def test_EXCEPTION_unknown_education():
    error = check_raises(ConfigError, lambda: load_config(env_file(
        "JOBPLANET_JOB_IDS=11904\nEDUCATION=학사\n")), "모르는 학력")
    check("대졸4" in str(error), "쓸 수 있는 이름을 알려야 한다")


def test_BOUNDARY_yoe_zero_is_new_grad_not_missing():
    check_equal(load_config(env_file("JOBPLANET_JOB_IDS=11904\nYOE=0\n")).yoe, 0,
                "YOE=0 은 신입이지 미지정이 아니다")


def test_BOUNDARY_yoe_out_of_range():
    check_raises(ConfigError, lambda: load_config(env_file(
        "JOBPLANET_JOB_IDS=11904\nYOE=99\n")), "범위 밖 (코드표 위쪽 끝이 11)")
    check_raises(ConfigError, lambda: load_config(env_file(
        "JOBPLANET_JOB_IDS=11904\nYOE=-2\n")), "-1 보다 작은 값")


def test_BOUNDARY_every_code_table_entry_is_reachable():
    for name in EMPLOYMENT_TYPE_CODES:
        config = load_config(env_file(
            "JOBPLANET_JOB_IDS=11904\nEMPLOYMENT_TYPES=%s\n" % name))
        check_equal(config.employment_types, [name], "고용형태 %s" % name)
        check_equal(config.unsupported_employment_types, [], "%s 는 걸 수 있다" % name)
    for name in EDUCATION_CODES:
        config = load_config(env_file("JOBPLANET_JOB_IDS=11904\nEDUCATION=%s\n" % name))
        check_equal(config.education, name, "학력 %s" % name)


def test_BOUNDARY_all_employment_types_unsupported():
    config = load_config(env_file(
        "JOBPLANET_JOB_IDS=11904\nEMPLOYMENT_TYPES=intern,freelance\n"))
    check_equal(config.employment_type_codes, [], "걸 수 있는 것이 하나도 없다")
    check_equal(config.unsupported_employment_types, ["intern", "freelance"], "둘 다 남긴다")
