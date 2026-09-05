"""상세 페이지에서 **본문 덩어리**를 잘라 내고, 그 안이 글인지 그림인지 가른다.

여기만 본문 컨테이너의 생김새를 안다. 기술스택을 뽑는 쪽(`skills`)도, CSV 한 줄을
만드는 쪽(`record`)도, 수집을 도는 쪽(`saramin.py`)도 전부 본문이 필요한데,
그 지식이 세 군데로 흩어지면 사이트가 마크업을 바꿀 때 세 곳을 고쳐야 한다.

    body_html(page)            본문 덩어리만 잘라 낸다
    looks_like_image_body(page) 사람이 읽을 글이 있는가
    image_urls(page)           본문 안 그림 주소 (읽지는 않는다)

**그림은 여기서 읽지 않는다.** 읽는 것은 수집이 끝난 뒤 도는 별도 단계의 일이고,
이 모듈은 "여기는 그림이다, 주소는 이것이다" 까지만 알려 준다 (D-13).
"""
from __future__ import annotations

import re
from urllib.parse import quote, urlsplit, urlunsplit

from _common.html_text import split_visible, to_text, visible_text

SITE_ORIGIN = "https://www.saramin.co.kr"

# 본문 컨테이너. rec_idx 가 클래스 이름에 박혀 있어 다른 블록과 헷갈릴 일이 없다.
BODY_CONTAINER = re.compile(r'<div class="user_content jobsViewDetail_(\d+)">')

# 본문 안 그림. `src` 만 본다.
IMAGE_SOURCE = re.compile(r"<img[^>]*?src\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)

# 보이는 본문이 이 길이에 못 미치면 사람이 읽을 글이 없는 것으로 본다.
# 131건 실측에서 보이는 본문 길이 중앙값은 1,018자였고, 100자 미만 24건은 전부
# 그림이거나 빈 껍데기였다. 경계를 넉넉히 낮게 잡아 멀쩡한 본문을 버리지 않는다.
MIN_BODY_LENGTH = 100

# 주소에서 **그대로 둬도 되는 글자** (RFC 3986). 이보다 넓게 인코딩하면 멀쩡한 주소가
# 바뀌고, 좁게 하면 공백·한글이 남아 받는 쪽이 터진다.
PATH_SAFE = "/%!$&\'()*+,;=:@"
QUERY_SAFE = PATH_SAFE + "?"


def body_html(page: str) -> str:
    """상세 페이지에서 본문 컨테이너만 잘라 낸다. 없으면 빈 문자열.

    안에 `div` 가 겹쳐 있으므로 깊이를 세어 짝을 맞춘다 — 첫 `</div>` 에서 끊으면
    본문 대부분을 잃는다.
    """
    if not page:
        return ""
    match = BODY_CONTAINER.search(page)
    if not match:
        return ""
    start = match.start()
    depth = 0
    for tag in re.finditer(r"<(/?)div\b[^>]*?(/?)>", page[start:]):
        if tag.group(2) == "/":
            continue
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return page[start:start + tag.end()]
    return page[start:]          # 안 닫혔으면 끝까지 — 잘라 버리는 것보다 낫다


def visible_body(page: str) -> str:
    """본문에서 **화면에 보이는 글만.** 산문 매칭에 넘길 것은 이것이다.

    숨긴 글을 섞으면 화면에 글자가 하나도 없는 공고에서 기술 61개가 나온다
    (`_common/html_text.py` 참고).
    """
    return visible_text(body_html(page))


def looks_like_image_body(page: str) -> bool:
    """본문에 사람이 읽을 글이 없는가 (그림 한 장짜리 공고).

    산문 매칭이 아무것도 못 낼 상태라는 뜻이지 오류가 아니다.
    """
    return len(visible_body(page)) < MIN_BODY_LENGTH


def image_urls(page: str) -> list[str]:
    """본문 안 그림 주소. 순서를 지키고 중복을 없앤다.

    **읽지는 않는다.** 나중 단계가 이 주소로 화면을 찍어 읽는다.
    주소는 바로 쓸 수 있게 다듬어 내보낸다 — 회사가 올린 파일 이름에 공백과 한글이
    들어서, 그대로 요청하면 `http.client.InvalidURL` 이 난다.
    """
    found = IMAGE_SOURCE.findall(body_html(page or ""))
    absolute = (safe_url(_absolute(url)) for url in found if _is_image(url))
    return list(dict.fromkeys(absolute))


def safe_url(url: str) -> str:
    """주소에 그대로 못 싣는 글자를 퍼센트 인코딩한다.

    실제로 겪은 것 — `/data/job_image/플렉스지 유지보수 개발(사람인).jpg`.

    **꼭 필요한 것만 바꾼다.** 이미 인코딩된 `%EC%9D%B4` 를 다시 인코딩하면 `%25EC…` 가
    되어 파일을 못 찾고, 경로에서 원래 써도 되는 글자(`+` `=` `(` `)` 등, RFC 3986 의
    sub-delims)까지 바꾸면 **멀쩡하던 주소가 매 실행 달라 보인다.** 실제로 그렇게
    안 고쳐도 될 주소 3장을 건드렸다.
    """
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, quote(parts.path, safe=PATH_SAFE),
                       quote(parts.query, safe=QUERY_SAFE), parts.fragment))


def hidden_body_text(page: str) -> str:
    """본문에서 화면에 **안 보이는** 글. 왜 본문이 비었는지 들여다볼 때 쓴다."""
    _visible, hidden = split_visible(body_html(page))
    return to_text(hidden)


def _is_image(url: str) -> bool:
    """추적 픽셀과 인라인 데이터는 공고 그림이 아니다."""
    if not url or url.startswith("data:"):
        return False
    return "." in url.rsplit("/", 1)[-1]


def _absolute(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return SITE_ORIGIN + url
    return url
