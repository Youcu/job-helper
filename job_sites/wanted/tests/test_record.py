"""공고 → CSV 한 줄."""
from __future__ import annotations

import tempfile
from pathlib import Path

from _common.store import merge
from lib.skills import find_skills_in_text
from lib.record import (
    COLUMNS,
    extract_skills,
    format_career,
    format_deadline,
    format_workplace,
    to_row,
)
from tests.helpers import FIXTURES, assert_raises


def test_BOUNDARY_career_inverted_and_negative():
    """결함: `10~3년`, `신입~-1년` 같은 말이 안 되는 문구가 CSV 에 실렸다."""
    assert format_career(10, 3) == "3~10년"      # 뒤집힌 범위는 바로잡는다
    assert format_career(-1, 5) == "신입~5년"      # 음수는 없는 값으로
    assert format_career(0, -1) == "신입"
    assert format_career(None, None) == "경력무관"


def test_BOUNDARY_career_unbounded_marker():
    """API 는 상한 없음을 100 으로 준다 (실측: 5~100, 3~100)."""
    assert format_career(5, 100) == "5년 이상"
    assert format_career(0, 100) == "신입"
    assert format_career(5, 99) == "5~99년"      # 99 는 아직 범위다


def test_BOUNDARY_deadline_edges():
    assert format_deadline(None) == "상시채용"
    assert format_deadline("") == "상시채용"
    assert format_deadline("2026-09-30T23:59:59") == "2026-09-30"


def test_BOUNDARY_workplace_falls_back_and_prefixes():
    """회사 자유 입력 주소에 등록된 구가 없으면 앞에 붙인다."""
    assert format_workplace({"location": "서울", "district": "강남구"}) == "서울 강남구"
    assert format_workplace(
        {"location": "서울", "district": "강남구", "full_location": "테헤란로 201"}
    ) == "서울 강남구 · 테헤란로 201"
    assert format_workplace({"full_location": "어딘가"}) == "어딘가"
    assert format_workplace({}) == ""


def test_BOUNDARY_workplace_gets_the_missing_sido():
    """결함: 구는 적고 시도를 빼먹은 주소가 8행 있었다 — `서초구 강남대로 465`.

    계약은 `시도 구 상세주소` 인데 그런 행은 시도로 묶이지 않는다. 등록된 시도가
    응답에 있으므로 앞에 붙인다. **이미 시도로 시작하면 건드리지 않는다.**
    """
    assert format_workplace(
        {"location": "서울", "district": "서초구", "full_location": "서초구 강남대로 465"}
    ) == "서울 서초구 강남대로 465"
    assert format_workplace(
        {"location": "서울", "district": "강남구", "full_location": "서울시 강남구 선릉로 525"}
    ) == "서울시 강남구 선릉로 525", "이미 시도가 있으면 그대로 (짧은 표기는 저장할 때 맞춘다)"
    assert format_workplace(
        {"district": "서초구", "full_location": "서초구 강남대로 465"}
    ) == "서초구 강남대로 465", "등록된 시도가 없으면 지어내지 않는다"


# ----------------------------------------------------------------------
# 재실행 — 파이프라인은 주기로 돈다
# ----------------------------------------------------------------------


def test_EXCEPTION_empty_and_missing_fields_do_not_crash():
    job = {"id": 1, "company": None, "detail": None, "address": None,
           "skill_tags": None, "annual_from": None, "annual_to": None, "due_time": None}
    row = to_row(job)
    assert row["기업명"] == "" and row["근무지"] == ""
    assert row["공고명"] == ""      # 상세를 못 받으면 공고명도 없다. 빈칸이 사실이다
    assert row["경력"] == "경력무관" and row["마감일"] == "상시채용"
    assert row["기술스택"] == ""
    assert extract_skills({}) == []
    assert format_workplace(None) == ""
    assert find_skills_in_text("") == []


def test_EXCEPTION_row_without_job_id_is_refused():
    """결함: id 가 없으면 `https://www.wanted.co.kr/wd/None` 을 조용히 내보냈다."""
    assert_raises(ValueError, to_row, {"company": {"name": "X"}, "detail": {}})


def test_NORMAL_career_range():
    assert format_career(0, 0) == "신입"
    assert format_career(0, 3) == "신입~3년"
    assert format_career(3, 10) == "3~10년"
    assert format_career(8, 8) == "8년"


def test_NORMAL_deadline():
    assert format_deadline("2026-09-30T00:00:00") == "2026-09-30"
    assert format_deadline("2026-09-30") == "2026-09-30"


def test_NORMAL_row_from_real_api_responses():
    """`to_row` 는 공고에서 나오는 칸만 만든다. 이력 두 칸은 병합이 채운다.

    한 실행 안에서는 '처음 본 날' 을 알 수 없다 — 쌓아 둔 파일과 맞대 봐야 나온다.
    """
    history = {"최초수집일", "최종확인일"}
    for payload in FIXTURES.values():
        row = to_row(payload["job"])
        assert set(row) == set(COLUMNS) - history, "컬럼 구성이 스키마와 다르다"
        assert row["기업명"] and row["마감일"] and row["근무지"]
        # 공고명은 **상세에만** 있다 (`detail.position`). 목록 응답에는 없다.
        assert row["공고명"] == (payload["job"]["detail"] or {})["position"].strip()
        assert row["공고명"], "실제 응답이면 공고명이 차 있어야 한다"
        assert row["사이트명"] == "wanted"
        assert row["연봉"] == ""                      # Wanted 는 연봉을 주지 않는다
        assert row["URL"].startswith("https://www.wanted.co.kr/wd/")

    # 병합을 거치면 13칸이 다 찬다 — CSV 로 나가는 모양이다
    merged = merge([], [to_row(p["job"]) for p in FIXTURES.values()], today="2026-09-03")
    assert all(set(r) == set(COLUMNS) for r in merged.rows)


def test_NORMAL_workplace_keeps_company_address():
    assert format_workplace(
        {"location": "서울", "district": "강남구", "full_location": "서울 강남구 테헤란로 445"}
    ) == "서울 강남구 테헤란로 445"
