"""엔트리포인트의 흐름과 **종료 코드**.

가장 중요한 것은 **버림과 실패를 가르는가**다. 그게 뚫리면 우리 쪽 사고로 멀쩡한 공고가
조용히 사라진다.

앞쪽은 `process_one()` 한 건씩, 뒤쪽(`_run()` 을 통째로 돌린다)은 **한 판 전체**다 —
행을 골라 처리하고 없어진 것을 뺀 채 다시 쓰는 재조립은 조각 함수를 아무리 시험해도
안 돈다. 네트워크도 `claude` 도 안 타고, 저장소의 `csv/` 에도 손대지 않는다.
"""
from __future__ import annotations

import contextlib
import io
import shutil as real_shutil
from pathlib import Path

from PIL import Image

import job_image_process as stage
from image_process import cache
from image_process import config as cfg
from image_process import fetch, reader

from .helpers import check, check_equal, read_csv, temp_dir, write_csv

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


def test_EXCEPTION_a_row_without_image_urls_is_never_dropped():
    # `_run()` 은 그림 행만 넘기지만, 이 함수는 공개된 문이다. 잘못 불렸을 때 **버리는
    # 쪽으로 흐르면** 그림도 아닌 행이 사라지고 빈 주소 목록이 캐시 열쇠가 된다.
    book = {}
    got = _run_one(_row(tech="Java, Spring"), book=book)
    check_equal(got.kind, "못읽음", "버림이 아니다")
    check_equal(got.row["기술스택"], "Java, Spring", "행을 건드리지 않는다")
    check_equal(book, {}, "빈 열쇠를 캐시에 만들면 안 된다")


def test_EXCEPTION_an_unopenable_image_keeps_the_row_and_is_not_cached():
    """**껍데기와 "못 열었다" 를 같이 다루면 그 공고는 영영 사라진다.**

    200 인데 안내 페이지 HTML 이거나 AVIF·HEIC 라서 Pillow 가 못 여는 경우다. 껍데기로
    세면 버려지고 그 버림이 캐시에 남아 다음 실행에도 다시 시도하지 않는다.
    """
    def html_instead_of_an_image(url, dest, **kwargs):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"<!DOCTYPE html><html>expired</html>")
        return dest

    book = {}
    got = _run_one(_row(), book=book, download=html_instead_of_an_image)
    check_equal(got.kind, "못읽음", "못 연 것은 껍데기가 아니다")
    check_equal(got.row["기술스택"], "https://img/1.png", "원래 모습 그대로 남긴다")
    check_equal(book, {}, "캐시에 넣으면 다음 실행에도 안 시도한다")


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
    cache.put(book, ["https://img/1.png"], FULL, "sonnet")

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
    check(cache.key(["https://img/1.png"]) in book,
          "빈 결과는 기억한다 — 매번 다시 읽지 않으려고: %r" % book)

    book2 = {}

    def boom(url, dest, **kwargs):
        raise fetch.FetchError("못 받음")

    _run_one(_row(), book=book2, download=boom)
    check_equal(book2, {}, "우리 실패는 기억하지 않는다 — 다음에 다시 시도해야 한다")


def test_BOUNDARY_read_failure_is_retried_once_then_given_up():
    # 실패는 대개 잠깐의 일이라 한 번은 다시 건다. 두 번째도 실패하면 둔다 —
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


def test_BOUNDARY_only_image_rows_are_targeted():
    # 대상 고르기만 본다. **자리를 지키는가**는 `_run()` 을 실제로 돌려서 본다 —
    # 아래 `test_NORMAL_run_keeps_every_surviving_row_in_place` 다.
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


# ── `_run()` 을 통째로 돌린다 ────────────────────────────────────────────────
#
# 여기서만 도는 것: CSV 를 읽고 → 대상만 골라 처리하고 → **없어진 행을 뺀 채 나머지의
# 자리를 지켜** 다시 쓰고 → 종료 코드를 정한다. 그 재조립이 틀어지면 멀쩡한 공고가
# 남의 자리에 가거나 사라지는데, 조각 함수만 시험해서는 절대 드러나지 않는다.
#
# 네트워크도 `claude` 도 안 탄다 — 내려받기·판독·`which` 를 가짜로 바꿔 넣고, 입출력과
# 캐시는 임시 폴더로 옮긴다. **저장소의 `csv/` 에는 손대지 않는다.**

