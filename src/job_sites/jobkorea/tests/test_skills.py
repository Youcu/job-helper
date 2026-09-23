"""기술 이름 뽑기.

여기는 **구조화 소스가 없다** — 산문 매칭이 전부다. 그래서 확인할 것은 두 가지다.
못 찾았을 때 채워 넣지 않는가, 그리고 잡코리아의 전 직군 어휘(운전면허·검도)를
끌어다 쓰지 않는가.
"""
from __future__ import annotations

from lib.skills import extract_skills, find_skills_in_text

from .helpers import body_html, check, check_equal


def test_NORMAL_finds_names_in_prose():
    found = extract_skills("<p>Python 과 Django 로 백엔드를 만듭니다. AWS 배포 경험 우대.</p>")
    for name in ("Python", "Django", "AWS"):
        check(name in found, "%s 를 찾아야 한다: %r" % (name, found))


def test_NORMAL_real_posting():
    found = extract_skills(body_html("49924906"))
    check(isinstance(found, list), "목록이어야 한다")


def test_NORMAL_no_duplicates():
    found = extract_skills("<p>Python Python python</p>")
    check_equal(len(found), len(set(found)), "같은 이름을 두 번 넣지 않는다: %r" % found)


def test_EXCEPTION_empty_input_yields_nothing():
    for value in ("", None, "<div></div>"):
        check_equal(extract_skills(value), [], "빈 입력에 이름을 지어내지 않는다: %r" % value)


def test_EXCEPTION_image_only_body_yields_nothing():
    # 그림은 읽지 않는다 (D-13). 여기서 억지로 채우면 없는 사실을 만든다.
    check_equal(extract_skills('<img src="https://a.co/1.png">'), [],
                "그림만 있는 본문에서 기술을 지어내지 않는다")


def test_BOUNDARY_word_boundary():
    check("Go" not in find_skills_in_text("Google 에서 일했습니다"), "Google 안의 Go 는 아니다")
    check("R" not in find_skills_in_text("REST API 를 설계합니다"), "REST 안의 R 은 아니다")


def test_BOUNDARY_does_not_use_jobkorea_all_industry_vocabulary():
    # 잡코리아 `hard_skill` 표에는 1종보통운전면허·간호사 면허·검도가 들어 있다.
    # 그걸 어휘로 쓰면 IT 공고에서 엉뚱한 말을 기술로 집는다 (그래서 공통 코퍼스를 쓴다).
    found = find_skills_in_text("검도 유단자 우대, 1종보통운전면허 소지자")
    for wrong in ("검도", "1종보통운전면허"):
        check(wrong not in found, "%s 는 기술이 아니다: %r" % (wrong, found))


def test_BOUNDARY_is_pure():
    html = "<p>Python, Java, Kubernetes</p>"
    check_equal(extract_skills(html), extract_skills(html), "같은 입력에 늘 같은 값")
