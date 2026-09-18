"""최종본을 화면으로 그리는 일.

그물도 모델도 안 탄다. 진짜 `csv/` 도 진짜 템플릿도 안 건드린다 — 경로를 전부
인자로 받으므로 임시 디렉터리에서 논다.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import report

COLUMNS = ["기업명", "공고명", "마감일", "지원자격", "우대사항", "경력", "URL",
           "연봉", "기술스택", "근무지", "사이트명", "평점", "최초수집일", "최종확인일"]

TEMPLATE = ("<title>__TITLE__</title><p>__LEDE__</p><p>__SOURCE__</p>"
            "<script>const DATA = __DATA__; const FUNNEL = __FUNNEL__;</script>")


def _csv(path: Path, rows: list[dict]) -> None:
    import csv as csv_module
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv_module.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in COLUMNS})


def _row(**kwargs) -> dict:
    base = {"기업명": "가나다", "공고명": "백엔드 개발자", "URL": "https://x/1",
            "기술스택": "Java, Spring", "사이트명": "wanted", "평점": "3.4",
            "지원자격": "자격", "우대사항": "우대", "경력": "신입", "마감일": "상시채용",
            "연봉": "", "근무지": "서울", "최초수집일": "2026-09-01",
            "최종확인일": "2026-09-18"}
    base.update(kwargs)
    return base


def _data_of(page: str) -> list[dict]:
    """그려 낸 화면에서 자료 부분만 도로 꺼낸다."""
    found = re.search(r"const DATA = (\[.*?\]); const FUNNEL", page, re.S)
    assert found, "화면에 자료가 없습니다"
    return json.loads(found.group(1).replace("<\\/", "</"))


def test_NORMAL_it_draws_every_posting():
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        (home / "csv").mkdir()
        source = home / "csv" / "merged_career.csv"
        _csv(source, [_row(URL="https://x/1"), _row(URL="https://x/2")])
        template = home / "t.html"
        template.write_text(TEMPLATE, encoding="utf-8")
        output = home / "csv" / "report.html"

        assert report._run(source, template, output) == 0
        page = output.read_text(encoding="utf-8")
        assert "백엔드 신입 공고 2건" in page
        assert len(_data_of(page)) == 2


def test_NORMAL_the_tech_column_becomes_a_list():
    """`기술스택` 은 CSV 에서 한 칸이지만 화면에서는 눌러서 거르는 낱낱이다."""
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        (home / "csv").mkdir()
        source = home / "csv" / "merged_career.csv"
        _csv(source, [_row(기술스택="Java, Spring Boot ,  Redis ,")])
        template = home / "t.html"
        template.write_text(TEMPLATE, encoding="utf-8")
        output = home / "csv" / "out.html"

        report._run(source, template, output)
        got = _data_of(output.read_text(encoding="utf-8"))[0]["tech"]
        assert got == ["Java", "Spring Boot", "Redis"], got


def test_BOUNDARY_a_posting_that_contains_a_closing_script_tag():
    """**공고 글은 남이 쓴 것이다.** `</script>` 가 들어오면 브라우저가 거기서
    스크립트를 끊고, 화면은 자료의 절반만 그린 채 멀쩡해 보인다.

    실제 공고에 `</script>` 가 있었던 것은 아니다 — 하지만 본문을 그대로 실어
    나르는 이상 언제든 들어올 수 있고, 들어오면 **조용히** 깨진다.
    """
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        (home / "csv").mkdir()
        source = home / "csv" / "merged_career.csv"
        _csv(source, [_row(지원자격="앞</script><script>window.x=1</script>뒤")])
        template = home / "t.html"
        template.write_text(TEMPLATE, encoding="utf-8")
        output = home / "csv" / "out.html"

        report._run(source, template, output)
        page = output.read_text(encoding="utf-8")
        assert "</script><script>window.x=1" not in page, "스크립트가 끊깁니다"
        assert _data_of(page)[0]["req"] == "앞</script><script>window.x=1</script>뒤", \
            "갈라 넣은 것을 도로 못 읽습니다"


def test_BOUNDARY_a_missing_stage_file_is_not_zero():
    """안 돌린 단계와 **걸러서 하나도 안 남은** 단계는 다르다.

    둘 다 0 으로 적으면 화면이 "평점에서 전멸했다" 고 말하는데 사실은 그 단계를
    아직 안 돌린 것일 수 있다.
    """
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        csv_dir = home / "csv"
        csv_dir.mkdir()
        _csv(csv_dir / "merged_career.csv", [_row()])
        _csv(csv_dir / "merged_rated.csv", [])          # 돌렸는데 안 남았다

        steps = dict(report.funnel(csv_dir))
        assert steps["평점"] == 0, "돌렸는데 안 남은 것은 0 이다"
        assert steps["핵심 기술"] is None, "안 돌린 것은 None 이다 — 0 이 아니다"


def test_EXCEPTION_no_input_says_so_and_stops():
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        template = home / "t.html"
        template.write_text(TEMPLATE, encoding="utf-8")
        assert report._run(home / "없다.csv", template, home / "out.html") == 1
        assert not (home / "out.html").exists()


def test_EXCEPTION_no_template_says_so_and_stops():
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        (home / "csv").mkdir()
        source = home / "csv" / "merged_career.csv"
        _csv(source, [_row()])
        assert report._run(source, home / "없다.html", home / "out.html") == 1


def test_BOUNDARY_the_real_template_has_every_placeholder():
    """템플릿은 디자인 하느라 손으로 고치는 파일이다. 자리 표시를 하나 지우면
    그 자리가 **글자 그대로** 화면에 남는다 — 오류는 안 난다."""
    page = report.TEMPLATE.read_text(encoding="utf-8")
    for mark in ("__TITLE__", "__LEDE__", "__SOURCE__", "__FUNNEL__", "__DATA__"):
        assert mark in page, "report_template.html 에 %s 가 없습니다" % mark


def test_BOUNDARY_nothing_of_the_template_is_left_unfilled():
    """그려 낸 화면에 자리 표시가 남아 있으면 안 된다."""
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        (home / "csv").mkdir()
        source = home / "csv" / "merged_career.csv"
        _csv(source, [_row()])
        output = home / "csv" / "out.html"
        report._run(source, report.TEMPLATE, output)
        page = output.read_text(encoding="utf-8")
        left = re.findall(r"__[A-Z]+__", page)
        assert not left, "채우지 않은 자리 표시가 남았습니다: %s" % left