WIDE, NARROW = 800, 300      # 가짜 판독이 답을 고르는 실마리 (아래 참조)


class _FakeShutil:
    """`shutil` 을 통째로 갈아 끼운다 — 진짜 모듈의 `which` 를 건드리지 않으려고."""
    which = staticmethod(lambda name: "/가짜/claude")
    rmtree = staticmethod(real_shutil.rmtree)


def _answer_by_width(paths, **kwargs):
    """가짜 판독. 조각 파일에는 어느 행의 그림이었는지가 안 남으므로 **너비로 가른다** —
    넓은 그림은 읽히고, 좁은 그림은 셋 다 비어 버려진다."""
    with Image.open(paths[0]) as image:
        width = image.size[0]
    return FULL if width >= WIDE else EMPTY


def _download_by_url(sizes: dict):
    def download(url, dest, **kwargs):
        return _draw(dest, *sizes.get(url, (WIDE, 1200)))
    return download


def _run_stage(rows, *, download=None, read=None, book=None):
    """임시 폴더에 CSV 를 깔고 `_run()` 을 돌린다. `(종료코드, 나온 행, 캐시)` 를 준다."""
    home = temp_dir()
    write_csv(home / "csv" / "merged.csv", rows, list(stage.COLUMNS))
    output = home / "csv" / "merged_read.csv"
    cache_path = home / "cache" / "image_reads.json"
    if book:
        cache.save(cache_path, book)

    saved = (stage.ROOT_DIR, stage.INPUT, stage.OUTPUT, stage.shutil,
             stage.fetch.download, stage.reader.read, stage.config.load_config,
             stage.cache.CACHE_PATH)
    stage.ROOT_DIR, stage.INPUT, stage.OUTPUT = home, home / "csv" / "merged.csv", output
    stage.shutil = _FakeShutil
    stage.fetch.download = download or _download_by_url({})
    stage.reader.read = read or _answer_by_width
    stage.config.load_config = lambda *args, **kwargs: CONFIG
    stage.cache.CACHE_PATH = cache_path
    noise = io.StringIO()                 # 진행 막대와 요약은 시험 화면을 어지럽힌다
    try:
        with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
            code = stage._run()
    finally:
        (stage.ROOT_DIR, stage.INPUT, stage.OUTPUT, stage.shutil,
         stage.fetch.download, stage.reader.read, stage.config.load_config,
         stage.cache.CACHE_PATH) = saved
    got = read_csv(output) if output.exists() else []
    return code, got, cache.load(cache_path)


def _at(url, tech, company="회사"):
    return _row(tech=tech, URL=url, 기업명=company)


def test_NORMAL_run_keeps_every_surviving_row_in_place():
    """**버린 행 하나가 나머지의 자리를 밀면 안 된다.**

    그림 아닌 행은 손대지 않고, 읽힌 행은 채우고, 셋 다 빈 행은 없앤다. 남은 것들의
    차례는 `merged.csv` 그대로여야 한다 — 두 파일을 눈으로 견주는 것이 이 단계가
    무엇을 했는지 확인하는 유일한 길이다.
    """
    rows = [
        _at("https://ex/1", "Python"),                      # 그림이 아니다
        _at("https://ex/2", "https://img/채움.png"),         # 읽혀서 채워진다
        _at("https://ex/3", "Go"),                          # 그림이 아니다
        _at("https://ex/4", "https://img/빈것.png"),         # 셋 다 비어 버려진다
    ]
    code, got, _ = _run_stage(rows, download=_download_by_url({
        "https://img/채움.png": (WIDE, 1200),
        "https://img/빈것.png": (NARROW, 400),
    }))
    check_equal(code, 0, "하나라도 해냈으면 정상")
    check_equal([r["URL"] for r in got], ["https://ex/1", "https://ex/2", "https://ex/3"],
                "버린 행만 빠지고 차례는 그대로")
    check_equal(got[0]["기술스택"], "Python", "그림 아닌 행은 손대지 않는다")
    check_equal(got[1]["기술스택"], "Java", "읽어 낸 기술로 갈아끼운다")
    check("3년 이상" in got[1]["지원자격"], "자격요건도 채운다: %r" % got[1]["지원자격"])
    check_equal(got[2]["기술스택"], "Go", "뒤에 있던 행이 앞으로 밀리면 안 된다")


