"""직무를 사이트 중립 이름으로 적는 규약.

**`_common` 의 것을 여기서 시험한다** — 여섯 사이트가 함께 쓰는 코드라 어느 한 사이트에
붙여 두면 그 사이트를 지웠을 때 시험도 같이 사라진다.

이 규약이 하는 일은 하나다. `.env` 에 `JOB_ROLES=백엔드` 라고 **한 번만** 적으면 여섯
사이트가 각자 자기 코드를 찾는다. 사이트마다 `WANTED_JOB_IDS=872`, `SARAMIN_JOB_IDS=84`
를 따로 적던 것을 없앴다.
"""
from __future__ import annotations

import json
from pathlib import Path

from _common import roles
from _common.env import ConfigError

from .helpers import check, check_equal

SITES_DIR = Path(__file__).resolve().parent.parent.parent


def _role_map(site: str) -> Path:
    return SITES_DIR / site / "tags" / ("%s_role_map.json" % site)


def test_NORMAL_known_roles_are_listed():
    names = roles.known_roles()
    check(len(names) >= 10, "표준 이름이 충분해야 한다: %d개" % len(names))
    for expected in ("백엔드", "프론트엔드", "데브옵스", "머신러닝"):
        check(expected in names, "%s 가 빠졌다" % expected)


def test_NORMAL_every_role_has_a_description():
    # 화면에 찍어 사람이 고르게 한다. 설명이 없으면 이름만 보고 짐작해야 한다.
    for name in roles.known_roles():
        check(roles.describe(name).strip(), "%s 에 설명이 없다" % name)


def test_NORMAL_aliases_are_understood():
    # 사람이 적는 말은 흔들린다. `서버`·`Backend` 라고 적어도 알아들어야 한다.
    check_equal(roles.normalize(["서버"]), ["백엔드"], "한글 별칭")
    check_equal(roles.normalize(["Backend"]), ["백엔드"], "영문 별칭")
    check_equal(roles.normalize(["BACKEND"]), ["백엔드"], "대소문자를 가리지 않는다")
    check_equal(roles.normalize(["프론트"]), ["프론트엔드"], "줄인 말")


def test_NORMAL_every_site_has_a_role_map():
    for site in ("wanted", "saramin", "jobkorea", "jobplanet", "jumpit", "pathsdog"):
        check(_role_map(site).exists(), "%s 에 대응표가 없다" % site)


def test_EXCEPTION_unknown_role_stops_the_run():
    # 조용히 빼면 조건이 느슨해지거나(다른 역할만 걷힘) 통째로 사라진다.
    error = None
    try:
        roles.normalize(["없는역할"])
    except roles.RoleError as caught:
        error = caught
    check(error is not None, "모르는 이름은 멈춰야 한다")
    check("없는역할" in str(error), "어느 이름이 문제인지 짚어야 한다")
    check("백엔드" in str(error), "쓸 수 있는 이름을 알려야 한다")


def test_EXCEPTION_role_error_is_a_config_error():
    # **엔트리포인트가 `ConfigError` 로 잡아 종료 코드 1 을 낸다.** 안 그러면 스택
    # 트레이스가 튀어나오고 오케스트레이터도 "알 수 없는 실패" 로 읽는다.
    check(issubclass(roles.RoleError, ConfigError), "ConfigError 를 물려받아야 한다")


def test_EXCEPTION_empty_job_roles_stops_the_run():
    error = None
    try:
        roles.resolve({}, _role_map("saramin"))
    except roles.RoleError as caught:
        error = caught
    check(error is not None, "비어 있으면 멈춰야 한다 — 직무 없이 돌면 전체를 긁는다")
    check("여섯 사이트가 함께" in str(error), "왜 하나만 적는지 알려야 한다")


def test_BOUNDARY_one_name_expands_to_many_codes():
    # Wanted 에는 `자바 개발자`·`파이썬 개발자` 처럼 언어별 직무가 있는데 다른 사이트엔
    # 없다. 같은 일을 하는 공고를 사이트가 어떻게 쪼개 뒀든 다 걷는 것이 목적이다.
    codes, _missing = roles.resolve({"JOB_ROLES": "백엔드"}, _role_map("wanted"))
    check(len(codes) >= 3, "Wanted 에서 백엔드는 여러 코드다: %r" % codes)
    check("872" in codes and "660" in codes, "서버·자바 개발자가 다 들어야 한다: %r" % codes)


