"""엔트리포인트의 흐름과 **종료 코드**.

가장 중요한 것은 **버림과 실패를 가르는가**다. 그게 뚫리면 우리 쪽 사고로 멀쩡한 공고가
조용히 사라진다.
"""
from __future__ import annotations

from PIL import Image

import job_image_process as stage
from image_process import config as cfg
from image_process import fetch, reader

from .helpers import check, check_equal, temp_dir

CONFIG = cfg.Config(model="sonnet", workers=1, timeout=60)
FULL = {"기술스택": ["Java"], "자격요건": ["3년 이상"], "우대사항": []}
EMPTY = {"기술스택": [], "자격요건": [], "우대사항": []}


def _row(tech="https://img/1.png", **fields) -> dict:
    row = {c: "" for c in stage.COLUMNS}
    row.update({"기업명": "회사", "URL": "https://example.com/1",
                "사이트명": "jobkorea", "기술스택": tech})
    row.update(fields)
    return row


def _draw(path, width=800, height=1200):
    Image.new("RGB", (width, height), (255, 255, 255)).save(path)
    return path


def _run_one(row, *, answer=FULL, book=None, size=(800, 1200), download=None):
    work = temp_dir()

    def fake_download(url, dest, **kwargs):
        return _draw(dest, *size)

    original = stage.fetch.download
    stage.fetch.download = download or fake_download
    try:
        return stage.process_one(row, cfg=CONFIG, book=book if book is not None else {},
                                 work_dir=work,
                                 reader_fn=lambda paths, **kw: answer)
    finally:
        stage.fetch.download = original


def test_NORMAL_a_normal_row_passes_through_untouched():
    row = _row(tech="Java, Spring")
    check_equal(stage.image_urls(row), [], "이미지 행이 아니다")


def test_NORMAL_image_row_is_filled():
    got = _run_one(_row())
    check_equal(got.kind, "채움", "채워야 한다")
    check_equal(got.row["기술스택"], "Java", "기술")
    check("3년 이상" in got.row["지원자격"], "자격요건")


def test_NORMAL_several_urls_in_one_cell():
    row = _row(tech="https://img/1.png, https://img/2.png")
    check_equal(stage.image_urls(row), ["https://img/1.png", "https://img/2.png"], "둘 다")


def test_EXCEPTION_empty_answer_drops_the_row():
    got = _run_one(_row(), answer=EMPTY)
    check_equal(got.kind, "버림", "셋 다 비면 버린다")
    check_equal(got.row, None, "남길 행이 없다")


def test_EXCEPTION_download_failure_keeps_the_row():
    """**이 테스트가 이 파일의 이유다.** 우리가 못 받은 것으로 공고를 버리면 안 된다."""
    def boom(url, dest, **kwargs):
        raise fetch.FetchError("못 받음")

    got = _run_one(_row(), download=boom)
    check_equal(got.kind, "못읽음", "실패는 버림이 아니다")
    check_equal(got.row["기술스택"], "https://img/1.png", "원래 모습 그대로 남긴다")


def test_EXCEPTION_read_failure_keeps_the_row():
    def boom(paths, **kwargs):
        raise reader.ReadError("시간 초과")

    work = temp_dir()
    original = stage.fetch.download
    stage.fetch.download = lambda url, dest, **kw: _draw(dest)
    try:
        got = stage.process_one(_row(), cfg=CONFIG, book={}, work_dir=work, reader_fn=boom)
    finally:
        stage.fetch.download = original
    check_equal(got.kind, "못읽음", "호출 실패는 버림이 아니다")


def test_BOUNDARY_junk_image_is_dropped_without_calling_the_model():
    called = []

    def watcher(paths, **kwargs):
        called.append(paths)
        return FULL

    work = temp_dir()
    original = stage.fetch.download
    stage.fetch.download = lambda url, dest, **kw: _draw(dest, 1, 1)
    try:
        got = stage.process_one(_row(), cfg=CONFIG, book={}, work_dir=work,
                                reader_fn=watcher)
    finally:
        stage.fetch.download = original
    check_equal(got.kind, "껍데기", "1×1 은 껍데기")
    check_equal(called, [], "모델을 부르면 안 된다 — 돈이 든다")