def test_NORMAL_run_writes_nothing_but_the_output_file():
    # 원본을 덮으면 없어진 행의 원본이 어디에도 안 남는다.
    rows = [_at("https://ex/1", "https://img/채움.png")]
    code, got, _ = _run_stage(rows)
    check_equal(code, 0, "정상")
    check_equal(len(got), 1, "한 행")
    check_equal(got[0]["기술스택"], "Java", "채워졌다")


def test_EXCEPTION_run_returns_two_when_nothing_at_all_succeeded():
    def boom(url, dest, **kwargs):
        raise fetch.FetchError("%s 를 못 받았습니다" % url)

    rows = [_at("https://ex/1", "https://img/1.png")]
    code, got, book = _run_stage(rows, download=boom)
    check_equal(code, 2, "하나도 못 해냈으면 2")
    check_equal(len(got), 1, "**못 읽은 행은 버리지 않는다**")
    check_equal(got[0]["기술스택"], "https://img/1.png", "원래 모습 그대로 남는다")
    check_equal(book, {}, "우리 실패는 캐시에 안 넣는다 — 다음 실행에 다시 시도한다")


def test_EXCEPTION_run_does_not_touch_rows_it_never_looked_at():
    # 그림 행이 하나도 없으면 할 일이 없다. 그래도 파일은 나오고 종료 코드는 0 이다.
    rows = [_at("https://ex/1", "Java"), _at("https://ex/2", "Go")]
    code, got, _ = _run_stage(rows)
    check_equal(code, 0, "대상이 0건이어도 정상")
    check_equal([r["기술스택"] for r in got], ["Java", "Go"], "그대로 통과")


def test_BOUNDARY_one_read_failure_among_cache_hits_is_not_a_total_failure():
    """**정상 상태에서 가장 잘 터질 곳이었다.**

    자리 잡힌 뒤에는 거의 모든 건이 캐시 적중이다. 캐시를 "해낸 것" 에서 빼고 세면
    캐시 28 + 새 공고 1건 시간 초과 → `2` → 오케스트레이터가 여덟 분짜리 수집 전체를
    실패로 적는다. 못 읽은 한 건은 요약에 찍히고 다음 실행에 다시 시도한다.
    """
    book = {}
    cache.put(book, ["https://img/캐시.png"], FULL, "sonnet")

    def boom(url, dest, **kwargs):
        if url == "https://img/새것.png":
            raise fetch.FetchError("시간 초과")
        return _draw(dest, WIDE, 1200)

    rows = [_at("https://ex/1", "https://img/캐시.png"),
            _at("https://ex/2", "https://img/새것.png")]
    code, got, _ = _run_stage(rows, download=boom, book=book)
    check_equal(code, 0, "캐시로 건진 것이 있으면 전량 실패가 아니다")
    check_equal(len(got), 2, "두 행 다 남는다")
    check_equal(got[0]["기술스택"], "Java", "캐시에서 채운 행")
    check_equal(got[1]["기술스택"], "https://img/새것.png", "못 읽은 행은 그대로")


def test_BOUNDARY_a_run_that_only_dropped_rows_is_still_a_success():
    # 다 버렸어도 **판정은 해낸 것**이다. `2` 는 "아무것도 못 해냈다" 일 때만이다.
    rows = [_at("https://ex/1", "https://img/빈것.png")]
    code, got, _ = _run_stage(rows, download=_download_by_url(
        {"https://img/빈것.png": (NARROW, 400)}))
    check_equal(code, 0, "버림은 실패가 아니다")
    check_equal(got, [], "버린 행은 안 남는다")


def test_BOUNDARY_run_remembers_what_it_read_for_the_next_time():
    rows = [_at("https://ex/1", "https://img/1.png, https://img/2.png")]
    code, _got, book = _run_stage(rows)
    check_equal(code, 0, "정상")
    check_equal(list(book), [cache.key(["https://img/1.png", "https://img/2.png"])],
                "**공고 하나에 항목 하나** — 낱장으로 흩어 놓으면 남의 공고가 받아 간다: %r"
                % book)


