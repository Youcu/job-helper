"""공고 본문을 CSV 옆에 따로 두는 일.

그물도 모델도 안 탄다.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from _common import bodies

ROOT = Path(__file__).resolve().parent.parent
SITES = ("saramin", "jobkorea", "jobplanet", "jumpit", "wanted")


def test_NORMAL_it_keeps_the_body_beside_the_csv():
    with tempfile.TemporaryDirectory() as home:
        target = Path(home) / "saramin_post.csv"
        written = bodies.write_map({"u1": "가나다", "u2": "라마바"}, bodies.path_for(target))
        assert written == 2
        assert bodies.load(bodies.path_for(target)) == {"u1": "가나다", "u2": "라마바"}


def test_NORMAL_running_one_site_again_keeps_what_was_there():
    """한 사이트만 여러 번 돌릴 때 앞 실행 본문을 잃지 않는다 — CSV 와 같은 규칙이다."""
    with tempfile.TemporaryDirectory() as home:
        path = Path(home) / "b.jsonl"
        bodies.write_map({"u1": "처음"}, path)
        bodies.write_map({"u2": "나중"}, path)
        assert bodies.load(path) == {"u1": "처음", "u2": "나중"}


def test_NORMAL_a_second_run_overwrites_the_same_posting():
    with tempfile.TemporaryDirectory() as home:
        path = Path(home) / "b.jsonl"
        bodies.write_map({"u1": "옛것"}, path)
        bodies.write_map({"u1": "새것"}, path)
        assert bodies.load(path) == {"u1": "새것"}


def test_BOUNDARY_a_broken_line_does_not_lose_the_rest():
    """본문은 거드는 자료다. 한 줄이 깨졌다고 수집 전체를 멈출 이유가 없다."""
    with tempfile.TemporaryDirectory() as home:
        path = Path(home) / "b.jsonl"
        path.write_text('{"URL":"u1","본문":"살아 있다"}\n{깨진 줄\n'
                        '{"URL":"u2","본문":"이것도"}\n', encoding="utf-8")
        assert bodies.load(path) == {"u1": "살아 있다", "u2": "이것도"}


def test_BOUNDARY_a_huge_page_is_cut():
    with tempfile.TemporaryDirectory() as home:
        path = Path(home) / "b.jsonl"
        bodies.write_map({"u1": "가" * (bodies.MAX_BODY + 500)}, path)
        assert len(bodies.load(path)["u1"]) == bodies.MAX_BODY


def test_BOUNDARY_an_empty_body_is_not_recorded():
    """빈 본문을 적으면 "받았는데 비었다" 와 "안 받았다" 가 같아 보인다."""
    with tempfile.TemporaryDirectory() as home:
        path = Path(home) / "b.jsonl"
        bodies.write_map({"u1": "   ", "u2": "있다"}, path)
        assert bodies.load(path) == {"u2": "있다"}


def test_NORMAL_gather_puts_five_sites_into_one():
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        paths = []
        for index in range(3):
            path = home / ("s%d.jsonl" % index)
            bodies.write_map({"u%d" % index: "본문%d" % index}, path)
            paths.append(path)
        total = bodies.gather(paths, home / "all.jsonl")
        assert total == 3
        assert bodies.load(home / "all.jsonl") == {
            "u0": "본문0", "u1": "본문1", "u2": "본문2"}


def test_BOUNDARY_gather_over_a_missing_file_still_writes():
    with tempfile.TemporaryDirectory() as home:
        home = Path(home)
        bodies.gather([home / "없다.jsonl"], home / "all.jsonl")
        assert (home / "all.jsonl").exists()
        assert bodies.load(home / "all.jsonl") == {}


def test_BOUNDARY_every_site_records_a_body():
    """**새 사이트가 본문을 빠뜨리면 여기서 잡는다.**

    빠뜨려도 수집은 멀쩡히 돈다. 어긋나는 것은 한참 뒤 — 직군을 가리는 단계가
    그 사이트의 통합 공고를 만났을 때인데, 그때는 **이미 잘려 나간 칸**으로
    판단하고 아무 말도 안 한다.

    처음에 사람인·잡코리아 둘만 넣으려 했다. 오늘 걷힌 672행에서 통합 공고가
    그 둘에만 있었기 때문이다. **그건 표본이지 규칙이 아니다** (2026-09-18 사용자)
    — 내일 wanted 에 하나 뜨면 조용히 틀린다. 그래서 다섯을 다 본다.
    """
    no_body = [site for site in SITES
               if "def body_of(" not in (ROOT / "job_sites" / site / "lib" / "record.py")
               .read_text(encoding="utf-8")]
    assert not no_body, (
        "본문을 안 내는 수집기가 있습니다: %s\n"
        "  `record.py` 에 `body_of()` 를 두세요 — 절로 자르기 전의 글 전부입니다."
        % ", ".join(no_body))

    unused = [site for site in SITES
              if "body_of(" not in (ROOT / "job_sites" / site / (site + ".py"))
              .read_text(encoding="utf-8")]
    assert not unused, (
        "`body_of()` 를 만들어 두고 안 부르는 수집기가 있습니다: %s\n"
        "  걷는 자리에서 (URL → 본문) 을 모아 `save(rows, OUTPUT, texts)` 로 넘기세요."
        % ", ".join(unused))


def test_BOUNDARY_the_site_list_here_matches_what_is_on_disk():
    """위 검사가 도는 사이트 목록도 손으로 적는다 — 새 사이트를 빠뜨리면 검사가 헛돈다."""
    on_disk = {path.parent.parent.name
               for path in (ROOT / "job_sites").glob("*/lib/record.py")}
    assert on_disk == set(SITES), "tests/test_bodies.py 의 SITES 가 디스크와 다릅니다: %s" % (
        sorted(on_disk ^ set(SITES)),)
