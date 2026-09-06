"""조건 → MCP `search_jobs` 인자.

**서버가 거르는 것과 우리가 거르는 것이 갈린다.** 근무지는 도구에 파라미터가 아예 없고,
고용형태는 값 하나만 받아서 `정규직,인턴` 중 하나를 잃는다 — 둘 다 받은 뒤 거른다.
"""
from __future__ import annotations

from _common.env import ConfigError
from lib.config import Config
from lib.filters import (build_arguments, known_roles, role_values, unknown_roles,
                         wanted_employments, wanted_locations)

from .helpers import check, check_equal, check_raises


def test_NORMAL_roles_go_to_skills():
    args = build_arguments(Config(job_ids=["Backend", "Fullstack"]))
    check_equal(args["skills"], ["Backend", "Fullstack"], "역할이 skills 로 간다")


def test_NORMAL_experience_is_translated():
    check_equal(build_arguments(Config(job_ids=["Backend"], yoe=0))["experience_filter"],
                "신입", "0년차 → 신입")
    check_equal(build_arguments(Config(job_ids=["Backend"], yoe=7))["experience_filter"],
                "시니어", "7년차 → 시니어")


def test_EXCEPTION_unknown_experience_value_stops():
    class Odd(Config):
        @property
        def experience_filter(self):
            return "초짜"
    check_raises(ConfigError, lambda: build_arguments(Odd(job_ids=["Backend"])),
                 "서버가 모르는 경력 값")


def test_BOUNDARY_unknown_role_is_allowed_but_reported():
    # 이 사이트의 skills 는 닫힌 코드표가 아니다 — 관측해서 모은 목록일 뿐이라
    # 없는 이름이라고 멈추면 멀쩡한 조건을 못 쓴다. 대신 눈에 띄게 알린다.
    args = build_arguments(Config(job_ids=["Backend", "쿠버네티스마스터"]))
    check_equal(args["skills"], ["Backend", "쿠버네티스마스터"], "막지 않는다")
    check_equal(unknown_roles(["Backend", "쿠버네티스마스터"]), ["쿠버네티스마스터"],
                "코드표에 없는 것만 알린다")


def test_BOUNDARY_known_roles_are_not_reported():
    check_equal(unknown_roles(known_roles()[:4]), [], "코드표에 있는 것은 안 알린다")
    check_equal(unknown_roles(["backend"]), [], "대소문자는 가리지 않는다")


def test_BOUNDARY_blank_and_duplicate_roles():
    check_equal(role_values(["Backend", "  ", "Backend", " Frontend "]),
                ["Backend", "Frontend"], "빈 값과 중복은 뺀다")
    check("skills" not in build_arguments(Config(job_ids=["  "])), "전부 비면 안 싣는다")


def test_BOUNDARY_employment_never_becomes_an_argument():
    # 서버가 값 하나만 받아서 `정규직,인턴` 중 하나를 잃는다 (실측: 조건 없이 29건 · 정규직 28건).
    args = build_arguments(Config(job_ids=["Backend"],
                                  employment_types=["regular", "intern"]))
    check("employment_type" not in args, "서버에 안 보낸다: %r" % args)
    check_equal(wanted_employments(Config(employment_types=["regular", "intern"])),
                ["정규직", "인턴"], "우리가 거를 목록으로 남긴다")


def test_BOUNDARY_locations_are_kept_as_names():
    # 서버에 못 보내므로 코드로 옮기지 않는다 — 근무지 글과 견줄 이름 그대로다.
    check_equal(wanted_locations(["서울", "판교"]), ["서울", "판교"], "이름 그대로")
    check_equal(wanted_locations(["  서울  "]), ["서울"], "공백은 다듬는다")
    check_equal(wanted_locations(["서울", "서울"]), ["서울"], "중복은 뺀다")
    check("locationTag" not in build_arguments(Config(job_ids=["Backend"])),
          "서버 인자에는 지역이 없다")


def test_BOUNDARY_nationwide_means_no_condition():
    check_equal(wanted_locations(["전국"]), [], "전국은 안 거른다")
    check_equal(wanted_locations([]), [], "비어 있어도 안 거른다")


def test_BOUNDARY_education_and_tech_never_become_arguments():
    args = build_arguments(Config(job_ids=["Backend"], education="대졸4",
                                  tech_stacks=["Python", "Django"]))
    check_equal(sorted(args), ["skills"], "그 둘은 안 실린다: %r" % args)
