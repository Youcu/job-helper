"""여러 직군이 섞인 공고를 **글자만 보고** 후보로 고르는 일. 그물도 모델도 안 탄다."""
from __future__ import annotations

import role_words
from _common.sections import VALUES_HEADING


def _row(title: str) -> dict:
    return {"공고명": title}


def test_NORMAL_a_multi_role_title_is_a_candidate():
    assert role_words.looks_mixed(_row("[NARA SPACE] 각 부문별 직원모집"))
    assert role_words.looks_mixed(_row("2026년 3분기 분야별 공개채용"))
    assert role_words.looks_mixed(_row("[(주)위로보틱스] 2026년 하반기 각 부문 수시채용"))


def test_NORMAL_an_ordinary_title_is_not():
    for title in ("백엔드 개발자 (전환형 인턴)", "신입 Nest/Spring 백엔드 개발자 모집",
                  "[의료IT] 2026년 직업계고 신입 개발자", "서버개발자 채용"):
        assert not role_words.looks_mixed(_row(title)), title


def test_NORMAL_spacing_does_not_matter():
    """회사가 띄어쓰기를 어떻게 하든 같은 말이다."""
    for title in ("각부문 채용", "각 부문 채용", "부문별 채용", "부문 별 채용"):
        assert role_words.looks_mixed(_row(title)), title


def test_BOUNDARY_one_common_word_is_not_enough():
    """`모집부문` 한 번은 **표의 열 이름**이라 흔하다 — 실측 682건 중 145건(21%)."""
    assert not role_words.looks_mixed(_row("평범한 공고"), "모집부문 상세내용 백엔드")


def test_BOUNDARY_one_rare_word_is_enough():
    """**드문 말에 2회 기준을 걸면 아무것도 안 걸린다.**

    실측(2026-09-18, 본문 682건) — `채용부문` 은 1회 이상이 8건인데 **2회 이상은
    0건**이다. `채용분야` 12/0 · `모집직무` 7/3 · `부문 안내` 2/0 도 같다.
    이 말을 쓰면 대개 진짜 통합 공고다.

    실제로 `[안랩] 2026년 연구소 상시채용`(기술 45개짜리 통합 공고)이 `채용부문`
    을 한 번 쓰고 그대로 빠져나갔다.
    """
    assert role_words.looks_mixed(_row("평범한 공고"), "채용부문 안내 SW 개발(Windows)")
    assert role_words.looks_mixed(_row("평범한 공고"), "채용분야 서버 개발")
    assert role_words.looks_mixed(_row("평범한 공고"), "모집직무 백엔드")


def test_BOUNDARY_a_common_word_twice_is_still_enough():
    """흔한 말은 두 번부터 — 실측 682건 중 46건으로 줄어든다."""
    assert role_words.looks_mixed(_row("평범한 공고"), "모집부문 A 모집부문 B")


def test_BOUNDARY_several_body_mentions_are():
    """제목에 부문 낱말이 없는 통합 공고를 여기서 줍는다 — `[안랩] 2026 연구소 집중 채용`."""
    body = "기술부문 모집부문 상세내용 A ... 사업부문 모집부문 상세내용 B"
    assert role_words.looks_mixed(_row("평범한 공고"), body)


def test_BOUNDARY_the_reason_says_which_signal_caught_it():
    """**왜 물어봤는지 못 되짚으면 규칙을 못 고친다.** 리포트에 그대로 실린다."""
    got = role_words.looks_mixed(_row("각 부문별 채용"), "모집부문 A 모집부문 B")
    assert any("제목" in one for one in got), got
    assert any("본문" in one for one in got), got


def test_BOUNDARY_the_same_word_twice_is_counted_once():
    got = role_words.title_hits("각 부문 채용 · 각 부문 모집")
    assert got == ["각 부문"], got


def test_BOUNDARY_an_empty_row_does_not_crash():
    assert role_words.looks_mixed({}) == []
    assert role_words.looks_mixed({"공고명": None}, None) == []


