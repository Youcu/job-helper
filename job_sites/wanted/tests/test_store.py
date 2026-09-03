"""CSV 스키마·병합·보존·원자적 쓰기."""
from __future__ import annotations

import tempfile
from pathlib import Path

from _common.store import COLUMNS, RETENTION_DAYS, merge, read_csv, write_csv
from tests.helpers import assert_raises


def test_BOUNDARY_extra_columns_are_dropped_on_write():
    """사이트가 여분 필드를 넣어도 스키마는 12컬럼 그대로다."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "out.csv"
        write_csv(path, [{**{c: "" for c in COLUMNS}, "URL": "a", "몰래추가": "값"}])
        assert list(read_csv(path)[0]) == COLUMNS


def test_BOUNDARY_merge_same_url_twice_in_one_run():
    """한 실행에 같은 공고가 두 번 들어오면 마지막 것만 남는다."""
    result = merge([], [{"URL": "a", "기업명": "먼저"}, {"URL": "a", "기업명": "나중"}],
                   today="2026-09-03")
    assert len(result.rows) == 1 and result.rows[0]["기업명"] == "나중"


def test_BOUNDARY_merge_with_nothing_on_either_side():
    assert merge([], [], today="2026-09-03").rows == []
    # 보존 기간 안이면 이번에 안 보여도 남고, 최종확인일은 멈춰 있다
    only_old = merge([{"URL": "a", "최초수집일": "2026-08-01", "최종확인일": "2026-08-20"}], [],
                     today="2026-09-03")
    assert only_old.unseen == 1 and only_old.rows[0]["최종확인일"] == "2026-08-20"
    # 이번 수집이 통째로 비어도(조건이 좁아졌거나 사이트가 비었거나) 쌓아 둔 것을 지우지 않는다
    assert only_old.added == 0 and only_old.updated == 0


def test_BOUNDARY_retention_cutoff_is_exact():
    """'30일까지 보존' 이면 30일째는 남고 31일째부터 뺀다."""
    assert RETENTION_DAYS == 30
    today = "2026-09-03"
    cases = {
        "2026-08-05": True,    # 29일 전 — 남는다
        "2026-08-04": True,    # 딱 30일 전 — 남는다
        "2026-08-03": False,   # 31일 전 — 뺀다
        "2026-09-03": True,    # 오늘
        "2026-09-10": True,    # 미래 (시계가 틀어진 경우) — 뺄 이유가 없다
    }
    for last_seen, should_keep in cases.items():
        result = merge([{"URL": "x", "최초수집일": "2026-07-01", "최종확인일": last_seen}],
                       [], today=today)
        kept = bool(result.rows)
        assert kept is should_keep, f"{last_seen}: 남음={kept}, 기대={should_keep}"


def test_BOUNDARY_retention_period_is_configurable():
    existing = [{"URL": "x", "최초수집일": "2026-07-01", "최종확인일": "2026-09-01"}]
    assert merge(existing, [], today="2026-09-03", retention_days=1).expired == 1
    assert merge(existing, [], today="2026-09-03", retention_days=7).rows
    # 0일이면 오늘 확인 안 된 것은 전부 뺀다
    assert merge(existing, [], today="2026-09-03", retention_days=0).expired == 1


def test_EXCEPTION_csv_from_before_the_columns_grew():
    """이력 컬럼이 없던 시절 파일도 읽어야 한다. 안 그러면 쌓아 둔 것을 잃는다."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "old.csv"
        path.write_text("기업명,URL,사이트명\nX,https://a,wanted\n", encoding="utf-8-sig")
        rows = read_csv(path)
        assert rows[0]["기업명"] == "X"
        assert rows[0]["최초수집일"] == ""          # 언제 처음 봤는지는 알 수 없다
        # 다음 수집에서 보이면 그때부터 날짜가 붙는다
        merged = merge(rows, [{"URL": "https://a", "기업명": "X"}], today="2026-09-03")
        assert merged.rows[0]["최초수집일"] == "2026-09-03"


def test_EXCEPTION_missing_csv_is_an_empty_start():
    assert read_csv(Path("/tmp/절대_없는_파일.csv")) == []


def test_EXCEPTION_rows_without_a_usable_date_are_never_expired():
    """날짜를 모르는 것을 오래됐다고 단정하면 지울 이유가 없는 공고를 지운다.

    이력 컬럼이 없던 시절 파일에서 올라온 행이 그렇다. 다음 수집에서 보이면 날짜가 붙는다.
    """
    existing = [
        {"URL": "빈값", "최초수집일": "", "최종확인일": ""},
        {"URL": "손으로고침", "최초수집일": "", "최종확인일": "어제쯤"},
    ]
    result = merge(existing, [], today="2026-09-03")
    assert result.expired == 0
    assert result.undated == 2
    assert len(result.rows) == 2
    # 다음 수집에서 보이면 날짜가 붙고 그때부터 세어진다
    after = merge(result.rows, [{"URL": "빈값"}], today="2026-09-03")
    assert next(r for r in after.rows if r["URL"] == "빈값")["최종확인일"] == "2026-09-03"


