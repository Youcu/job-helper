"""`lib/config.py` · `_common/env.py` — `.env` 읽기.

노리는 결함 셋. 셋 다 실제로 겪었다.

1. **`C#` 이 잘리는 것.** `#` 으로 무턱대고 자르면 기술 이름이 반토막 난다.
2. **셸 환경변수가 새어 드는 것.** `load_dotenv()` 는 값을 `os.environ` 에 심는다 —
   `.env` 에 안 적은 항목이 셸에서 조용히 들어와 엉뚱한 조건으로 긁는다.
3. **사이트끼리 코드가 섞이는 것.** Wanted 의 직무 `872` 와 사람인의 `84` 는
   같은 칸에 넣을 수 없다.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from _common import env as common_env
from lib import config
from tests.helpers import check, check_equal


def write_env(text: str) -> Path:
    path = Path(tempfile.mkdtemp()) / ".env"
    path.write_text(text, encoding="utf-8")
    return path


# ─────────────────────────────── 일반 ───────────────────────────────

def test_NORMAL_reads_job_ids_and_conditions():
    path = write_env("JOB_ROLES=백엔드,웹\nYOE=0\nHOME_LOCATIONS=서울\n")
    loaded = config.load_config(path)
    check_equal(loaded.job_ids, [84, 87, 113], "직무 코드 (백엔드+웹이 세 코드로 펼쳐진다)")
    check_equal(loaded.yoe, 0, "경력")
    check_equal(loaded.home_locations, ["서울"], "근무지")


def test_NORMAL_employment_types_default_when_absent():
    path = write_env("JOB_ROLES=백엔드,웹\n")
    check_equal(config.load_config(path).employment_types,
                config.DEFAULT_EMPLOYMENT_TYPES, "안 적으면 기본값")


def test_NORMAL_employment_types_become_site_codes():
    path = write_env("JOB_ROLES=백엔드,웹\nEMPLOYMENT_TYPES=regular,contract\n")
    check_equal(config.load_config(path).employment_type_codes, ["1", "2"], "사람인 코드")


def test_NORMAL_one_role_expands_to_several_site_codes():
    """`백엔드` 하나가 이 사이트에서 코드 몇 개로 펼쳐진다.

    사이트마다 직무를 쪼갠 방식이 달라서 1:1 이 아니다 — 같은 일을 하는 공고를 다 걷는
    것이 목적이라, 이름 하나가 여러 코드가 된다.
    """
    path = write_env("JOB_ROLES=백엔드\n")
    codes = config.load_config(path).job_ids
    check(len(codes) >= 1, "적어도 하나는 나와야 한다: %r" % codes)
    check(84 in codes, "백엔드/서버개발(84)이 들어야 한다: %r" % codes)


# ─────────────────────────────── 예외 ───────────────────────────────

def test_EXCEPTION_missing_env_file_says_where():
    try:
        config.load_config(Path("/없는/경로/.env"))
    except common_env.ConfigError as error:
        check("없는" in str(error), "어느 경로인지 알려야 한다")
        return
    raise AssertionError(".env 가 없는데 그냥 돌았다")




def test_EXCEPTION_unknown_employment_type_is_rejected():
    path = write_env("JOB_ROLES=백엔드,웹\nEMPLOYMENT_TYPES=정규직\n")
    try:
        config.load_config(path)
    except common_env.ConfigError as error:
        check("쓸 수 있는 값" in str(error), "쓸 수 있는 값을 알려야 한다")
        return
    raise AssertionError("모르는 고용형태를 받았다")


def test_EXCEPTION_shell_environment_does_not_leak_in():
    # `.env` 에 줄이 없는 항목이 셸에서 새어 들면 엉뚱한 조건으로 긁는다.
    path = write_env("JOB_ROLES=백엔드,웹\n")
    os.environ["HOME_LOCATIONS"] = "부산"
    try:
        check_equal(config.load_config(path).home_locations, [],
                    ".env 에 없으면 셸 값을 쓰면 안 된다")
    finally:
        os.environ.pop("HOME_LOCATIONS", None)


def test_EXCEPTION_hash_inside_a_value_is_not_a_comment():
    # `C#,F#` 을 `#` 으로 자르면 `C` 만 남는다.
    check_equal(common_env.csv_list("C#,F#,Java"), ["C#", "F#", "Java"],
                "값 안의 # 은 주석이 아니다")
    check_equal(common_env.strip_comment("84,87  # 백엔드, 웹"), "84,87",
                "공백 뒤의 # 부터가 주석이다")


# ─────────────────────────────── 경계 ───────────────────────────────

def test_BOUNDARY_yoe_range_is_enforced():
    for value, ok in ((-1, True), (0, True), (20, True), (-2, False), (21, False)):
        path = write_env("JOB_ROLES=백엔드,웹\nYOE=%d\n" % value)
        try:
            config.load_config(path)
            check(ok, "YOE=%d 를 받으면 안 된다" % value)
        except common_env.ConfigError:
            check(not ok, "YOE=%d 를 막으면 안 된다" % value)


def test_BOUNDARY_yoe_defaults_to_all_when_blank():
    path = write_env("JOB_ROLES=백엔드,웹\nYOE=\n")
    check_equal(config.load_config(path).yoe, config.YOE_ALL, "안 적으면 전체")



def test_BOUNDARY_blank_items_are_dropped():
    check_equal(common_env.csv_list("84, ,87,"), ["84", "87"], "빈 칸은 버린다")
    check_equal(common_env.csv_list(""), [], "빈 값")
    check_equal(common_env.csv_list(None), [], "없는 값")


