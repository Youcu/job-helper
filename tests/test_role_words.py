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