def test_EXCEPTION_rows_without_url_are_skipped_in_merge():
    """URL 이 없으면 어느 공고인지 못 가린다. 키 없는 행을 쌓으면 중복만 는다."""
    result = merge([{"기업명": "키없음"}], [{"기업명": "이것도"}], today="2026-09-03")
    assert result.rows == [] and result.added == 0


def test_EXCEPTION_unreadable_today_deletes_nothing():
    """오늘이 언제인지 못 읽으면 만료 판단을 하지 않는다.

    지우는 판단이라 '모르겠으면 지운다' 는 있을 수 없다.
    """
    existing = [{"URL": "아주오래됨", "최초수집일": "2020-01-01", "최종확인일": "2020-01-01"}]
    result = merge(existing, [], today="언제인지 모름")
    assert result.expired == 0 and len(result.rows) == 1


def test_EXCEPTION_write_failure_keeps_the_previous_file():
    """쌓는 구조라 쓰기 사고의 대가가 크다 — 한 번 깨지면 이력 전체를 잃는다."""
    import tempfile

    class Boom(dict):
        def get(self, *args, **kwargs):
            raise RuntimeError("쓰다가 죽음")

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "out.csv"
        write_csv(path, [{**{c: "" for c in COLUMNS}, "URL": "a", "기업명": "원본"}])
        before = read_csv(path)
        assert_raises(RuntimeError, write_csv, path,
                      [{**{c: "" for c in COLUMNS}, "URL": "b"}, Boom()])
        assert read_csv(path) == before, "이전 파일이 깨졌다"
        assert not list(path.parent.glob(".out.csv.tmp*")), "임시 파일이 남았다"


def test_NORMAL_csv_round_trip():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "out.csv"
        rows = merge([], [{"URL": "a", "기업명": "X", "기술스택": "Python, Go"}], today="2026-09-03").rows
        write_csv(path, rows)
        back = read_csv(path)
        assert len(back) == 1
        assert list(back[0]) == COLUMNS, "컬럼 순서가 바뀌면 다른 사이트 CSV 와 못 합친다"
        assert back[0]["기술스택"] == "Python, Go"
        assert back[0]["최초수집일"] == "2026-09-03"


def test_NORMAL_expired_postings_are_removed():
    """내려간 공고를 영영 쌓아 두면 지원할 수도 없는 것이 지금 열린 것과 섞인다."""
    existing = [
        {"URL": "살아있음", "최초수집일": "2026-07-01", "최종확인일": "2026-09-03"},
        {"URL": "오래됨", "최초수집일": "2026-07-01", "최종확인일": "2026-07-20"},
    ]
    result = merge(existing, [{"URL": "살아있음"}], today="2026-09-03")
    assert result.expired == 1
    assert [r["URL"] for r in result.rows] == ["살아있음"]


def test_NORMAL_merge_adds_updates_and_keeps_unseen():
    """세 갈래를 한 번에: 새로 뜬 것 · 이번에도 본 것 · 이번에 안 보인 것."""
    existing = [
        {"URL": "a", "기업명": "옛이름", "최초수집일": "2026-08-30", "최종확인일": "2026-09-02"},
        {"URL": "b", "기업명": "내려감", "최초수집일": "2026-08-30", "최종확인일": "2026-09-02"},
    ]
    fresh = [{"URL": "a", "기업명": "새이름"}, {"URL": "c", "기업명": "신규"}]
    result = merge(existing, fresh, today="2026-09-03")

    assert (result.added, result.updated, result.unseen) == (1, 1, 1)
    by_url = {r["URL"]: r for r in result.rows}

    # 이번에도 본 공고: 내용은 최신으로, 처음 본 날은 지킨다
    assert by_url["a"]["기업명"] == "새이름"
    assert by_url["a"]["최초수집일"] == "2026-08-30"
    assert by_url["a"]["최종확인일"] == "2026-09-03"
    # 이번에 안 보인 공고: 지우지 않고 최종확인일을 그대로 둔다
    assert by_url["b"]["최종확인일"] == "2026-09-02"
    # 새로 뜬 공고: 두 날짜가 오늘
    assert by_url["c"]["최초수집일"] == by_url["c"]["최종확인일"] == "2026-09-03"


def test_NORMAL_merge_is_idempotent():
    """같은 결과로 여러 번 돌려도 행이 불어나지 않는다."""
    fresh = [{"URL": "a", "기업명": "X"}, {"URL": "b", "기업명": "Y"}]
    rows = []
    for _ in range(3):
        result = merge(rows, fresh, today="2026-09-03")
        rows = result.rows
    assert len(rows) == 2
    assert result.added == 0 and result.updated == 2


def test_NORMAL_merge_sorts_recently_seen_first():
    rows = merge(
        [{"URL": "old", "최초수집일": "2026-08-01", "최종확인일": "2026-08-01"}],
        [{"URL": "new"}],
        today="2026-09-03",
    ).rows
    assert rows[0]["URL"] == "new", "최근에 확인된 공고가 위로 와야 한다"
