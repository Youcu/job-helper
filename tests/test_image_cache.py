"""주소별 판독 캐시.

사이트별 CSV 가 30일 누적이라 **같은 공고가 30일 동안 계속 대상에 잡힌다.** 캐시가 없으면
같은 그림을 한 달에 서른 번 읽는다. 그림 주소는 공고마다 고유하고 내용이 안 바뀌므로
열쇠로 알맞다.
"""
from __future__ import annotations

from image_process import cache

from .helpers import check, check_equal, temp_dir

READ = {"기술스택": ["Java"], "자격요건": ["3년 이상"], "우대사항": []}


def test_NORMAL_put_then_get():
    book = {}
    cache.put(book, "https://a/1.png", READ, "sonnet")
    got = cache.get(book, "https://a/1.png")
    check_equal(got["기술스택"], ["Java"], "넣은 것을 그대로 돌려준다")


def test_NORMAL_survives_a_round_trip_through_the_file():
    home = temp_dir() / "cache" / "image_reads.json"
    book = {}
    cache.put(book, "https://a/1.png", READ, "sonnet")
    cache.save(home, book)
    check_equal(cache.load(home), book, "파일로 갔다 와도 같아야 한다")


def test_NORMAL_records_when_and_with_what_it_was_read():
    # 나중에 "이 값은 어느 모델이 언제 읽은 것인가" 를 되짚을 수 있어야 한다.
    book = {}
    cache.put(book, "https://a/1.png", READ, "opus")
    entry = book["https://a/1.png"]
    check_equal(entry["모델"], "opus", "모델")
    check(entry.get("읽은날"), "읽은 날이 있어야 한다")


def test_EXCEPTION_missing_file_is_an_empty_book():
    check_equal(cache.load(temp_dir() / "없는파일.json"), {}, "없으면 빈 것")


def test_EXCEPTION_broken_file_is_ignored_not_fatal():
    # **캐시 때문에 단계가 멎으면 안 된다.** 캐시는 편의지 진실이 아니다.
    path = temp_dir() / "깨진.json"
    path.write_text("{이건 JSON 이 아니다", encoding="utf-8")
    check_equal(cache.load(path), {}, "무시하고 새로 읽는다")


def test_BOUNDARY_miss_returns_none():
    check_equal(cache.get({}, "https://a/없다.png"), None, "없으면 None")


def test_BOUNDARY_empty_read_is_cached_too():
    # "셋 다 비었다" 는 **결과이지 실패가 아니다.** 캐시에 안 넣으면 쓰레기 이미지를
    # 30일 동안 매 실행 다시 읽는다.
    book = {}
    empty = {"기술스택": [], "자격요건": [], "우대사항": []}
    cache.put(book, "https://a/blank.png", empty, "sonnet")
    got = cache.get(book, "https://a/blank.png")
    check_equal(got, empty, "빈 결과도 기억한다")
    check(got is not None, "None 이 아니어야 한다 — 없는 것과 다르다")


def test_BOUNDARY_save_creates_missing_directories():
    home = temp_dir() / "없는" / "깊은" / "경로" / "cache.json"
    cache.save(home, {"https://a/1.png": {"기술스택": [], "자격요건": [], "우대사항": []}})
    check(home.exists(), "디렉터리를 만들어야 한다")
