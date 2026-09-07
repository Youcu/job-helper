"""그림을 받아 오고, 글이 담길 수 없는 것을 걸러낸다.

## 크기로 욕심내지 않는다

주소 33개를 전부 받아 재 봤다. 크기로 걸러지는 것은 `blank.png`(1×1, 73바이트) 하나뿐이다.
사람인 기본 템플릿(`it1.webp`, 1720×760) 같은 것은 **크기로 못 가린다** — 그건 판정
단계에서 "셋 다 비었다" 로 걸린다. 여기서 과하게 거르면 멀쩡한 공고를 잃는다.

## 실패는 숨기지 않는다

내려받기 실패를 조용히 "빈 결과" 로 넘기면 **버림 판정이 오염된다.** 우리가 못 받은 것을
그림에 내용이 없는 것으로 읽어 멀쩡한 공고를 버리게 된다. 그래서 예외로 알린다.
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
    """글이 담길 수 없는 그림인가. 여기 걸리면 모델을 부르지 않는다."""
    try:
        with Image.open(path) as image:
            width, height = image.size
    except Exception:
        return True
    return width < MIN_SIDE or height < MIN_SIDE
