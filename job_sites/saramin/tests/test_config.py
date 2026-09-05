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
    path = write_env("SARAMIN_JOB_IDS=84,87\nYOE=0\nHOME_LOCATIONS=서울\n")
    loaded = config.load_config(path)
    check_equal(loaded.job_ids, [84, 87], "직무 코드")
    check_equal(loaded.yoe, 0, "경력")
    check_equal(loaded.home_locations, ["서울"], "근무지")


def test_NORMAL_employment_types_default_when_absent():
    path = write_env("SARAMIN_JOB_IDS=84\n")
    check_equal(config.load_config(path).employment_types,
                config.DEFAULT_EMPLOYMENT_TYPES, "안 적으면 기본값")


def test_NORMAL_employment_types_become_site_codes():
    path = write_env("SARAMIN_JOB_IDS=84\nEMPLOYMENT_TYPES=regular,contract\n")
    check_equal(config.load_config(path).employment_type_codes, ["1", "2"], "사람인 코드")


def test_NORMAL_only_the_prefixed_key_is_read():
    env = {"JOB_IDS": "999", "SARAMIN_JOB_IDS": "84", "WANTED_JOB_IDS": "872"}
    check_equal(common_env.site_key(env, "saramin", "JOB_IDS"), "84", "사람인 것")
    check_equal(common_env.site_key(env, "wanted", "JOB_IDS"), "872", "Wanted 것")


# ─────────────────────────────── 예외 ───────────────────────────────

def test_EXCEPTION_missing_env_file_says_where():
    try:
        config.load_config(Path("/없는/경로/.env"))
    except common_env.ConfigError as error:
        check("없는" in str(error), "어느 경로인지 알려야 한다")
        return
    raise AssertionError(".env 가 없는데 그냥 돌았다")


def test_EXCEPTION_missing_job_ids_explains_how_to_fix():
    path = write_env("YOE=0\n")
    try:
        config.load_config(path)
    except common_env.ConfigError as error:
        check("README" in str(error), "코드표가 어디 있는지 알려야 한다")
        return
    raise AssertionError("직무 코드 없이 돌았다")


def test_EXCEPTION_non_numeric_job_id_is_rejected():
    path = write_env("SARAMIN_JOB_IDS=84,백엔드\n")
    try:
        config.load_config(path)
    except common_env.ConfigError as error:
        check("백엔드" in str(error), "어느 값이 문제인지 알려야 한다")
        return
    raise AssertionError("숫자가 아닌 코드를 받았다")


def test_EXCEPTION_unknown_employment_type_is_rejected():
    path = write_env("SARAMIN_JOB_IDS=84\nEMPLOYMENT_TYPES=정규직\n")
    try:
        config.load_config(path)
    except common_env.ConfigError as error:
        check("쓸 수 있는 값" in str(error), "쓸 수 있는 값을 알려야 한다")
        return
    raise AssertionError("모르는 고용형태를 받았다")


def test_EXCEPTION_shell_environment_does_not_leak_in():
    # `.env` 에 줄이 없는 항목이 셸에서 새어 들면 엉뚱한 조건으로 긁는다.
    path = write_env("SARAMIN_JOB_IDS=84\n")
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
        path = write_env("SARAMIN_JOB_IDS=84\nYOE=%d\n" % value)
        try:
            config.load_config(path)
            check(ok, "YOE=%d 를 받으면 안 된다" % value)
        except common_env.ConfigError:
            check(not ok, "YOE=%d 를 막으면 안 된다" % value)


def test_BOUNDARY_yoe_defaults_to_all_when_blank():
    path = write_env("SARAMIN_JOB_IDS=84\nYOE=\n")
    check_equal(config.load_config(path).yoe, config.YOE_ALL, "안 적으면 전체")


def test_BOUNDARY_duplicate_job_ids_collapse():
    path = write_env("SARAMIN_JOB_IDS=84,84,87\n")
    check_equal(config.load_config(path).job_ids, [84, 87],
                "같은 코드를 두 번 적어도 두 번 크롤하지 않는다")


def test_BOUNDARY_blank_items_are_dropped():
    check_equal(common_env.csv_list("84, ,87,"), ["84", "87"], "빈 칸은 버린다")
    check_equal(common_env.csv_list(""), [], "빈 값")
    check_equal(common_env.csv_list(None), [], "없는 값")


def test_EXCEPTION_saramin_never_falls_back_to_wanted_job_codes():
    # 결함: 짧은 `JOB_IDS` 로 되돌아가게 뒀더니, SARAMIN_JOB_IDS 를 안 적었을 때
    # 사람인이 Wanted 의 872 를 cat_kewd 로 받았다. **예외도 안 나고 결과도 나온다.**
    path = write_env("JOB_GROUP_IDS=518\nJOB_IDS=872,873\nYOE=0\n")
    try:
        config.load_config(path)
    except common_env.ConfigError as error:
        check("SARAMIN_JOB_IDS" in str(error), "무엇을 적어야 하는지 알려야 한다")
        return
    raise AssertionError("남의 사이트 직무 코드를 조용히 받았다")


def test_BOUNDARY_short_name_is_never_used_for_code_keys():
    # 짧은 이름으로 되돌아가면 남의 사이트 코드로 긁는다. 어느 사이트든 안 본다.
    env = {"JOB_IDS": "872"}
    for site in ("saramin", "wanted", "jobkorea"):
        check_equal(common_env.site_key(env, site, "JOB_IDS"), None,
                    "%s 가 접두 없는 이름을 읽으면 안 된다" % site)
