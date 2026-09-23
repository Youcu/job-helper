"""`.env` 읽기.

여기서 가장 중요한 것은 **`JOBKOREA_` 접두사가 없는 이름으로 물러서지 않는다**는 것이다.
`JOB_IDS` 로 물러서면 사람인 코드(`84`)로 잡코리아를 긁고, 그건 코드표에 없는 값이라
멈추기라도 하지만, 우연히 겹치는 숫자였다면 **엉뚱한 직무를 조용히 긁는다.**
"""
from __future__ import annotations

from _common.env import ConfigError
from lib.config import (DEFAULT_EMPLOYMENT_TYPES, EDUCATION_CODES,
                        EMPLOYMENT_TYPE_CODES, YOE_ALL, load_config)

from .helpers import check, check_equal, check_raises


def _write(tmp_path, text: str):
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def _env(text: str):
    import tempfile
    from pathlib import Path
    directory = Path(tempfile.mkdtemp())
    return _write(directory, text)


def test_NORMAL_reads_every_field():
    config = load_config(_env(
        "JOB_ROLES=백엔드\n"
        "EMPLOYMENT_TYPES=regular,intern\n"
        "YOE=3\n"
        "EDUCATION=대졸4\n"
        "HOME_LOCATIONS=서울,성남시\n"
        "TECH_STACKS=Python,Django\n"
        "HOPE_ANNUAL_SALARY=3300\n"))
    check_equal(config.job_ids, [1000229], "직무 코드")
    check_equal(config.employment_types, ["regular", "intern"], "고용형태")
    check_equal(config.yoe, 3, "년차")
    check_equal(config.education, "대졸4", "학력")
    check_equal(config.home_locations, ["서울", "성남시"], "근무지")
    check_equal(config.employment_type_codes, ["1", "3"], "고용형태 코드")


def test_NORMAL_defaults_when_optional_fields_missing():
    config = load_config(_env("JOB_ROLES=백엔드\n"))
    check_equal(config.employment_types, DEFAULT_EMPLOYMENT_TYPES, "고용형태 기본값")
    check_equal(config.yoe, YOE_ALL, "년차 기본값은 전체")
    check_equal(config.education, "", "학력 기본값은 조건 없음")
    check_equal(config.home_locations, [], "근무지 기본값은 전국")


def test_NORMAL_strips_inline_comment():
    config = load_config(_env("JOB_ROLES=백엔드\nEDUCATION=대졸4   # 4년제\n"))
    check_equal(config.education, "대졸4", "주석을 떼고 읽어야 한다")



def test_EXCEPTION_unknown_employment_type():
    error = check_raises(ConfigError, lambda: load_config(_env(
        "JOB_ROLES=백엔드\nEMPLOYMENT_TYPES=regular,정규직\n")),
        "모르는 고용형태")
    check("정규직" in str(error), "어느 값이 문제인지 짚어야 한다")
    check("regular" in str(error), "쓸 수 있는 값을 알려야 한다")


def test_EXCEPTION_unknown_education():
    error = check_raises(ConfigError, lambda: load_config(_env(
        "JOB_ROLES=백엔드\nEDUCATION=학사\n")), "모르는 학력")
    check("대졸4" in str(error), "쓸 수 있는 이름을 알려야 한다")



def test_BOUNDARY_yoe_zero_is_new_grad_not_missing():
    # `0` 은 거짓값이라 `or` 로 처리하면 조용히 전체(-1)가 된다.
    check_equal(load_config(_env("JOB_ROLES=백엔드\nYOE=0\n")).yoe, 0,
                "YOE=0 은 신입이지 미지정이 아니다")


def test_BOUNDARY_yoe_out_of_range():
    check_raises(ConfigError,
                 lambda: load_config(_env("JOB_ROLES=백엔드\nYOE=99\n")),
                 "범위 밖 년차")
    check_raises(ConfigError,
                 lambda: load_config(_env("JOB_ROLES=백엔드\nYOE=-2\n")),
                 "-1 보다 작은 값")


def test_BOUNDARY_empty_values_are_not_conditions():
    config = load_config(_env(
        "JOB_ROLES=백엔드\nEDUCATION=\nHOME_LOCATIONS=\nEMPLOYMENT_TYPES=\n"))
    check_equal(config.education, "", "빈 학력")
    check_equal(config.home_locations, [], "빈 근무지")
    check_equal(config.employment_types, DEFAULT_EMPLOYMENT_TYPES,
                "고용형태를 비우면 기본값으로 돌아간다")


def test_BOUNDARY_every_code_table_entry_is_reachable():
    # 코드표에 있는 이름은 전부 `.env` 에 적을 수 있어야 한다.
    for name in EMPLOYMENT_TYPE_CODES:
        config = load_config(_env("JOB_ROLES=백엔드\nEMPLOYMENT_TYPES=%s\n" % name))
        check_equal(config.employment_types, [name], "고용형태 %s" % name)
    for name in EDUCATION_CODES:
        config = load_config(_env("JOB_ROLES=백엔드\nEDUCATION=%s\n" % name))
        check_equal(config.education, name, "학력 %s" % name)
