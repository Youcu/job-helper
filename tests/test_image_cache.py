"""공고 하나 단위의 판독 캐시.

사이트별 CSV 가 30일 누적이라 **같은 공고가 30일 동안 계속 대상에 잡힌다.** 캐시가 없으면
같은 그림을 한 달에 서른 번 읽는다.

열쇠는 **낱장 주소가 아니라 그 공고의 주소 목록 전체**다. 낱장으로 넣으면 같은 그림을 쓰는
다른 공고가 남의 답을 받아 간다 — 실제로 `blank.png` 를 서로 다른 두 회사가 쓰고 있었고
사람인 공용 템플릿은 성격상 여러 공고가 나눠 쓴다. 이 파일의 절반이 그 경계다.
"""
from __future__ import annotations

from image_process import cache

from .helpers import check, check_equal, temp_dir

READ = {"기술스택": ["Java"], "자격요건": ["3년 이상"], "우대사항": []}
OTHER = {"기술스택": ["Go"], "자격요건": ["신입"], "우대사항": []}


def test_NORMAL_put_then_get():
    book = {}
    cache.put(book, ["https://a/1.png"], READ, "sonnet")
    got = cache.get(book, ["https://a/1.png"])
    check_equal(got["기술스택"], ["Java"], "넣은 것을 그대로 돌려준다")


def test_NORMAL_a_posting_with_several_images_is_one_entry():
    # 여러 장을 **합쳐 한 번** 읽으므로 답도 하나다. 항목이 장수만큼 생기면 안 된다.
    book = {}
    urls = ["https://a/1.png", "https://a/2.png", "https://a/3.png"]
    cache.put(book, urls, READ, "sonnet")
    check_equal(len(book), 1, "공고 하나에 항목 하나: %r" % book)
    check_equal(cache.get(book, urls)["자격요건"], ["3년 이상"], "목록 그대로 물으면 나온다")


def test_NORMAL_survives_a_round_trip_through_the_file():
    home = temp_dir() / "cache" / "image_reads.json"
    book = {}
    cache.put(book, ["https://a/1.png"], READ, "sonnet")
    cache.save(home, book)
    check_equal(cache.load(home), book, "파일로 갔다 와도 같아야 한다")


def test_NORMAL_records_when_and_with_what_it_was_read():
    # 나중에 "이 값은 어느 모델이 언제 읽은 것인가" 를 되짚을 수 있어야 한다.
    book = {}
    cache.put(book, ["https://a/1.png"], READ, "opus")
    entry = book[cache.key(["https://a/1.png"])]
    check_equal(entry["모델"], "opus", "모델")
    check(entry.get("읽은날"), "읽은 날이 있어야 한다")


def test_EXCEPTION_missing_file_is_an_empty_book():
    check_equal(cache.load(temp_dir() / "없는파일.json"), {}, "없으면 빈 것")


def test_EXCEPTION_broken_file_is_ignored_not_fatal():
    # **캐시 때문에 단계가 멎으면 안 된다.** 캐시는 편의지 진실이 아니다.
    path = temp_dir() / "깨진.json"
    path.write_text("{이건 JSON 이 아니다", encoding="utf-8")
    check_equal(cache.load(path), {}, "무시하고 새로 읽는다")


def test_EXCEPTION_a_shared_image_does_not_leak_between_postings():
    """**이 테스트가 이 파일의 이유다.**

    낱장 열쇠였을 때 A 공고의 자격요건이 B 공고로 새어 들어갔다. 회사 이름은 B 인데
    내용은 A 인 행이, 버려지지도 않고 캐시에까지 남는다.
    """
    공용 = "https://static.saraminimage.co.kr/static/hiring/images/blank.png"
    book = {}
    cache.put(book, [공용, "https://a/A_2.png"], READ, "sonnet")
    check_equal(cache.get(book, [공용, "https://b/B_2.png"]), None,
                "다른 공고는 남의 답을 받으면 안 된다")
    check_equal(cache.get(book, [공용]), None, "낱장으로 물어도 안 나온다")


def test_BOUNDARY_miss_returns_none():
    check_equal(cache.get({}, ["https://a/없다.png"]), None, "없으면 None")


def test_BOUNDARY_old_per_url_entries_are_misses():
    # 옛 캐시 파일은 주소 하나가 열쇠였다. 빗나가는 게 맞다 — 다시 읽으면 그만이고,
    # 잘못 맞는 것보다 낫다.
    book = {"https://a/1.png": {**READ, "읽은날": "2026-09-01", "모델": "sonnet"}}
    check_equal(cache.get(book, ["https://a/1.png", "https://a/2.png"]), None,
                "옛 열쇠는 안 맞는다")


def test_BOUNDARY_order_is_part_of_the_key():
    # 조각을 잇는 차례가 바뀌면 모델에 넣는 입력이 달라진다. 같은 답으로 볼 수 없다.
    book = {}
    cache.put(book, ["https://a/1.png", "https://a/2.png"], READ, "sonnet")
    check_equal(cache.get(book, ["https://a/2.png", "https://a/1.png"]), None,
                "차례가 다르면 다른 열쇠")


def test_BOUNDARY_two_postings_keep_their_own_answers():
    book = {}
    cache.put(book, ["https://a/1.png"], READ, "sonnet")
    cache.put(book, ["https://b/1.png"], OTHER, "sonnet")
    check_equal(cache.get(book, ["https://a/1.png"])["기술스택"], ["Java"], "A 의 답")
    check_equal(cache.get(book, ["https://b/1.png"])["기술스택"], ["Go"], "B 의 답")


def test_BOUNDARY_empty_read_is_cached_too():
    # "셋 다 비었다" 는 **결과이지 실패가 아니다.** 캐시에 안 넣으면 쓰레기 이미지를
    # 30일 동안 매 실행 다시 읽는다.
    book = {}
    empty = {"기술스택": [], "자격요건": [], "우대사항": []}
    cache.put(book, ["https://a/blank.png"], empty, "sonnet")
    got = cache.get(book, ["https://a/blank.png"])
    check_equal(got, empty, "빈 결과도 기억한다")
    check(got is not None, "None 이 아니어야 한다 — 없는 것과 다르다")


def test_BOUNDARY_save_creates_missing_directories():
    home = temp_dir() / "없는" / "깊은" / "경로" / "cache.json"
    cache.save(home, {"https://a/1.png": {"기술스택": [], "자격요건": [], "우대사항": []}})
    check(home.exists(), "디렉터리를 만들어야 한다")
