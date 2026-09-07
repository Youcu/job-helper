"""이미지 판독 단계의 설정.

`.env` 는 **여섯 사이트가 함께 쓰는 검색 조건** 한 벌이고 이 셋은 성격이 다르다.
그래서 **없어도 도는 쪽**으로 둔다 — 조건은 없으면 멈추지만(D-08), 이건 기본값이 있다.
"""
from __future__ import annotations

from _common.env import ConfigError
from image_process import config as cfg

from .helpers import check, check_equal, temp_dir


def _env(text: str):
    path = temp_dir() / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def test_NORMAL_defaults_when_env_is_empty():
    got = cfg.load_config(_env(""))
    check_equal(got.model, "sonnet", "기본 모델")
    check_equal(got.workers, 4, "기본 동시 수")
    check_equal(got.timeout, 300, "기본 시간제한")


def test_NORMAL_env_overrides_defaults():
    got = cfg.load_config(_env("IMAGE_MODEL=opus\nCLAUDE_WORKER=8\nIMAGE_TIMEOUT=120\n"))
    check_equal(got.model, "opus", "모델")
    check_equal(got.workers, 8, "동시 수")
    check_equal(got.timeout, 120, "시간제한")


def test_EXCEPTION_workers_must_be_a_number():
    error = None
    try:
        cfg.load_config(_env("CLAUDE_WORKER=넷\n"))
    except ConfigError as caught:
        error = caught
    check(error is not None, "숫자가 아니면 멈춰야 한다")
    check("CLAUDE_WORKER" in str(error), "어느 항목인지 짚어야 한다: %s" % error)


def test_BOUNDARY_workers_out_of_range_stops_the_run():
    # 0 이면 아무것도 안 돌고, 너무 크면 프로세스가 그만큼 뜨고 막힐 때 한꺼번에 실패한다.
    for value in ("0", "65"):
        error = None
        try:
            cfg.load_config(_env("CLAUDE_WORKER=%s\n" % value))
        except ConfigError as caught:
            error = caught
        check(error is not None, "%s 는 막아야 한다" % value)


def test_BOUNDARY_missing_env_file_uses_defaults():
    # `.env` 가 없어도 이 단계는 돈다. 검색 조건이 아니라 운영 손잡이다.
    got = cfg.load_config(temp_dir() / "없는파일")
    check_equal(got.model, "sonnet", "기본값으로 돈다")


def test_BOUNDARY_comment_after_value_is_stripped():
    got = cfg.load_config(_env("IMAGE_MODEL=opus  # 잠깐 바꿔 봄\n"))
    check_equal(got.model, "opus", "값 옆 주석은 떼어 낸다")