def test_BOUNDARY_download_failure_is_retried_once():
    """**내려받기가 재시도가 필요한 쪽이다.**

    실측 두 실행에서 최종 실패 3건 중 2건이 그림 서버가 연결을 끊은 것이었고, 그 그림을
    나중에 단독으로 받으면 멀쩡히 받힌다. 처음에는 비싼 모델 호출에만 재시도를 걸어 뒀는데,
    정작 끊기는 쪽은 값싼 내려받기였다 — 거꾸로 걸려 있었다.
    """
    tries = []

    def flaky(url, dest, **kwargs):
        tries.append(1)
        if len(tries) == 1:
            raise fetch.FetchError("연결이 끊겼습니다")
        return _draw(dest)

    original = stage.RETRY_PAUSE
    stage.RETRY_PAUSE = 0
    try:
        got = _run_one(_row(), download=flaky)
    finally:
        stage.RETRY_PAUSE = original
    check_equal(len(tries), 2, "한 번은 다시 받아야 한다")
    check_equal(got.kind, "채움", "두 번째에 받히면 그대로 진행한다")


def test_BOUNDARY_download_failing_twice_keeps_the_row():
    # 두 번째도 실패하면 포기하되 **버리지 않는다** — 우리가 못 받은 것이지 그림에
    # 내용이 없는 게 아니다.
    tries = []

    def always(url, dest, **kwargs):
        tries.append(1)
        raise fetch.FetchError("연결이 끊겼습니다")

    book = {}
    original = stage.RETRY_PAUSE
    stage.RETRY_PAUSE = 0
    try:
        got = _run_one(_row(), download=always, book=book)
    finally:
        stage.RETRY_PAUSE = original
    check_equal(len(tries), 2, "두 번까지만 시도한다")
    check_equal(got.kind, "못읽음", "버리지 않는다")
    check_equal(got.row["기술스택"], "https://img/1.png", "원래 모습 그대로 남긴다")
    check_equal(book, {}, "우리 실패는 캐시에 안 넣는다 — 다음 실행에 다시 시도해야 한다")


def test_BOUNDARY_undecodable_image_is_not_retried():
    """받아졌는데 안 열리는 파일은 **다시 받아도 같다.**

    2억 3천만 픽셀짜리 그림이 실제로 그랬다. 같은 바이트를 다시 열어 봐야 시간만 버린다 —
    재시도는 내려받기에만 걸고 판독에는 안 건다.
    """
    opens = []

    def broken(path):
        opens.append(1)
        raise fetch.FetchError("%s 를 못 열었습니다: 폭탄 방어" % path.name)

    original_junk, original_pause = stage.fetch.is_junk, stage.RETRY_PAUSE
    stage.fetch.is_junk = broken
    stage.RETRY_PAUSE = 0
    try:
        got = _run_one(_row())
    finally:
        stage.fetch.is_junk = original_junk
        stage.RETRY_PAUSE = original_pause
    check_equal(len(opens), 1, "열기는 한 번만 — 같은 바이트를 다시 열 이유가 없다")
    check_equal(got.kind, "못읽음", "그래도 버리지는 않는다")


def test_BOUNDARY_tech_and_url_in_one_cell_is_still_a_target():
    """**기술이 먼저 오고 주소가 뒤에 오는 행도 그림 본문이다.**

    사람인이 이렇게 준다 — `C++, C, Java, https://…/recruit.png`. 처음에는 칸이 `http` 로
    시작하는지만 봤고, "주소와 기술이 섞인 행은 0건" 이라는 실측을 근거로 삼았다.
    **그 실측이 틀렸다** — `http` 로 시작하는 행만 골라 놓고 그 안에서 섞인 것을 찾는
    순환 논증이었다. 실제 데이터에서 주소가 든 175행 중 **73행(42%)** 이 이 모양이라
    판독 단계를 통째로 지나갔고, 그 공고들의 내용은 그림 안에 있는데 아무도 안 읽었다.
    """
    row = _row(tech="C++, C, Java, https://img/1.png")
    check_equal(stage.image_urls(row), ["https://img/1.png"], "주소를 찾아야 한다")


