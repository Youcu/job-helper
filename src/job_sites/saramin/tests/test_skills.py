"""`lib/skills.py` — 사람인 기술스택 추출.

노리는 결함은 셋이다.

1. **축을 안 가리는 것.** `#태그` 에는 기술스택 말고 직무·전문분야도 섞여 있다.
   그걸 걸러 내지 않으면 `백엔드/서버개발` `딥러닝` 이 기술스택 칸에 들어간다.
2. **안 보이는 글을 읽는 것.** 실제 공고 하나에서 화면에 글자가 하나도 없는데 61개가 나왔다.
3. **없는 것을 채우는 것.** 본문이 이미지면 ② 는 아무것도 못 낸다. 그때는 비워야 한다.
"""
from __future__ import annotations

from lib import skills
from tests.helpers import body, check, check_equal, detail_pages, page, tag_link

JAVA = "235"        # 기술스택 축
PYTHON = "272"      # 기술스택 축
BACKEND = "84"      # 직무·직업 축 — 기술스택이 아니다
NOT_A_CODE = "99999999"


# ─────────────────────────────── 일반 ───────────────────────────────

def test_NORMAL_structured_tags_are_read_by_code():
    html = body("<p>본문</p>") + tag_link(JAVA, "Java") + tag_link(PYTHON, "Python")
    check_equal(skills.structured_skills(html), ["Java", "Python"],
                "기술스택 코드는 표준 이름으로 나와야 한다")


def test_NORMAL_text_matching_finds_names_in_prose():
    html = body("<p>Java 와 Kubernetes 를 씁니다</p>")
    found = skills.extract_skills(html)
    check("Java" in found and "Kubernetes" in found, "산문에서도 찾아야 한다: %r" % found)


def test_NORMAL_two_sources_are_merged_without_duplicates():
    html = body("<p>Java 경험</p>") + tag_link(JAVA, "Java") + tag_link(PYTHON, "Python")
    check_equal(skills.extract_skills(html), ["Java", "Python"],
                "양쪽에 다 있는 이름이 두 번 나오면 안 된다")


def test_NORMAL_real_posting_merges_both_sources():
    """두 경로(①태그 ②산문)를 합친 결과가 실제 공고에서 어떻게 나오나.

    **2026-09-14 에 달라진 것** — 기술이 아닌 말을 corpus 에서 걷어 내자, 이 픽스처
    셋에서 **산문 경로의 기여가 0 이 됐다.** 정리 전에 산문이 더하던 유일한 이름이
    `웹 개발` 이었다 — 기술이 아니었다.

    합치기 자체는 그대로 둔다. 산문 경로는 **태그를 안 붙인 공고를 위한 것**이고,
    이 픽스처 셋이 마침 태그가 풍부할 뿐이다. 다만 **"산문이 늘 뭔가를 더한다" 는
    말은 이제 이 픽스처로 증명되지 않는다** — 그래서 그 단언을 뺀다.
    """
    fixture = detail_pages()["52783795"]
    check(set(fixture["structured"]), "① 태그에서 이름이 나와야 한다")
    check_equal(skills.extract_skills(fixture["page"]), fixture["final"],
                "실제 공고의 최종 결과")


def test_BOUNDARY_non_tech_names_never_reach_the_output():
    """**기술이 아닌 말은 어느 경로로도 안 들어온다** (2026-09-14 사용자).

    막을 자리가 둘이다. 산문은 `_searchable` 이 차단을 보고, **태그는 오래 안 봤다** —
    그래서 `풀스택` 이 사람인 코드표(2232·347건)를 타고 그대로 들어왔다.
    """
    from _common.skills import blocked

    for name in ("풀스택", "컨테이너", "웹 개발", "DevOps", "ORM", "딥러닝", "SDLC"):
        check(blocked(name), "차단돼야 한다: %s" % name)
    for name in ("Docker", "Java", "Spring Boot", "PyTorch"):
        check(not blocked(name), "막으면 안 된다: %s" % name)
    # 실제 공고의 결과에도 없어야 한다
    got = skills.extract_skills(detail_pages()["52783795"]["page"])
    check(not [n for n in got if blocked(n)], "결과에 남았다: %r" % got)


