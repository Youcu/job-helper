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


def test_NORMAL_default_tls_is_tried_first():
    """**기본 보안 설정으로 먼저 붙는다.** 낮춘 설정은 물러설 때만 쓴다."""
    seen = []
    original = fetch._open
    fetch._open = lambda url, timeout, context=None: seen.append(context) or b"IMG"
    try:
        fetch.download("https://a/1.png", temp_dir() / "x.png")
    finally:
        fetch._open = original
    check_equal(seen, [None], "기본 설정(None)으로 한 번만 부른다: %r" % seen)


def test_EXCEPTION_old_server_falls_back_to_a_weaker_cipher():
    """오래된 서버는 **TLS 악수 단계에서** 연결을 끊는다.

    실제로 겪었다 — `m.altwell.co.kr` 은 `AES128-SHA` 하나만 지원하는데 파이썬 기본
    설정(보안 수준 2)이 그 암호를 목록에서 빼서 악수가 깨진다. `curl` 은 5/5 로 받는다.
    **재시도로는 절대 안 풀린다** — 우리 설정이 안 맞는 것이라 백 번을 걸어도 백 번
    실패한다. 실제로 전체 실행 네 번에서 네 번 다 같은 자리에서 잃었다.
    """
    seen = []

    def picky(url, timeout, context=None):
        seen.append(context)
        if context is None:
            raise OSError(54, "Connection reset by peer")
        return b"IMG"

    original = fetch._open
    fetch._open = picky
    try:
        home = temp_dir() / "x.png"
        fetch.download("https://a/1.png", home)
    finally:
        fetch._open = original
    check_equal(len(seen), 2, "두 번 시도해야 한다: %r" % seen)
    check(seen[0] is None, "먼저 기본 설정")
    check(seen[1] is not None, "그다음 낮춘 설정")
    check_equal(home.read_bytes(), b"IMG", "받은 것을 써야 한다")


def test_EXCEPTION_a_real_http_error_is_not_retried_with_weaker_tls():
    # 404 는 TLS 문제가 아니다. 낮춰 봐야 똑같이 404 이고, 헛되이 한 번 더 두드린다.
    import urllib.error
    seen = []

    def missing(url, timeout, context=None):
        seen.append(context)
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    original = fetch._open
    fetch._open = missing
    try:
        error = None
        try:
            fetch.download("https://a/없다.png", temp_dir() / "x.png")
        except fetch.FetchError as caught:
            error = caught
    finally:
        fetch._open = original
    check(error is not None, "실패는 알려야 한다")
    check_equal(len(seen), 1, "한 번만 시도한다 — 404 는 물러설 일이 아니다: %r" % seen)


def test_BOUNDARY_the_relaxed_context_is_only_a_cipher_step_down():
    # 인증서 검증까지 끄면 안 된다. 낮추는 것은 **암호 모음 하나**다.
    ctx = fetch.relaxed_context()
    check(ctx.check_hostname, "호스트 이름 검증은 그대로 켜 둔다")
    import ssl
    check_equal(ctx.verify_mode, ssl.CERT_REQUIRED, "인증서 검증도 그대로다")