def test_BOUNDARY_tech_already_in_the_cell_is_not_thrown_away():
    # 수집 단계가 이미 찾아 둔 기술이다. 그림에서 읽은 것으로 **갈아끼우면 그게 사라진다.**
    row = _row(tech="C++, C, Java, https://img/1.png")
    got = _run_one(row, answer={"기술스택": ["Python"], "자격요건": [], "우대사항": []})
    check_equal(got.kind, "채움", "채워야 한다")
    for kept in ("C++", "C", "Java"):
        check(kept in got.row["기술스택"], "%s 가 사라졌다: %r" % (kept, got.row["기술스택"]))
    check("Python" in got.row["기술스택"], "그림에서 읽은 것도 들어가야 한다")
    check("http" not in got.row["기술스택"], "주소는 걷어내야 한다: %r" % got.row["기술스택"])


def test_BOUNDARY_url_is_removed_even_when_the_image_gives_nothing():
    # 그림에서 기술을 못 얻어도 주소는 남기지 않는다 — 주소는 기술이 아니다.
    # 기존 기술이 있으니 이 공고는 살아남는다.
    row = _row(tech="Java, https://img/1.png")
    got = _run_one(row, answer={"기술스택": [], "자격요건": ["3년 이상"], "우대사항": []})
    check_equal(got.kind, "채움", "자격요건을 얻었으니 산다")
    check_equal(got.row["기술스택"], "Java", "기존 기술만 남는다")


def test_BOUNDARY_a_row_with_no_url_is_still_not_a_target():
    # 그림이 없는 평범한 행까지 잡으면 안 된다.
    check_equal(stage.image_urls(_row(tech="Java, Spring")), [], "주소가 없으면 대상이 아니다")
    check_equal(stage.image_urls(_row(tech="")), [], "빈 칸도 아니다")


def test_BOUNDARY_a_warning_survives_the_progress_bar():
    """**경고가 진행 막대에 묻히면 안 된다.**

    경고는 stderr 로 나가는데 막대도 stderr 를 쓴다. 그대로 두면 막대가 덮어써서 실행
    로그에 `warnings.warn(` 마지막 줄만 남는다 — 실제 전체 실행에서 그렇게 한 건을 잃었고,
    어느 그림 때문인지 끝내 못 찾았다.

    Pillow 는 픽셀이 8,900만을 넘으면 **경고만 내고 그림은 읽는다**(오류는 1억 7,900만부터).
    그 구간의 그림은 조용히 지나가므로, 경고가 사라지면 알 방법이 없다.
    """
    import warnings
    said = []
    original = stage.tqdm.write
    stage.tqdm.write = lambda text, **kw: said.append(text)
    try:
        with stage.warnings_through_bar():
            warnings.warn("픽셀이 너무 많습니다", UserWarning)
    finally:
        stage.tqdm.write = original
    joined = "\n".join(said)
    check("픽셀이 너무 많습니다" in joined, "경고 본문이 남아야 한다: %r" % said)
    check("UserWarning" in joined, "종류도 남아야 한다: %r" % said)


def test_BOUNDARY_a_warning_names_the_image_it_came_from():
    # 경고만 남고 어느 그림인지 모르면 손볼 수가 없다.
    import warnings
    said = []
    original = stage.tqdm.write
    stage.tqdm.write = lambda text, **kw: said.append(text)
    try:
        with stage.warnings_through_bar():
            stage.note_current_image("https://img/거대한그림.png")
            warnings.warn("픽셀이 너무 많습니다", UserWarning)
            stage.note_current_image(None)
    finally:
        stage.tqdm.write = original
    check("거대한그림.png" in "\n".join(said), "어느 그림인지 짚어야 한다: %r" % said)


def test_BOUNDARY_the_warning_hook_is_put_back():
    # 남의 경고 처리까지 바꿔 놓고 나가면 안 된다.
    import warnings
    before = warnings.showwarning
    with stage.warnings_through_bar():
        pass
    check(warnings.showwarning is before, "빠져나오면 원래대로 돌려놔야 한다")
