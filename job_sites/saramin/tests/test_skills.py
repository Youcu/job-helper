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


def test_NORMAL_real_posting_needs_both_sources():
    # 합치기로 한 근거 자체를 굳힌다 — 한쪽만으로는 부족하다는 실제 사례.
    fixture = detail_pages()["52783795"]
    only_structured = set(fixture["structured"])
    only_text = set(fixture["in_text"])
    check(only_structured - only_text, "① 에만 있는 이름이 있어야 한다")
    check(only_text - only_structured, "② 에만 있는 이름이 있어야 한다")
    check_equal(skills.extract_skills(fixture["page"]), fixture["final"],
                "실제 공고의 최종 결과")


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

    corpus = dictionaries.corpus()
    unresolved = [name for name in skills._tech_codes().values()
                  if canonical(name).lower() not in corpus]
    check_equal(unresolved, [], "공통 코퍼스로 안 풀리는 사람인 어휘")


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
