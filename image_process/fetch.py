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


def _fetch(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


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