def test_BOUNDARY_cache_hit_skips_the_model():
    called = []
    book = {}
    from image_process import cache
    cache.put(book, "https://img/1.png", FULL, "sonnet")

    def watcher(paths, **kwargs):
        called.append(paths)
        return FULL

    work = temp_dir()
    original = stage.fetch.download
    stage.fetch.download = lambda url, dest, **kw: _draw(dest)
    try:
        got = stage.process_one(_row(), cfg=CONFIG, book=book, work_dir=work,
                                reader_fn=watcher)
    finally:
        stage.fetch.download = original
    check_equal(got.kind, "캐시", "캐시에서 나와야 한다")
    check_equal(called, [], "부르면 안 된다")


def test_BOUNDARY_empty_answer_is_cached_but_failure_is_not():
    book = {}
    _run_one(_row(), answer=EMPTY, book=book)
    check("https://img/1.png" in book, "빈 결과는 기억한다 — 매번 다시 읽지 않으려고")

    book2 = {}

    def boom(url, dest, **kwargs):
        raise fetch.FetchError("못 받음")

    _run_one(_row(), book=book2, download=boom)
    check_equal(book2, {}, "우리 실패는 기억하지 않는다 — 다음에 다시 시도해야 한다")


def test_BOUNDARY_read_failure_is_retried_once_then_given_up():
    # 실패는 대개 한도에 걸린 것이라 한 번은 다시 건다. 두 번째도 실패하면 둔다 —
    # 계속 매달리면 뒤엣것이 밀린다.
    tries = []

    def flaky(paths, **kwargs):
        tries.append(1)
        raise reader.ReadError("한도")

    work = temp_dir()
    original_download, original_pause = stage.fetch.download, stage.RETRY_PAUSE
    stage.fetch.download = lambda url, dest, **kw: _draw(dest)
    stage.RETRY_PAUSE = 0
    try:
        got = stage.process_one(_row(), cfg=CONFIG, book={}, work_dir=work,
                                reader_fn=flaky)
    finally:
        stage.fetch.download = original_download
        stage.RETRY_PAUSE = original_pause
    check_equal(len(tries), 2, "두 번 시도해야 한다")
    check_equal(got.kind, "못읽음", "그래도 안 되면 못읽음")


def test_BOUNDARY_a_second_try_that_succeeds_is_used():
    tries = []

    def flaky(paths, **kwargs):
        tries.append(1)
        if len(tries) == 1:
            raise reader.ReadError("한도")
        return FULL

    work = temp_dir()
    original_download, original_pause = stage.fetch.download, stage.RETRY_PAUSE
    stage.fetch.download = lambda url, dest, **kw: _draw(dest)
    stage.RETRY_PAUSE = 0
    try:
        got = stage.process_one(_row(), cfg=CONFIG, book={}, work_dir=work,
                                reader_fn=flaky)
    finally:
        stage.fetch.download = original_download
        stage.RETRY_PAUSE = original_pause
    check_equal(got.kind, "채움", "두 번째에 성공하면 쓴다")


def test_BOUNDARY_rows_that_are_not_images_keep_their_place():
    # 그림 행만 손대고 나머지는 차례까지 그대로여야 한다 — 순서가 바뀌면 눈으로 견주기 어렵다.
    rows = [_row(tech="Java"), _row(tech="https://img/1.png"), _row(tech="Go")]
    check_equal([bool(stage.image_urls(r)) for r in rows], [False, True, False], "가운데만 대상")


def test_BOUNDARY_output_is_beside_merged_not_on_top_of_it():
    check_equal(stage.OUTPUT.name, "merged_read.csv", "이름")
    check(stage.INPUT.name == "merged.csv", "입력")
    check(stage.INPUT != stage.OUTPUT, "**원본을 덮으면 안 된다**")


def test_BOUNDARY_main_returns_three_when_locked():
    import tempfile
    from pathlib import Path

    from _common.runlock import run_lock
    original = stage.LOCK
    stage.LOCK = Path(tempfile.mkdtemp()) / ".test.lock"
    try:
        with run_lock(stage.LOCK):
            check_equal(stage.main(), 3, "겹쳐 돌면 3")
    finally:
        stage.LOCK = original