# ─────────────────────────────── 예외 ───────────────────────────────

def test_EXCEPTION_non_tech_axis_codes_are_rejected():
    html = body("<p>x</p>") + tag_link(BACKEND, "백엔드/서버개발")
    check_equal(skills.structured_skills(html), [],
                "직무 코드가 기술스택 칸에 들어가면 안 된다")


def test_EXCEPTION_unknown_code_is_ignored_not_guessed():
    html = body("<p>x</p>") + tag_link(NOT_A_CODE, "Java")
    check_equal(skills.structured_skills(html), [],
                "코드표에 없는 코드는 이름이 그럴듯해도 버린다")


def test_EXCEPTION_label_text_is_not_trusted_only_the_code():
    # 사이트가 표기를 바꿔도(`Github`→`GitHub`) 코드가 같으면 같은 기술이다.
    html = body("<p>x</p>") + tag_link(JAVA, "자바스크립트아님")
    check_equal(skills.structured_skills(html), ["Java"],
                "이름이 아니라 코드로 풀어야 한다")


def test_EXCEPTION_hidden_seo_block_does_not_become_skills():
    # 실제로 61개가 나왔던 모양. 화면에는 글자가 하나도 없다.
    hidden = ('<td style="display:block; height:0; width:0; font-size:0; overflow:hidden;">'
              'IT개발·데이터 &gt; 기술스택 &gt; Java Python Kubernetes Docker AWS</td>')
    html = body('<table><tr><td><img src="a.png"></td></tr><tr>' + hidden + "</tr></table>")
    check_equal(skills.extract_skills(html), [],
                "안 보이는 글에서 기술을 만들어 내면 안 된다")


def test_EXCEPTION_empty_page_does_not_crash():
    for value in ("", None):
        check_equal(skills.extract_skills(value or ""), [], "빈 입력")
        check_equal(skills.structured_skills(value or ""), [], "빈 입력")


def test_EXCEPTION_unclosed_body_container_reads_to_the_end():
    html = '<div class="user_content jobsViewDetail_9"><p>Java 를 씁니다</p>'
    check("Java" in skills.extract_skills(html),
          "닫는 태그가 없어도 본문을 버리지 않는다")


# ─────────────────────────────── 경계 ───────────────────────────────

def test_BOUNDARY_image_only_body_yields_nothing_from_text():
    fixture = detail_pages()["54459386"]
    check(fixture["image_body"], "이 공고는 본문이 이미지다")
    check_equal(fixture["in_text"], [], "이미지 본문에서 산문 매칭은 아무것도 못 낸다")
    check(fixture["structured"], "그래도 ① 이 메운다")


def test_BOUNDARY_both_sources_empty_stays_empty():
    fixture = detail_pages()["54645542"]
    check_equal(skills.extract_skills(fixture["page"]), [],
                "채울 게 없으면 비워 둔다. 지어내지 않는다")


def test_BOUNDARY_duplicate_tag_links_collapse():
    html = body("<p>x</p>") + tag_link(JAVA, "Java") * 3
    check_equal(skills.structured_skills(html), ["Java"], "같은 코드가 여러 번 나와도 하나다")


def test_BOUNDARY_tag_order_is_preserved():
    html = body("<p>x</p>") + tag_link(PYTHON, "Python") + tag_link(JAVA, "Java")
    check_equal(skills.structured_skills(html), ["Python", "Java"],
                "나온 순서를 지킨다 — 정렬은 CSV 를 쓰는 쪽이 정한다")