def test_BOUNDARY_a_parenthesised_list_is_not_chopped():
    """**쉼표로만 가르면 괄호 안의 쉼표까지 갈라 조각이 난다.**

    실측(2026-09-18) 후보 파일에 `AWS(ECS` · `Cognito)` · `Python (FastAPI` ·
    `aiohttp)` 같은 것이 30개 쌓였다. 결과가 더러워지지는 않았다 — 흰 목록이
    어차피 버린다. 문제는 **진짜 이름을 놓친다**는 것이다.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "job_sites"))
    from _common.skills import split_names

    assert split_names("AWS(ECS, Cognito), Spring") == ["AWS", "ECS", "Cognito", "Spring"]
    assert split_names("Python (FastAPI, Django)") == ["Python", "FastAPI", "Django"]
    assert split_names("C#, C++, Node.js") == ["C#", "C++", "Node.js"]
    assert split_names("Opensearch(ElasticSearch)") == ["Opensearch", "ElasticSearch"]


def test_BOUNDARY_a_version_number_is_not_part_of_the_name():
    """**판마다 사전에 한 줄씩 더하는 것은 끝이 없다** — `React 18` 이 오면 또 더해야
    한다. 판은 이름이 아니라 이름에 붙는 꼬리다 (2026-09-18 사용자 지적).

    붙어 있으면 그게 이름이다 — `S3` · `Vue3` 는 안 건드린다.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "job_sites"))
    from _common.skills import known

    assert known("React 19") == "React"
    assert known("NestJS 8") == "NestJS"
    assert known("Java 17") == "Java"
    assert known("Spring Boot 3") == "Spring Boot"
    assert known("S3") == "Amazon S3", "붙어 있으면 그게 이름이다"


