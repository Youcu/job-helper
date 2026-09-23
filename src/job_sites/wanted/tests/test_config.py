""".env 읽기와 검증."""
from __future__ import annotations

import tempfile
from pathlib import Path

from lib.config import Config, ConfigError, load_config
from tests.helpers import assert_raises, write_env

# 직무는 이제 여섯 사이트가 함께 쓰는 `JOB_ROLES` 하나다. 다른 항목을 보는
# 테스트도 이것이 있어야 설정 읽기가 그 항목까지 간다.
ROLES = "JOB_ROLES=백엔드\n"


def test_BOUNDARY_duplicate_config_values_collapse():
    """`백엔드` 하나가 여러 직무로 펼쳐지고, 직군은 그 직무들에서 유도된다.

    Wanted 에는 `자바 개발자`·`파이썬 개발자` 처럼 언어별 직무가 있어 한 이름이
    코드 여섯이 된다. 직군(518=개발)은 그 직무들이 속한 곳이라 사람이 또 적을
    이유가 없다 — 적게 하면 직무와 어긋날 여지만 생긴다.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        env = write_env(Path(d), "JOB_ROLES=백엔드\n")
        cfg = load_config(env)
        # 직군은 이제 **직무에서 유도한다** — 사람이 따로 안 적는다.
        assert cfg.job_group_ids == [518]
        assert cfg.job_ids == [872, 660, 899, 895], cfg.job_ids


def test_EXCEPTION_env_does_not_leak_from_shell_environment():
    """결함: `.env` 에 줄이 없으면 셸 환경변수가 조용히 조건이 됐다.

    `load_dotenv()` 가 값을 `os.environ` 에 심어서, 근무지를 안 적었는데 셸에
    `HOME_LOCATIONS=부산` 이 있으면 부산 공고를 긁었다. 조건이 파일에 안 적힌 채로
    결과가 달라지는 건 재현이 안 된다는 뜻이다.
    """
    import os
    import tempfile
    saved = {k: os.environ.get(k) for k in ("TECH_STACKS", "HOME_LOCATIONS", "YOE")}
    try:
        os.environ["TECH_STACKS"] = "셸에서_새어들어온_값"
        os.environ["HOME_LOCATIONS"] = "부산"
        os.environ["YOE"] = "9"
        with tempfile.TemporaryDirectory() as d:
            cfg = load_config(write_env(Path(d), ROLES))
        assert cfg.tech_stacks == [], cfg.tech_stacks
        assert cfg.home_locations == [], cfg.home_locations
        assert cfg.yoe == -1, cfg.yoe            # .env 에 없으면 기본값
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_EXCEPTION_env_empty_value_does_not_swallow_comment():
    """결함: 값이 비면 python-dotenv 가 다음 줄 주석을 값으로 읽어 온 적이 있다."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        env = write_env(Path(d), ROLES + "# 희망근무지\nHOME_LOCATIONS=\n")
        assert load_config(env).home_locations == []


def test_EXCEPTION_env_inline_comment_after_space_is_still_stripped():
    """값 뒤에 공백을 두고 붙인 주석은 여전히 걷어내야 한다 (dotenv 관례)."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        env = write_env(Path(d), ROLES + "TECH_STACKS=Python,Java   # 보유 스택\n")
        assert load_config(env).tech_stacks == ["Python", "Java"]


def test_EXCEPTION_env_missing_or_invalid():
    import tempfile
    assert_raises(ConfigError, load_config, Path("/tmp/절대_없는_파일.env"))
    with tempfile.TemporaryDirectory() as d:
        # 직무가 없으면 무엇을 긁을지 알 수 없다 — 조용히 전체를 긁으면 안 된다
        assert_raises(ConfigError, load_config, write_env(Path(d), ""))
        # 모르는 역할 이름을 조용히 빼면 조건이 통째로 사라진다
        assert_raises(ConfigError, load_config,
                      write_env(Path(d), "JOB_ROLES=없는역할\n"))
        # 모르는 고용형태를 조용히 무시하면 조건과 다른 결과가 나온다
        assert_raises(ConfigError, load_config,
                      write_env(Path(d), ROLES + "EMPLOYMENT_TYPES=정규직\n"))
        # 경력이 정수가 아니거나 범위 밖
        assert_raises(ConfigError, load_config, write_env(Path(d), ROLES + "YOE=신입\n"))
        assert_raises(ConfigError, load_config, write_env(Path(d), ROLES + "YOE=99\n"))
        assert_raises(ConfigError, load_config, write_env(Path(d), ROLES + "YOE=-2\n"))


def test_EXCEPTION_env_reads_are_independent_of_each_other():
    """설정을 두 번 읽으면 앞의 값이 뒤에 남으면 안 된다."""
    import tempfile
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        a = load_config(write_env(Path(d1), ROLES + "TECH_STACKS=Python\nYOE=3\n"))
        b = load_config(write_env(Path(d2), ROLES))
        assert a.tech_stacks == ["Python"] and a.yoe == 3
        assert b.tech_stacks == [] and b.yoe == -1, (b.tech_stacks, b.yoe)


def test_EXCEPTION_env_value_containing_hash_is_not_truncated(tmp=Path("/tmp")):
    """결함: `#` 을 무조건 주석으로 봐서 `TECH_STACKS=C#,Java` 가 `['C']` 가 됐다.

    C# · F# 은 흔한 스택이다. 값 하나가 아니라 뒤의 목록 전체가 사라졌다.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        env = write_env(Path(d), ROLES + "TECH_STACKS=C#,Java,F#\n")
        cfg = load_config(env)
        assert cfg.tech_stacks == ["C#", "Java", "F#"], cfg.tech_stacks


def test_NORMAL_employment_type_keys_expand():
    """`.env` 에는 짧게 쓰고 API 에는 긴 키로 보낸다. 여기가 틀리면 필터가 안 걸린다."""
    cfg = Config(job_group_ids=[518], employment_types=["regular", "intern"])
    assert cfg.employment_type_keys == [
        "job.employment_type.regular", "job.employment_type.intern",
    ]
