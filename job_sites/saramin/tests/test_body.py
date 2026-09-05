"""`lib/body.py` — 본문 덩어리를 잘라 내고 글인지 그림인지 가른다.

**여기가 틀리면 그 뒤가 전부 틀린다.** 본문을 못 찾으면 기술스택도 지원자격도 빈다.
그래서 노리는 것은 셋이다.

1. **본문을 짧게 끊는 것.** 안에 `div` 가 겹쳐 있어 첫 `</div>` 에서 끊으면 대부분을 잃는다
2. **안 보이는 글을 본문으로 세는 것.** 숨긴 SEO 블록 때문에 글자가 0자인 공고에서
   기술 61개가 나온 적이 있다
3. **그림 주소를 그대로 내보내는 것.** 파일 이름에 공백·한글이 들면 받는 쪽이 터진다 —
   실제로 그 이유로 389건 수집이 50건째에서 죽었다
"""
from __future__ import annotations

from lib import body
from tests.helpers import check, check_equal


def wrap(inner: str, rec_idx: str = "1234") -> str:
    return '<div class="user_content jobsViewDetail_%s">%s</div>' % (rec_idx, inner)


def test_NORMAL_body_container_is_found_by_rec_idx_class():
    html = '<div class="wrap">' + wrap("<p>본문</p>", rec_idx="7") + "</div>"
    check("본문" in body.body_html(html), "본문 컨테이너를 찾아야 한다")


def test_NORMAL_image_urls_are_read_from_the_body_only():
    page = '<img src="/banner.png">' + wrap('<img src="https://x.test/a.png">')
    check_equal(body.image_urls(page), ["https://x.test/a.png"],
                "본문 밖 그림은 공고 내용이 아니다")


def test_NORMAL_relative_image_urls_become_absolute():
    check_equal(body.image_urls(wrap('<img src="//cdn.test/a.png">')),
                ["https://cdn.test/a.png"], "// 로 시작하면 https 를 붙인다")
    check_equal(body.image_urls(wrap('<img src="/recruit/a.png">')),
                ["https://www.saramin.co.kr/recruit/a.png"], "/ 로 시작하면 사람인 호스트")


def test_EXCEPTION_tracking_pixels_and_inline_data_are_skipped():
    page = wrap('<img src="data:image/png;base64,AAAA"><img src="/track?id=1">')
    check_equal(body.image_urls(page), [], "그림 파일이 아닌 것은 뺀다")


def test_BOUNDARY_duplicate_image_urls_collapse():
    page = wrap('<img src="https://x.test/a.png"><img src="https://x.test/a.png">')
    check_equal(body.image_urls(page), ["https://x.test/a.png"], "같은 그림은 하나로")


def test_NORMAL_spaces_and_hangul_in_an_image_url_are_encoded():
    # 이 결함이 실제로 389건 수집을 50건째에서 죽였다 —
    # `/data/job_image/플렉스지 유지보수 개발(사람인).jpg` 에서 `InvalidURL` 이 났다.
    encoded = body.safe_url("https://x.test/a/플렉스 개발(사람인).jpg")
    check(" " not in encoded, "공백이 남으면 요청이 터진다: %s" % encoded)
    check("플렉스" not in encoded, "한글은 인코딩돼야 한다")


def test_BOUNDARY_already_encoded_url_is_not_double_encoded():
    # `%20` 을 다시 인코딩하면 `%2520` 이 되어 파일을 못 찾는다.
    url = "https://x.test/%EC%9D%B4%EB%AF%B8.png"
    check_equal(body.safe_url(url), url, "이중 인코딩하면 안 된다")


def test_NORMAL_plain_url_is_left_alone():
    for url in ("https://x.test/a.png", "https://x.test/a.png?v=1&x=2"):
        check_equal(body.safe_url(url), url, "멀쩡한 주소는 안 건드린다")


def test_EXCEPTION_missing_body_container_is_empty_not_crash():
    check_equal(body.body_html("<html><p>본문 컨테이너가 없다</p></html>"), "",
                "컨테이너가 없으면 빈 문자열이다")
    check_equal(body.body_html(""), "", "빈 문자열")
    check_equal(body.visible_body("<html></html>"), "", "본문이 없으면 볼 글도 없다")