def test_BOUNDARY_missing_role_is_reported_not_silent():
    # 사이트에 그 직무 분류가 없을 수 있다. **조용히 빠지면 왜 결과가 적은지 못 찾는다.**
    codes, missing = roles.resolve({"JOB_ROLES": "백엔드,블록체인"}, _role_map("jobplanet"))
    check(codes, "백엔드는 걸려야 한다")
    check_equal(missing, ["블록체인"], "못 건 역할을 남겨야 한다")


def test_BOUNDARY_duplicate_names_and_codes_collapse():
    check_equal(roles.normalize(["백엔드", "서버", "Backend"]), ["백엔드"],
                "같은 것을 여러 이름으로 적어도 하나다")
    codes, _ = roles.resolve({"JOB_ROLES": "백엔드,백엔드"}, _role_map("saramin"))
    check_equal(len(codes), len(set(codes)), "코드가 겹치면 안 된다: %r" % codes)


def test_BOUNDARY_order_is_kept():
    # 실행마다 코드 차례가 바뀌면 결과 순서도 바뀌어 눈으로 견주기 어렵다.
    first, _ = roles.resolve({"JOB_ROLES": "백엔드,웹"}, _role_map("saramin"))
    again, _ = roles.resolve({"JOB_ROLES": "백엔드,웹"}, _role_map("saramin"))
    check_equal(first, again, "같은 입력에 같은 차례")


def test_BOUNDARY_blank_and_spaced_names():
    check_equal(roles.normalize(["  백엔드  ", "", "  "]), ["백엔드"], "공백은 다듬는다")
    codes, _ = roles.resolve({"JOB_ROLES": " 백엔드 , 웹 "}, _role_map("saramin"))
    check(codes, "콤마 둘레 공백도 받아야 한다: %r" % codes)


def test_BOUNDARY_every_mapped_code_exists_in_the_site_table():
    """대응표의 코드가 **그 사이트 코드표에 실제로 있는가.**

    오타 하나면 그 역할이 조용히 안 걸린다 — 결과가 적게 나오는데 원인이 안 보인다.
    """
    tables = {
        "saramin": _codes_from(SITES_DIR / "saramin/tags/saramin_job_category.json",
                               lambda d: [c["code"] for c in d["categories"]]),
        "jobkorea": _codes_from(SITES_DIR / "jobkorea/tags/jobkorea_duty.json",
                                lambda d: [s["code"] for g in d["groups"] for s in g["sub"]]),
        "jobplanet": _codes_from(SITES_DIR / "jobplanet/tags/jobplanet_occupation.json",
                                 lambda d: [str(s["code"]) for g in d["groups"] for s in g["sub"]]),
        "jumpit": _codes_from(SITES_DIR / "jumpit/tags/jumpit_job_category.json",
                              lambda d: [str(i["code"]) for i in d["categories"]]),
        "pathsdog": _codes_from(SITES_DIR / "pathsdog/tags/pathsdog_role.json",
                                lambda d: [r["name"] for r in d["roles"]]),
    }
    for site, known in tables.items():
        book = roles.load_role_map(_role_map(site))
        for role, codes in book.items():
            for code in codes:
                check(str(code) in known,
                      "%s 대응표의 %s → %r 가 그 사이트 코드표에 없다" % (site, role, code))


def _codes_from(path: Path, pick) -> set[str]:
    return {str(c) for c in pick(json.loads(path.read_text(encoding="utf-8")))}


def test_BOUNDARY_role_map_covers_only_known_names():
    # 대응표에 표준 목록에 없는 이름이 있으면 영영 안 쓰인다 — 오타이거나 지워야 할 것이다.
    known = set(roles.known_roles())
    for site in ("wanted", "saramin", "jobkorea", "jobplanet", "jumpit", "pathsdog"):
        for name in roles.load_role_map(_role_map(site)):
            check(name in known, "%s 대응표의 %r 가 표준 이름에 없다" % (site, name))
