"""`lib/filters.py` — 수집 조건을 사람인 파라미터로.

**여기서 틀리면 조용히 엉뚱한 것을 긁는다.** 실측에서 걸린 세 함정을 그대로 굳힌다.

| 함정 | 무슨 일이 나는가 |
|---|---|
| 구 코드를 `loc_mcd` 에 | **0건**. 결과가 비어서 티라도 난다 |
| `exp_min` 단독 | 에러 없이 **전체**. 필터가 먹은 줄 안다 |
| `exp_cd=99` | 그것도 **전체** |

뒤의 둘이 더 나쁘다. 조건을 좁혔는데 안 좁혀지고, 결과가 늘어나는 방향이라 사람이
알아채기 어렵다.
"""
from __future__ import annotations

from lib import filters
from lib.config import Config
from tests.helpers import check, check_equal


# ─────────────────────────────── 일반 ───────────────────────────────

def test_NORMAL_province_uses_loc_mcd():
    check_equal(filters.resolve_locations(["서울"]), {"loc_mcd": "101000"},
                "시도 전체는 loc_mcd 다")


def test_NORMAL_district_uses_loc_bcd():
    # 실측: 구 코드를 loc_mcd 에 넣으면 0건이 나온다.
    check_equal(filters.resolve_locations(["강남구"]), {"loc_bcd": "101010"},
                "구·시는 loc_bcd 다")


def test_NORMAL_province_spelling_variants():
    for spelling in ("서울", "서울시", "서울특별시"):
        check_equal(filters.resolve_locations([spelling]), {"loc_mcd": "101000"},
                    "%s 도 받아야 한다" % spelling)


def test_NORMAL_new_graduate_uses_exp_cd_only():
    check_equal(filters.experience_params(0), {"exp_cd": "1"}, "신입")


def test_NORMAL_experienced_needs_exp_cd_with_exp_min():
    # 결함이 될 뻔한 곳: exp_min 만 주면 사람인이 통째로 무시한다.
    params = filters.experience_params(3)
    check_equal(params.get("exp_cd"), "2", "exp_cd 를 함께 줘야 exp_min 이 먹는다")
    check_equal(params.get("exp_min"), "3", "연차")


def test_NORMAL_search_params_carry_job_codes():
    config = Config(job_ids=[84, 87], yoe=0, home_locations=["서울"])
    params = filters.build_search_params(config)
    check_equal(params["cat_kewd"], "84,87", "직무 코드 — 콤마 하나로 잇는다")
    check_equal(params["loc_mcd"], "101000", "지역")
    check_equal(params["exp_cd"], "1", "경력")


# ─────────────────────────────── 예외 ───────────────────────────────

def test_EXCEPTION_unknown_place_stops_instead_of_widening():
    # 조용히 빼면 조건이 느슨해져 전국을 긁는다. 결과가 늘어나는 방향이라
    # 사람이 알아채기 어렵다 — 그래서 멈춘다.
    try:
        filters.resolve_locations(["없는동네"])
    except filters.LocationError as error:
        check("없는동네" in str(error), "어느 이름이 문제인지 알려야 한다")
        return
    raise AssertionError("모르는 근무지를 조용히 넘겼다")


def test_EXCEPTION_ambiguous_district_needs_a_province():
    # `중구` 는 대구·부산 등 여러 시도에 있다. 아무거나 고르면 엉뚱한 지역을 긁는다.
    check("중구" in filters.ambiguous_names(), "중구는 여러 시도에 있다")
    try:
        filters.resolve_locations(["중구"])
    except filters.LocationError as error:
        check("시도를 붙여" in str(error), "어떻게 고치는지 알려야 한다")
        return
    raise AssertionError("여러 시도에 있는 이름을 임의로 골랐다")


def test_EXCEPTION_province_prefixed_district_resolves():
    check_equal(filters.resolve_locations(["대구 중구"]), {"loc_bcd": "104080"},
                "시도를 붙이면 정해진다")


def test_EXCEPTION_nationwide_means_no_location_filter():
    # `전국`(117000)은 "전체" 가 아니라 근무지가 "전국" 이라 적힌 공고 버킷이다.
    # 그걸로 좁히면 전체 1,842건 중 10건만 나온다.
    check_equal(filters.resolve_locations(["전국"]), {},
                "전국은 파라미터를 빼는 것이지 버킷 하나가 아니다")