def test_BOUNDARY_image_body_threshold_is_inclusive():
    short = "가" * (body.MIN_BODY_LENGTH - 1)
    exact = "가" * body.MIN_BODY_LENGTH
    check(body.looks_like_image_body(wrap("<p>%s</p>" % short)),
          "기준보다 짧으면 이미지 본문으로 본다")
    check(not body.looks_like_image_body(wrap("<p>%s</p>" % exact)),
          "기준과 같으면 본문이 있는 것으로 본다")


def test_BOUNDARY_nested_div_in_the_body_does_not_end_it_early():
    # 본문 안에 div 가 겹쳐 있다. 첫 </div> 에서 끊으면 본문 대부분을 잃는다.
    html = wrap("<div><div><p>안쪽 깊은 곳의 글</p></div></div>") + "<p>본문 밖</p>"
    check("안쪽 깊은 곳의 글" in body.visible_body(html), "겹친 div 를 세어야 한다")
    check("본문 밖" not in body.visible_body(html), "본문을 넘어가면 안 된다")


def test_NORMAL_hidden_body_text_is_available_for_diagnosis():
    # 숨긴 글은 기술스택에 안 넣지만, 왜 비었는지 볼 수 있어야 한다.
    hidden = '<td style="display:none">IT개발·데이터 &gt; 기술스택 &gt; Java</td>'
    html = wrap("<p>보이는 글</p>" + hidden)
    text = body.hidden_body_text(html)
    check("기술스택" in text, "숨긴 글을 꺼내 볼 수 있어야 한다: %r" % text)
    check("보이는 글" not in text, "보이는 글은 안 섞인다")


def test_BOUNDARY_returned_urls_are_already_encoded():
    # **결함이었던 곳.** `safe_url` 을 만들어 두고 `image_urls` 에서 안 불렀다.
    # 문서에는 "인코딩해 둔다" 고 적혀 있는데 실제 CSV 에는 공백이 든 주소가 나갔다.
    # 다듬는 함수가 있는 것과 그것이 실제로 쓰이는 것은 다르다.
    page = wrap('<img src="https://x.test/data/플렉스지 유지보수 개발(사람인).jpg">')
    got = body.image_urls(page)[0]
    check(" " not in got, "공백이 남으면 받는 쪽이 터진다: %s" % got)
    check("플렉스" not in got, "한글도 인코딩돼야 한다: %s" % got)


def test_BOUNDARY_proxy_url_keeps_its_nested_address_usable():
    # 사람인 CDN 이 다른 주소를 질의로 감싸 온다. 질의 안의 `://` 와 `/` 를 인코딩하면
    # 프록시가 원래 주소를 못 읽는다.
    page = wrap('<img src="https://www.saraminimage.co.kr?url=http://a.test/b/대지-1.png">')
    got = body.image_urls(page)[0]
    check(got.startswith("https://www.saraminimage.co.kr?url=http://a.test/b/"),
          "질의 안의 주소 모양은 지켜야 한다: %s" % got)
    check("대지" not in got, "한글 파일명은 인코딩한다: %s" % got)


def test_BOUNDARY_encoding_is_idempotent():
    # 두 번 다듬어도 같아야 한다. 아니면 실행할 때마다 CSV 가 달라진다.
    page = wrap('<img src="https://x.test/a b.png">')
    once = body.image_urls(page)[0]
    check_equal(body.safe_url(once), once, "다시 다듬어도 그대로여야 한다")


def test_BOUNDARY_legal_url_characters_are_left_alone():
    # **꼭 필요한 것만 바꾼다.** 경로에서 원래 써도 되는 글자까지 인코딩하면
    # 멀쩡하던 주소가 매 실행 달라 보인다 — 실제로 안 고쳐도 될 3장을 건드렸다.
    for url in ("https://x.test/a/Forward+Deployed+Engineer(FDE).jpeg",
                "https://x.test/a.jpeg%20alt=",
                "https://x.test/%5B%EC%97%90%5D.jpeg",
                "https://x.test/a,b;c=d:e@f/g.png"):
        check_equal(body.safe_url(url), url, "멀쩡한 주소를 바꾸면 안 된다: %s" % url)