def test_BOUNDARY_korean_spacing_does_not_matter():
    """별칭에 `C언어` 가 있는데 공고는 `C 언어` 라고 적는다. 띄어쓰기마다 한 줄씩
    더하는 것도 끝이 없다."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "job_sites"))
    from _common.skills import known

    assert known("C 언어") == "C"
    assert known("자바") == "Java"
    assert known("쿠버네티스") == "Kubernetes"


# ── 두 번째 게이트: 절을 못 갈랐는가 ─────────────────────────────────────
#
# 회사가 `자격요건` 이라는 말을 안 쓰면 절 가르기가 아무것도 못 가른다. 실측
# (2026-09-22, `merged_role` 599행 중 23행) — 머리말이 아예 없다 9 · 표 형식이라
# 못 갈랐다 6 · 본문 자체가 없다 4 · 껍데기다 4.
#
# **앞의 15행은 글은 있는데 우리가 못 읽은 것**이고, 규칙을 넓혀도 다음 형태에서 또
# 뚫린다. 그래서 규칙이 못 가르면 이상한 경우로 보고 모델이 직접 읽는다
# (2026-09-22 사용자).

def test_NORMAL_an_empty_qualification_with_a_body_is_a_candidate():
    why = role_words.needs_sections({"지원자격": ""}, "글" * 500, VALUES_HEADING)
    assert why, "후보여야 한다"
    assert "본문" in why, "근거에 본문 길이가 들어가야 한다: %r" % why


def test_NORMAL_a_filled_qualification_is_not_a_candidate():
    assert role_words.needs_sections(
        {"지원자격": "• 대졸 이상"}, "글" * 500, VALUES_HEADING) is None


def test_EXCEPTION_no_body_means_nothing_to_read():
    """**빈 글을 주면 빈 답을 받는다.** 그 빈 답이 "조건이 없다" 로 굳는다.

    본문이 없는 것은 수집기를 고쳐야 하는 별개 문제다 — 여기서 물으면 값만 든다.
    """
    for body in ("", "   ", None):
        assert role_words.needs_sections(
            {"지원자격": ""}, body, VALUES_HEADING) is None, repr(body)


def test_EXCEPTION_a_husk_body_is_not_worth_asking():
    """전형절차·유의사항만 있는 껍데기다. 실측으로 `(주)슈튜` 가 176자였다."""
    husk = "🚀 채용절차 접수기간 : 2026-09-17 … 🛎️ 유의사항 • 입사지원 서류에"
    assert len(husk) < role_words.MIN_BODY, "이 글은 껍데기 기준보다 짧아야 한다"
    assert role_words.needs_sections({"지원자격": ""}, husk, VALUES_HEADING) is None


def test_BOUNDARY_a_values_only_column_still_counts_as_empty():
    """**인재상만 든 칸은 빈 것이다.**

    그림 판독이 인재상을 `지원자격` 칸에 별도 표기로 넣는다. 그것을 "차 있다" 로
    읽으면 진짜 자격요건이 없는 공고가 후보에서 빠져 영영 안 채워진다.
    """
    only_values = "%s\n• 도전을 좋아하시는 분" % VALUES_HEADING
    assert role_words.needs_sections({"지원자격": only_values}, "글" * 500,
                                     VALUES_HEADING), "인재상뿐이면 여전히 후보다"


def test_BOUNDARY_real_requirements_before_the_values_block_are_enough():
    text = "• 대졸 이상\n%s\n• 도전을 좋아하시는 분" % VALUES_HEADING
    assert role_words.needs_sections({"지원자격": text}, "글" * 500,
                                     VALUES_HEADING) is None


# ── 세 번째 게이트: 제목만으로 내 직군인지 아는가 ──────────────────────
#
# **이 단계가 25% 만 검사하고 있었다** (2026-09-23 사용자 지적). `looks_mixed` 는
# 통합 공고를 찾는 자라 **단일 직군 공고를 아예 안 물어봤다.**
#
#     직군 단계 입력 656행 중 물어본 것 163행(25%) · 안 물어본 것 493행(75%)
#
# ## 블랙리스트를 버리고 화이트리스트로 (2026-09-23 사용자)
#
# 처음에는 "다른 직군 낱말이 있으면 묻는다" 로 고쳤다. **그건 열린 집합이라 영원히
# 미완성이다** — `모션 플래닝 엔지니어` · `자율주행 엔지니어` · `AX매니저` ·
# `SW Engineer` 가 그 표를 통째로 빠져나갔다. 직군 이름은 회사마다 새로 지어 붙인다.
#
# **내가 원하는 것은 닫힌 집합이다.** 갈래가 둘뿐이면 `if` 와 `else` 로 끝난다.
#
#     블랙리스트   656행 중 후보 203행 (31%)
#     화이트리스트  656행 중 후보 457행 (70%)

def test_NORMAL_a_title_without_my_role_words_is_a_candidate():
    """**내 직군 낱말이 없으면 무조건 묻는다.** 다른 직군 표에 없어도 그렇다."""
    for title in ("모션 플래닝 엔지니어 (3년 미만)", "자율주행 엔지니어", "SW Engineer",
                  "2026년도 직원 채용 공고", "강남펠리컨랩에서 AX매니저로 함께 성장해요",
                  "보안솔루션 엔지니어 모집"):
        assert role_words.title_unclear({"공고명": title}), title


def test_NORMAL_my_own_role_title_is_not_a_candidate():
    for title in ("백엔드 개발자(신입)", "웹 개발자 Java / Spring 백엔드 채용",
                  "서버개발자 채용", "JAVA 기반 풀스택 웹 개발자 신입/경력 모집",
                  "신입 Nest/Spring 백엔드 개발자 모집"):
        assert role_words.title_unclear({"공고명": title}) is None, title


def test_NORMAL_a_known_foreign_role_is_named_in_the_reason():
    """`FOREIGN_ROLES` 는 이제 **까닭을 적는 자**다 — 후보를 고르지는 않는다.

    `제목에 내 직군 낱말이 없다` 보다 `제목이 다른 직군: 보안` 이 보고에서 쓸모 있다.
    """
    why = role_words.title_unclear({"공고명": "보안솔루션 엔지니어 모집"})
    assert "보안" in why, why
    plain = role_words.title_unclear({"공고명": "2026년도 직원 채용 공고"})
    assert plain == "제목에 내 직군 낱말이 없다", plain


def test_EXCEPTION_a_title_with_both_is_left_alone():
    """**내 직군 낱말이 있으면 안 건다.** `Java 백엔드 / 데이터 엔지니어` 는 내 자리다."""
    for title in ("Java 백엔드 / 데이터 엔지니어", "백엔드·DevOps 엔지니어",
                  "웹개발자 (Android 앱 연동 경험 우대)"):
        assert role_words.title_unclear({"공고명": title}) is None, title


def test_BOUNDARY_only_the_title_is_read():
    """**본문은 안 본다.** 제목은 회사가 **그 자리를 뭐라고 부르는지**를 말한다."""
    row = {"공고명": "백엔드 개발자", "지원자격": "DevOps · 보안 엔지니어와 협업"}
    assert role_words.title_unclear(row) is None, "본문·칸을 보면 안 된다"


def test_BOUNDARY_an_empty_title_is_a_candidate():
    """제목이 비면 **알 수 없는 것**이다 — 아는 척하고 통과시키면 안 된다."""
    for title in ("", "   ", None):
        assert role_words.title_unclear({"공고명": title}), repr(title)
