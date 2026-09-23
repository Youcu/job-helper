"""그림을 받아 오고, 글이 담길 수 없는 것을 걸러낸다.

## 크기로 욕심내지 않는다

주소 33개를 전부 받아 재 봤다. 크기로 걸러지는 것은 `blank.png`(1×1, 73바이트) 하나뿐이다.
사람인 기본 템플릿(`it1.webp`, 1720×760) 같은 것은 **크기로 못 가린다** — 그건 판정
단계에서 "셋 다 비었다" 로 걸린다. 여기서 과하게 거르면 멀쩡한 공고를 잃는다.

## 실패는 숨기지 않는다

내려받기 실패를 조용히 "빈 결과" 로 넘기면 **버림 판정이 오염된다.** 우리가 못 받은 것을
그림에 내용이 없는 것으로 읽어 멀쩡한 공고를 버리게 된다. 그래서 예외로 알린다.

**파일을 아예 못 여는 것도 같은 실패다.** 200 으로 받았는데 내용이 안내 페이지의 HTML
이거나, AVIF·HEIC 처럼 Pillow 가 기본으로 모르는 형식이면 `Image.open` 이 터진다. 그것을
"글이 담길 수 없는 그림" 으로 세면 그 공고는 버려지고 캐시에까지 들어가 **영영 다시
시도하지 않는다.** 그래서 `is_junk` 는 크기만 판정하고, 못 여는 것은 `FetchError` 로
올린다 — 껍데기(버림)와 우리 쪽 실패(보류)는 다른 사실이다.
"""
from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

MIN_SIDE = 100
TIMEOUT = 25
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")


class FetchError(RuntimeError):
    """그림을 못 받았다. **버림 판정에 쓰면 안 된다.**"""


def relaxed_context() -> ssl.SSLContext:
    """암호 모음만 한 칸 낮춘 TLS 설정. **인증서 검증은 그대로 켜 둔다.**

    낮추는 것은 `SECLEVEL` 하나다 — 호스트 이름 확인도, 인증서 검증도 건드리지 않는다.
    "안 되면 검증을 끈다" 는 유혹이 있는데, 그러면 아무 서버나 그 회사인 척할 수 있다.
    """
    context = ssl.create_default_context()
    context.set_ciphers("DEFAULT@SECLEVEL=1")
    return context


def _open(url: str, timeout: int, context: ssl.SSLContext | None = None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if context is None:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))
    with opener.open(request, timeout=timeout) as response:
        return response.read()


def _fetch(url: str, timeout: int) -> bytes:
    """**기본 보안 설정으로 먼저 붙고, 악수가 깨질 때만 한 칸 물러선다.**

    오래된 서버는 TLS 악수 단계에서 연결을 끊는다. `m.altwell.co.kr` 은 `AES128-SHA`
    하나만 지원하는데 파이썬 기본 설정(보안 수준 2)이 그 암호를 목록에서 빼서 악수가
    깨진다 — `curl` 은 같은 주소를 5/5 로 받는다.

    **재시도로는 안 풀린다.** 우리 설정이 그 서버와 안 맞는 것이라 백 번을 걸어도 백 번
    실패한다. 실제로 전체 실행 네 번에서 네 번 다 같은 공고를 잃었고, 그 공고에는
    Delphi·Visual Basic·MS-SQL 같은 구체적인 자격요건이 그림 안에 온전히 들어 있었다.

    **HTTP 오류에는 물러서지 않는다.** 404 는 TLS 문제가 아니라서 낮춰 봐야 똑같이 404 다.
    """
    try:
        return _open(url, timeout)
    except urllib.error.HTTPError:
        raise
    except (urllib.error.URLError, OSError):
        return _open(url, timeout, context=relaxed_context())


def download(url: str, dest: Path, *, timeout: int = TIMEOUT, opener=None) -> Path:
    opener = opener or _fetch
    try:
        data = opener(url, timeout)
    except Exception as error:
        raise FetchError("%s 를 못 받았습니다: %s: %s"
                         % (url, type(error).__name__, error)) from error
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


def is_junk(path: Path) -> bool:
    """글이 담길 수 없는 **크기**인가. 여기 걸리면 모델을 부르지 않고 버린다.

    **못 여는 파일은 여기서 판정하지 않는다** — `FetchError` 로 올린다. "열었는데 너무
    작다" 는 그림에 대한 사실이고, "아예 못 열었다" 는 우리 쪽 사실이다. 둘을 같이
    다루면 안 열린 공고가 버려지고 그 버림이 캐시에 남는다.
    """
    try:
        with Image.open(path) as image:
            width, height = image.size
    except Exception as error:
        raise FetchError("%s 를 못 열었습니다: %s: %s"
                         % (path.name, type(error).__name__, error)) from error
    return width < MIN_SIDE or height < MIN_SIDE
