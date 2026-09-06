"""공고 본문에서 읽을 글을 꺼내고, 글인지 그림인지 가른다.

**본문은 상세 페이지에 없다.** `GI_Read_Comt_Ifrm` 이 따로 준다 (`collect.fetch_body`).
상세 HTML 에는 `iframe` 이라는 글자조차 없어서 — JS 가 나중에 꽂는다 — 본문이 아예
없는 줄 알기 쉽다. 실제로 그렇게 헤맸다.

## 그림 본문이 24%다

공고 67건 실측 — 보이는 글 200자 이상 45건(67%), **0자 16건(24%)**, 1~199자 6건.
짧은 22건은 거의 다 `<img>` 를 갖고 있다(중앙값 1장). 사람인(18%)보다 나쁘다.

**여기서 그림을 읽지 않는다.** 읽는 것은 수집이 끝난 뒤 도는 별도 단계의 일이고,
이 모듈은 "여기는 그림이다, 주소는 이것이다" 까지만 알려 준다 (D-13).
"""
from __future__ import annotations

import re
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from _common.html_text import split_visible, to_text, visible_text

SITE_ORIGIN = "https://www.jobkorea.co.kr"

# 주소는 **굽은 따옴표에서도 끊는다.** 손으로 쓴 공고에 `src="주소" alt="` 처럼 닫는
# 따옴표가 굽은 것(`"`)인 것이 있어, 곧은 따옴표만 끝으로 보면 다음 따옴표까지 먹어
# `...jpeg%E2%80%9D%20alt=` 라는 못 쓰는 주소가 된다 — 실측 2건.
# **공백에서는 끊지 않는다.** `.../Devops Engineer_260624_예서_.png` 처럼 파일 이름에
# 공백이 든 주소가 실제로 있다. `safe_url` 이 `%20` 으로 바꿔 내보낸다.
IMAGE_SOURCE = re.compile(
    r"""<img[^>]*?src\s*=\s*["']([^"'\u201c\u201d\u2018\u2019]+)""", re.IGNORECASE)

TEMPLATE_ASSET = re.compile(r"//i\.jobkorea\.kr/content/images/", re.IGNORECASE)

# 보이는 글이 이 길이에 못 미치면 사람이 읽을 글이 없는 것으로 본다.
# 67건 실측에서 중앙값 519자였고, 200자 미만 22건은 거의 다 그림이거나 빈 껍데기였다.
MIN_BODY_LENGTH = 200

# 주소에서 **그대로 둬도 되는 글자** (RFC 3986). 넓게 인코딩하면 멀쩡한 주소가 바뀌고,
# 좁게 하면 공백·한글이 남아 받는 쪽이 터진다.
PATH_SAFE = "/%!$&'()*+,;=:@"
QUERY_SAFE = PATH_SAFE + "?"


def visible_body(body_html: str) -> str:
    """본문에서 **화면에 보이는 글만.** 산문 매칭에 넘길 것은 이것이다."""
    return visible_text(_without_code(body_html))


def looks_like_image_body(body_html: str) -> bool:
    """읽을 글이 없는가 (그림으로만 된 공고).

    산문 매칭이 아무것도 못 낼 상태라는 뜻이지 오류가 아니다.
    """
    return len(visible_body(body_html)) < MIN_BODY_LENGTH


def image_urls(body_html: str) -> list[str]:
    """본문 안 그림 주소. 순서를 지키고 중복을 없앤다.

    **읽지는 않는다.** 나중 단계가 이 주소로 화면을 찍어 읽는다.
    주소는 바로 쓸 수 있게 다듬어 내보낸다 — 파일 이름에 공백·한글이 들면
    받는 쪽에서 요청이 터진다.
    """
    found = IMAGE_SOURCE.findall(_without_code(body_html) or "")
    kept = (safe_url(_absolute(url)) for url in found if _is_image(url))
    return list(dict.fromkeys(url for url in kept if not TEMPLATE_ASSET.search(url)))


def safe_url(url: str) -> str:
    """주소에 그대로 못 싣는 글자를 퍼센트 인코딩한다.

    이미 인코딩된 `%EC%9D%B4` 를 다시 인코딩하면 `%25EC…` 가 되어 파일을 못 찾으므로
    `%` 는 건드리지 않는다. 경로에서 원래 써도 되는 글자도 그대로 둔다.
    """
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, quote(parts.path, safe=PATH_SAFE),
                       quote(parts.query, safe=QUERY_SAFE), parts.fragment))


def hidden_body_text(body_html: str) -> str:
    """본문에서 화면에 **안 보이는** 글. 왜 본문이 비었는지 들여다볼 때 쓴다."""
    _visible, hidden = split_visible(_without_code(body_html))
    return to_text(hidden)


def visible_body_html(body_html: str) -> str:
    """본문 HTML 에서 코드 덩이만 걷어낸 것. 태그는 남는다 — 줄바꿈을 살려야 절을 가른다."""
    return _without_code(body_html)


def _without_code(body_html: str) -> str:
    return re.sub(r"<(script|style)\b.*?</\1>", " ", body_html or "",
                  flags=re.DOTALL | re.IGNORECASE)


def _is_image(url: str) -> bool:
    """읽으러 갈 수 있는 주소인가. 인라인 데이터는 주소가 아니라 그림 자체다.

    **확장자를 요구하지 않는다.** 잡코리아가 회사 그림을 나르는 주력 경로가
    `//file2.jobkorea.co.kr/Net/Mng/DownImage/CorpEditor?file_No=1862238` 이라 경로에
    점이 없다. 확장자를 요구했더니 그림 본문 공고 6건이 통째로 사라졌다.
    장식 그림은 `TEMPLATE_ASSET` 이 따로 거른다.
    """
    return bool(url) and not url.startswith("data:")


def _absolute(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return urljoin(SITE_ORIGIN, url)
    return url