def test_BOUNDARY_structured_comes_before_text_matches():
    html = body("<p>Kubernetes 경험</p>") + tag_link(JAVA, "Java")
    check_equal(skills.extract_skills(html)[0], "Java",
                "회사가 직접 고른 ① 이 앞에 온다")


def test_BOUNDARY_every_vocabulary_name_resolves_to_the_common_corpus():
    # 140개 중 하나라도 표준 이름으로 안 풀리면 사이트마다 표기가 갈린다.
    from _common import dictionaries
    from _common.normalize import canonical

    from _common.skills import blocked

    corpus = dictionaries.corpus()
    # **차단된 이름은 예외다.** 사람인 코드표에는 `풀스택`(2232·347건)처럼 기술이
    # 아닌 것이 섞여 있다. corpus 에서 뺐으므로 여기서도 안 풀리는 것이 맞고,
    # `blocked()` 가 태그 경로에서 걸러 낸다 (2026-09-14).
    unresolved = [name for name in skills._tech_codes().values()
                  if canonical(name).lower() not in corpus and not blocked(name)]
    check_equal(unresolved, [], "공통 코퍼스로 안 풀리고 차단도 안 된 사람인 어휘")


def test_EXCEPTION_clear_caches_reloads_the_vocabulary():
    skills.clear_caches()
    check(skills._tech_codes(), "사전을 다시 읽어야 한다")


# ────────────────── 그림 주소 (읽지는 않는다) ──────────────────
#
# 수집은 주소만 남긴다. 읽는 것은 수집이 끝난 뒤 도는 **별도 단계**의 일이다.


def test_BOUNDARY_skills_are_found_inside_nested_divs():
    # 본문 자르기는 body.py 가 하지만, 그 결과로 기술이 실제로 잡히는지는 여기서 본다.
    check("Java" in skills.extract_skills(body("<div><div><p>Java 를 씁니다</p></div></div>")),
          "겹친 div 안의 글에서도 찾아야 한다")


# ── 공통으로 올린 것 ──────────────────────────────────────────────────────
# 잡코리아·잡플래닛·점핏이 똑같은 세 줄(`_matcher`/`clear_caches`/`find_skills_in_text`)을
# 각자 쓰고 있었다. **`_common` 시험은 사람인에 둔다** — 세 사이트가 함께 쓰는 코드라
# 어느 한 사이트에 붙여 두면 그 사이트를 지웠을 때 시험도 같이 사라진다.


def test_NORMAL_corpus_matcher_finds_names():
    from _common.skills import find_in_corpus
    found = find_in_corpus("Java 와 Spring Boot 로 백엔드를 만듭니다")
    check("Java" in found and "Spring Boot" in found, found)


def test_EXCEPTION_corpus_matcher_handles_empty_text():
    from _common.skills import find_in_corpus
    for value in ("", None, "   ", "가나다라마바사"):
        check_equal(find_in_corpus(value), [], "빈 입력에 이름을 지어내지 않는다: %r" % value)


def test_BOUNDARY_build_matcher_without_site_terms():
    # 쓸 만한 사이트 어휘가 없는 사이트는 비워 둔다. corpus 는 어차피 안에서 더한다 —
    # `site_terms=corpus_names()` 로 넘기면 같은 목록을 두 번 넣는 셈이었다.
    from _common.skills import build_matcher
    check(build_matcher().find("Python 개발자"), "어휘를 안 넘겨도 corpus 로 찾는다")


def test_BOUNDARY_corpus_matcher_is_cached_and_clearable():
    from _common.skills import clear_corpus_matcher, corpus_matcher
    first = corpus_matcher()
    check(corpus_matcher() is first, "같은 매처를 돌려줘야 한다 (사전 세 벌을 다시 안 읽는다)")
    clear_corpus_matcher()
    check(corpus_matcher() is not first, "비운 뒤에는 새로 만들어야 한다")
    check_equal(corpus_matcher().find("Java"), first.find("Java"), "결과는 같아야 한다")
