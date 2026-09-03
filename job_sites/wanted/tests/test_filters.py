"""수집 조건 → API 코드 (직군·직무·근무지)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from lib.filters import LocationError, job_groups, job_titles, resolve_locations
from tests.helpers import assert_raises


def test_BOUNDARY_ambiguous_district_includes_all_and_warns():
    """'중구' 는 여섯 시도에 있다. 하나만 고르면 조용히 틀린다."""
    slugs, warnings = resolve_locations(["중구"])
    assert len(slugs) >= 6 and warnings and "중구" in warnings[0]


def test_BOUNDARY_duplicate_locations_collapse():
    assert resolve_locations(["서울", "서울", " 서울 "])[0] == ["seoul.all"]
    assert resolve_locations([])[0] == ["all"]
    assert resolve_locations([""])[0] == ["all"]


def test_EXCEPTION_unknown_location_is_loud():
    """모르는 지역을 조용히 버리면 사용자는 조건이 걸린 줄 안다."""
    assert_raises(LocationError, resolve_locations, ["없는동네"])
    assert_raises(LocationError, resolve_locations, ["SEOUL.ALL"])   # slug 는 소문자다


def test_NORMAL_job_code_tables_load():
    assert job_groups()[518] == "개발"
    assert job_titles()[872] == "서버 개발자"



def test_NORMAL_location_mapping():
    assert resolve_locations(["서울"])[0] == ["seoul.all"]
    assert resolve_locations(["강남구"])[0] == ["seoul.gangnam-gu"]
    assert resolve_locations(["서울 강남구"])[0] == ["seoul.gangnam-gu"]
    assert resolve_locations(["gyeonggi.yongin-si"])[0] == ["gyeonggi.yongin-si"]
    slugs, warnings = resolve_locations(["서울", "용인시", "성남시", "수원시", "화성시"])
    assert slugs == [
        "seoul.all", "gyeonggi.yongin-si", "gyeonggi.seongnam-si",
        "gyeonggi.suwon-si", "gyeonggi.hwaseong-si",
    ]
    assert not warnings
