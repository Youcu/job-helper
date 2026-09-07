"""그림을 받아 오고, **글이 담길 수 없는 크기**를 걸러낸다.

주소 33개를 전부 내려받아 재 본 결과 크기로 걸러지는 것은 `blank.png`(1×1) 하나뿐이었다.
크기로 더 욕심내지 않는다 — 사람인 기본 템플릿(1720×760) 같은 것은 크기로 못 가리고,
그건 판정 단계에서 "셋 다 비었다" 로 걸린다.

**`is_junk` 는 크기만 본다.** 못 여는 파일은 껍데기가 아니라 우리 쪽 실패라 예외로 올린다 —
껍데기는 버리고 캐시에 넣지만, 우리 쪽 실패는 둘 다 안 한다.
"""
from __future__ import annotations

from PIL import Image

from image_process import fetch

from .helpers import check, check_equal, temp_dir


def _png(width: int, height: int, name: str = "a.png"):
    path = temp_dir() / name
    Image.new("RGB", (width, height), (255, 255, 255)).save(path)
    return path


def test_NORMAL_downloads_to_the_given_path():
    home = temp_dir() / "받은것.png"
    fetch.download("https://a/1.png", home, opener=lambda url, timeout: b"PNGBYTES")
    check_equal(home.read_bytes(), b"PNGBYTES", "받은 것을 그대로 쓴다")


def test_NORMAL_a_normal_image_is_not_junk():
    check(not fetch.is_junk(_png(860, 5628)), "긴 공고 그림은 멀쩡하다")


def test_EXCEPTION_download_failure_raises():
    def boom(url, timeout):
        raise OSError("연결 실패")

    error = None
    try:
        fetch.download("https://a/1.png", temp_dir() / "x.png", opener=boom)
    except fetch.FetchError as caught:
        error = caught
    check(error is not None, "실패는 알려야 한다 — 조용히 넘기면 버림 판정이 오염된다")
    check("https://a/1.png" in str(error), "어느 주소인지 짚어야 한다: %s" % error)


def test_EXCEPTION_unopenable_file_is_our_failure_not_junk():
    """**안 열리는 것은 껍데기가 아니다.**

    200 으로 받았는데 안내 페이지 HTML 이거나 AVIF·HEIC 라서 Pillow 가 못 여는 경우다.
    껍데기로 세면 그 공고는 버려지고 그 버림이 캐시에 남아 영영 다시 시도하지 않는다.
    """
    path = temp_dir() / "그림이아님.png"
    path.write_bytes("이건 이미지가 아니다".encode())
    error = None
    try:
        fetch.is_junk(path)
    except fetch.FetchError as caught:
        error = caught
    check(error is not None, "못 여는 것은 버림이 아니라 우리 쪽 실패로 올려야 한다")
    check("그림이아님.png" in str(error), "어느 파일인지 짚어야 한다: %s" % error)


def test_EXCEPTION_an_html_placeholder_is_not_junk_either():
    # 실제로 걸릴 만한 모양 — 만료된 공고가 200 으로 안내 페이지를 준다.
    path = temp_dir() / "안내.jpg"
    path.write_bytes(b"<!DOCTYPE html><html><body>\xeb\x81\x9d\xeb\x82\x9c \xea\xb3\xb5\xea\xb3\xa0</body></html>")
    raised = False
    try:
        fetch.is_junk(path)
    except fetch.FetchError:
        raised = True
    check(raised, "HTML 을 그림으로 세면 멀쩡한 공고가 사라진다")


def test_BOUNDARY_one_by_one_is_junk():
    # 실제로 있었다. `static.saraminimage.co.kr/.../blank.png` 는 1×1 · 73바이트다.
    check(fetch.is_junk(_png(1, 1)), "1×1 은 글이 담길 수 없다")


def test_BOUNDARY_exactly_min_side_is_kept():
    check(not fetch.is_junk(_png(fetch.MIN_SIDE, fetch.MIN_SIDE)), "딱 100×100 은 통과")
    check(fetch.is_junk(_png(fetch.MIN_SIDE - 1, 500)), "가로가 하나 모자라면 껍데기")
    check(fetch.is_junk(_png(500, fetch.MIN_SIDE - 1)), "세로가 하나 모자라면 껍데기")


def test_BOUNDARY_wide_and_short_strip_is_kept():
    # 한 공고가 그림 여섯 장으로 쪼개져 있었고 그중 하나가 960×212 였다. 버리면 안 된다.
    check(not fetch.is_junk(_png(960, 212)), "짧은 띠도 글이 있을 수 있다")
