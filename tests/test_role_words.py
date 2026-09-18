"""여러 직군이 섞인 공고를 **글자만 보고** 후보로 고르는 일. 그물도 모델도 안 탄다."""
from __future__ import annotations

import role_words


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


def test_BOUNDARY_one_body_mention_is_not_enough():
    """`모집부문` 한 번은 **표의 열 이름**이라 거의 모든 공고에 있다.

    처음에는 본문의 이 낱말을 세려 했는데, 사람인 28건을 실제로 받아 세어 보니
    통합 공고인 한양이엔지도 1회였고 단일 공고도 1회였다 (2026-09-18 실측).
    """
    assert not role_words.looks_mixed(_row("평범한 공고"), "모집부문 상세내용 백엔드")


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