def test_EXCEPTION_empty_locations_mean_everywhere():
    check_equal(filters.resolve_locations([]), {}, "안 적으면 전국이다")


# ─────────────────────────────── 경계 ───────────────────────────────

def test_BOUNDARY_all_experience_sends_no_experience_params():
    check_equal(filters.experience_params(-1), {}, "전체는 파라미터를 안 보낸다")


def test_BOUNDARY_exp_min_never_appears_without_exp_cd():
    for yoe in range(-1, 21):
        params = filters.experience_params(yoe)
        if "exp_min" in params:
            check_equal(params.get("exp_cd"), "2",
                        "YOE=%d 에서 exp_min 이 홀로 나갔다" % yoe)


def test_BOUNDARY_exp_cd_99_is_never_used():
    # 코드표에 `99=경력무관` 이 있지만 그건 필터가 아니다 — 기준선과 같은 수가 나온다.
    for yoe in range(-1, 21):
        check(filters.experience_params(yoe).get("exp_cd") != "99",
              "YOE=%d 에서 필터 구실을 못 하는 99 를 썼다" % yoe)


def test_BOUNDARY_mixed_levels_go_to_their_own_parameters():
    resolved = filters.resolve_locations(["서울", "성남시"])
    check_equal(resolved["loc_mcd"], "101000", "시도는 loc_mcd")
    check(resolved["loc_bcd"].startswith("102180"), "시·구는 loc_bcd: %r" % resolved["loc_bcd"])


def test_BOUNDARY_duplicate_places_collapse():
    check_equal(filters.resolve_locations(["서울", "서울특별시", "서울시"]),
                {"loc_mcd": "101000"}, "같은 곳을 여러 표기로 적어도 하나다")


def test_BOUNDARY_whitespace_in_place_names_is_tolerated():
    check_equal(filters.resolve_locations(["  경기  성남시  "]),
                {"loc_bcd": "102180"}, "앞뒤와 사이 공백을 다듬는다")


def test_BOUNDARY_nationwide_wins_over_other_places():
    # `전국` 을 적었다면 뜻은 "전부" 다. 다른 지역과 같이 적혀도 좁히면 안 된다.
    check_equal(filters.resolve_locations(["서울", "전국"]), {},
                "전국이 섞이면 지역 조건을 걸지 않는다")


def test_BOUNDARY_multiple_values_are_joined_with_one_comma():
    # **실측**: 같은 이름을 여러 번 보내면 사람인은 마지막 값만 쓴다.
    #   cat_kewd=84            1,854건
    #   cat_kewd=87            1,507건
    #   cat_kewd=84&cat_kewd=87  1,507건  ← 84 가 통째로 버려졌다
    #   cat_kewd=84,87         2,552건  ← 이게 합집합이다
    # 조건을 넓혔는데 결과가 줄고 예외도 안 난다. 총계가 이상해서야 알아챘다.
    config = Config(job_ids=[84, 87], yoe=-1,
                    home_locations=["강남구", "서초구"], employment_types=["regular", "intern"])
    params = filters.build_search_params(config)
    for key in ("cat_kewd", "loc_bcd", "job_type"):
        check(isinstance(params[key], str),
              "%s 는 목록이 아니라 콤마로 이은 문자열이어야 한다: %r" % (key, params[key]))
        check("," in params[key], "%s 에 값 둘이 다 들어가야 한다: %r" % (key, params[key]))


def test_BOUNDARY_no_parameter_value_is_ever_a_list():
    # 목록이 하나라도 남아 있으면 client 가 반복 파라미터로 펼쳐 조용히 값을 잃는다.
    config = Config(job_ids=[84, 87], yoe=3,
                    home_locations=["서울", "부산", "강남구"],
                    employment_types=["regular", "contract", "intern"])
    for key, value in filters.build_search_params(config).items():
        check(not isinstance(value, (list, tuple)),
              "%s 가 목록이다: %r" % (key, value))


# ────────────────── 학력 · 경력무관 ──────────────────

def test_NORMAL_education_needs_both_min_and_max():
    # `edu_min` 만 주면 "4년제 이상"(869건), `edu_max` 만 주면 "4년제 이하"(1,500건)라
    # 뜻이 달라진다. 둘을 같이 줘야 그 학력으로 좁혀진다(846건).
    check_equal(filters.education_params("대졸4"), {"edu_min": "8", "edu_max": "11"},
                "딱 그 학력을 요구하는 공고")


