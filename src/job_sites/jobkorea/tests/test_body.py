"""본문에서 글을 꺼내고 그림 주소를 남긴다.

**실제 결함 둘이 여기 있었다.** 둘 다 예외가 안 나고 결과도 나와서, 실행 결과를
눈으로 훑기 전에는 몰랐다.

    확장자 검사      → 잡코리아 주력 배달 주소를 버려 그림 공고 6건이 통째로 사라졌다
    공백에서 끊기     → 파일 이름에 공백이 든 주소를 앞에서 잘라 버렸다
"""
from __future__ import annotations

from lib.body import (MIN_BODY_LENGTH, image_urls, looks_like_image_body, safe_url,
                      visible_body)

from .helpers import body_html, check, check_equal, img


def test_NORMAL_reads_visible_text():
    text = visible_body("<div><p>Python 백엔드 개발자를 찾습니다</p></div>")
    check("Python" in text and "백엔드" in text, "보이는 글: %r" % text)


def test_NORMAL_collects_image_urls_in_order():
    html = img("https://a.co/1.png") + img("https://a.co/2.png")
    check_equal(image_urls(html), ["https://a.co/1.png", "https://a.co/2.png"], "순서 유지")


def test_NORMAL_real_image_body_yields_urls():
    # 본문이 그림 하나뿐인 실제 공고.
    html = body_html("49911986")
    check(looks_like_image_body(html), "그림 본문으로 판정해야 한다")
    urls = image_urls(html)
    check_equal(len(urls), 1, "그림 하나: %r" % urls)
    check(urls[0].startswith("https://file2.jobkorea.co.kr/"), urls[0])


def test_NORMAL_script_and_style_are_not_text():
    html = "<script>var skill='Rust';</script><style>.a{color:red}</style><p>Java</p>"
    text = visible_body(html)
    check("Rust" not in text and "color" not in text, "코드는 글이 아니다: %r" % text)
    check("Java" in text, "글은 남아야 한다")


def test_EXCEPTION_empty_and_broken_input():
    for value in ("", None, "<img", "<div>"):
        check_equal(image_urls(value), [], "망가진 입력: %r" % value)
        check_equal(visible_body(value), "", "망가진 입력: %r" % value)
    check(looks_like_image_body(""), "빈 본문은 읽을 글이 없는 것이다")


def test_EXCEPTION_data_uri_is_not_a_url():
    check_equal(image_urls(img("data:image/gif;base64,R0lGOD")), [],
                "인라인 데이터는 읽으러 갈 주소가 아니다")


def test_EXCEPTION_empty_src():
    check_equal(image_urls(img("")), [], "빈 src")


def test_BOUNDARY_url_without_extension_is_kept():
    # 결함이었던 곳: 확장자를 요구했더니 잡코리아 주력 배달 경로가 통째로 버려졌다.
    # 그림 본문 공고 6건이 "기술도 그림도 없음" 으로 빠졌다.
    url = "//file2.jobkorea.co.kr/Net/Mng/DownImage/CorpEditor?file_No=1862238"
    check_equal(image_urls(img(url, 'title="채용공고.png"')),
                ["https:" + url], "확장자가 없어도 그림 주소다")


def test_BOUNDARY_space_in_filename_is_encoded_not_truncated():
    # 결함이었던 곳: 공백에서 끊었더니 `.../Devops` 만 남아 버려졌다.
    got = image_urls(img("https://s3.aws.com/Devops Engineer_예서_.png"))
    check_equal(len(got), 1, "주소를 잃으면 안 된다: %r" % got)
    check("%20" in got[0] and got[0].endswith(".png"), got[0])


def test_BOUNDARY_curly_closing_quote():
    # 결함이었던 곳: 닫는 따옴표가 굽은 것(`"`)이면 다음 따옴표까지 먹어
    # `...jpeg%E2%80%9D%20alt=` 라는 못 쓰는 주소가 됐다 — 실측 2건.
    check_equal(image_urls('<img src="https://imgur.com/NASx9W1.jpeg” alt=">'),
                ["https://imgur.com/NASx9W1.jpeg"], "굽은 따옴표에서 끊어야 한다")


def test_BOUNDARY_template_decoration_is_dropped():
    # 편집기가 깔아 주는 머리말 그림·꾸밈 아이콘. 읽어도 공고 내용이 없다.
    html = (img("http://i.jobkorea.kr/content/images/yocruit/yctr/gen/hd_req.png")
            + img("https://file1.jobkorea.co.kr/Mng/2026/9/ahnlab.jpg"))
    check_equal(image_urls(html), ["https://file1.jobkorea.co.kr/Mng/2026/9/ahnlab.jpg"],
                "회사가 올린 그림만 남는다")


def test_BOUNDARY_all_images_are_decoration():
    html = img("http://i.jobkorea.kr/content/images/yocruit/skin/icn_shape_7.gif")
    check_equal(image_urls(html), [], "장식뿐이면 남길 주소가 없다")


def test_BOUNDARY_protocol_relative_and_root_relative():
    check_equal(image_urls(img("//img.datau.co.kr/a.jpg")),
                ["https://img.datau.co.kr/a.jpg"], "`//` 는 https 로")
    check_equal(image_urls(img("/Mng/a.jpg")),
                ["https://www.jobkorea.co.kr/Mng/a.jpg"], "`/` 는 사이트 기준으로")


def test_BOUNDARY_single_quoted_src():
    check_equal(image_urls("<img src='https://a.co/1.png'>"), ["https://a.co/1.png"],
                "홑따옴표도 읽어야 한다")


def test_BOUNDARY_duplicate_images_collapse():
    check_equal(image_urls(img("https://a.co/1.png") * 3), ["https://a.co/1.png"],
                "같은 그림은 한 번만")


def test_BOUNDARY_safe_url_is_idempotent():
    # 두 번 인코딩하면 `%EC` 가 `%25EC` 가 되어 그림을 못 받는다.
    for url in ("https://a.co/a%20b_%EC%98%88.png",
                "https://a.co/a+b=c.png",
                "https://a.co/p?f=1&g=2"):
        check_equal(safe_url(safe_url(url)), safe_url(url), "두 번 인코딩: %s" % url)
        check_equal(safe_url(url), url, "이미 멀쩡한 주소는 그대로 둔다: %s" % url)


def test_BOUNDARY_image_body_threshold():
    check(looks_like_image_body("<p>%s</p>" % ("가" * (MIN_BODY_LENGTH - 1))),
          "기준 바로 아래는 그림 본문")
    check(not looks_like_image_body("<p>%s</p>" % ("가" * (MIN_BODY_LENGTH + 1))),
          "기준 바로 위는 글 본문")