def test_NORMAL_education_any_uses_its_own_parameter():
    check_equal(filters.education_params("무관"), {"edu_none": "y"},
                "학력무관은 범위가 아니라 별도 파라미터다")


def test_BOUNDARY_education_min_and_max_never_share_a_number():
    # 코드 9 가 min 에선 석사 이상, max 에선 고졸 이하다. 한 표를 돌려쓰면 안 된다.
    for level in filters.EDUCATION_CODES:
        low, high = filters.EDUCATION_CODES[level]
        check(low != high, "%s 의 min/max 가 같은 번호다 — 표를 돌려쓴 것이다" % level)


def test_EXCEPTION_unknown_education_is_rejected():
    try:
        filters.education_params("초졸")
    except Exception as error:
        check("쓸 수 있는 값" in str(error), "쓸 수 있는 값을 알려야 한다")
        return
    raise AssertionError("모르는 학력을 조용히 받았다")


def test_EXCEPTION_blank_education_means_no_condition():
    for value in ("", None, "   "):
        check_equal(filters.education_params(value), {}, "안 적으면 조건을 안 건다")


# ────────────────── 시를 고르면 구까지 ──────────────────

def test_NORMAL_choosing_a_city_includes_its_districts():
    # **시 코드는 구를 포함하지 않는다.** `성남시`(102180)와 `성남시 분당구`(102190)가
    # 별개라, 시만 보내면 구에 등록된 공고를 놓친다 — 실측 133건 → 160건.
    codes = filters.resolve_locations(["성남시"])["loc_bcd"].split(",")
    check("102180" in codes, "시 자체")
    for district in ("102190", "102200", "102210"):
        check(district in codes, "%s (분당·수정·중원) 이 빠졌다: %r" % (district, codes))


def test_NORMAL_choosing_a_district_stays_narrow():
    # 구를 콕 집었으면 시 전체로 넓히면 안 된다.
    check_equal(filters.resolve_locations(["성남시 분당구"]), {"loc_bcd": "102190"},
                "고른 구만")


def test_BOUNDARY_city_without_districts_is_unchanged():
    # 구가 없는 시도 있다. 그때는 시 코드 하나만 나가야 한다.
    codes = filters.resolve_locations(["김포시"])["loc_bcd"].split(",")
    check_equal(len(codes), 1, "구가 없으면 하나다: %r" % codes)


def test_BOUNDARY_seoul_is_a_province_not_a_city():
    # 서울은 시도(loc_mcd)라 구 확장이 붙으면 안 된다 — 이미 전체를 뜻한다.
    check_equal(filters.resolve_locations(["서울"]), {"loc_mcd": "101000"},
                "시도는 그 자체로 전체다")


def test_BOUNDARY_expansion_does_not_duplicate_codes():
    # 시와 그 구를 같이 적어도 코드가 두 번 나가면 안 된다.
    codes = filters.resolve_locations(["성남시", "성남시 분당구"])["loc_bcd"].split(",")
    check_equal(len(codes), len(set(codes)), "중복된 코드: %r" % codes)


def test_BOUNDARY_new_graduate_search_already_covers_career_free():
    # **실측** — `exp_cd=1`(신입) 160건의 속: `신입` 103 + `경력무관` 57.
    # 경력무관으로 따로 뽑은 58건 중 57건이 그 안에 있었다. 따로 걸 필요가 없다.
    #
    # `exp_none=y` 를 경력무관으로 쓰면 안 된다 — 그것으로 뽑은 82건은
    # `경력무관` 58 + `신입` 16 + **`경력(년수무관)` 8** 이 섞인다.
    # "경력을 안 본다" 가 아니라 "**년수를 안 적었다**" 는 뜻이라,
    # 신입을 찾는 사람에게 경력직 공고가 딸려 온다.
    for yoe in range(-1, 21):
        params = filters.experience_params(yoe)
        check("exp_none" not in params,
              "YOE=%d 에서 exp_none 을 썼다 — 경력직 공고가 섞여 든다" % yoe)


def test_NORMAL_new_graduate_sends_only_exp_cd():
    check_equal(filters.experience_params(0), {"exp_cd": "1"},
                "신입은 exp_cd=1 하나면 된다")
