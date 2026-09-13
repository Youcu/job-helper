"""거르기의 **말 규칙** — 공고를 묶는 키와, 빼는 낱말.

`filter.py` 는 파일을 읽고 쓰고 보고하는 절차라 거의 안 바뀌지만, 여기 규칙은 실제
공고를 보다가 "이건 오탐이다" 를 만날 때마다 손댄다. **바뀌는 이유가 다르므로 시험도
따로 둔다** (`docs/convention/05-testing.md` 의 "제품 모듈 하나에 테스트 파일 하나").

여기 규칙이 틀리면 **행이 조용히 사라진다.** 낱말표가 조금 넓어지면 멀쩡한 공고가
없어지고, 키가 조금 헐거워지면 다른 공고가 하나로 뭉개진다. 둘 다 CSV 행 수만 보고는
알 수 없다. 그래서 여기 테스트는 **"안 지워야 할 것을 지키는가"** 쪽이 더 많다.

낱말 경계 테스트에 쓰는 문자열은 **규칙을 만들 때 안 본 실측 사례**다 — 규칙을 만든
데이터로만 재면 일반화를 확인한 것이 아니다.
"""
from __future__ import annotations

import filter_words
from _common.store import COLUMNS

from .helpers import check, check_equal


def _row(**fields) -> dict:
    row = {c: "" for c in COLUMNS}
    row.update({"기업명": "회사", "공고명": "백엔드 개발자"})
    row.update(fields)
    return row


# ── 일반 ────────────────────────────────────────────────────────────────

def test_NORMAL_company_key_drops_the_legal_form():
    """법인 표기 차이 하나로 **같은 회사가 둘로 갈렸다.**

    실측 710행에서 같은 공고명을 쓴 37개 그룹 중 **27개가 이 표기 차이**였다 —
    `(주)안랩` vs `㈜안랩`, `뱅크웨어글로벌(주)` vs `뱅크웨어글로벌㈜`.
    """
    same = ("(주)안랩", "㈜안랩", "주식회사 안랩", "안랩", " 안 랩 ")
    keys = {filter_words.company_key(name) for name in same}
    check_equal(keys, {"안랩"}, "다섯이 한 회사여야 한다: %r" % keys)


def test_NORMAL_banned_word_is_reported_with_its_surroundings():
    hits = filter_words.banned_words("여러 줄 중에\n고객사 상주 근무가 있습니다\n끝")
    check_equal([name for name, _ in hits], ["고객사"], "낱말")
    check("고객사 상주" in hits[0][1],
          "**근거에 그 자리의 글이 있어야** 오탐을 되짚을 수 있다: %r" % hits[0][1])


def test_NORMAL_key_pairs_company_with_title():
    check_equal(filter_words.key(_row(기업명="(주)안랩", 공고명="백엔드 (신입)")),
                ("안랩", "백엔드신입"), "둘을 함께 본다")


# ── 예외 ────────────────────────────────────────────────────────────────

def test_EXCEPTION_missing_or_blank_names_do_not_crash():
    for value in (None, "", "   "):
        check_equal(filter_words.company_key(value), "", "빈 기업명: %r" % value)
        check_equal(filter_words.title_key(value), "", "빈 공고명: %r" % value)
    check_equal(filter_words.key({}), ("", ""), "칸이 아예 없어도 터지면 안 된다")


def test_EXCEPTION_a_name_that_is_only_a_legal_form_collapses_to_nothing():
    """**빈 키가 나올 수 있다.** 그러면 `filter.py` 가 묶으면 안 된다.

    `(주)` 만 적힌 행과 `주식회사` 만 적힌 행이 같은 회사로 묶이면, 서로 무관한
    공고가 하나로 사라진다. 빈 키를 거르는 일은 `filter.py` 의 몫이고
    (`test_EXCEPTION_blank_key_rows_are_never_merged`), 여기서는 **빈 키가 실제로
    나온다는 사실**을 굳힌다.
    """
    check_equal(filter_words.company_key("(주)"), "", "법인 표기뿐이면 남는 것이 없다")
    check_equal(filter_words.title_key("[]()"), "", "기호뿐이면 남는 것이 없다")


def test_EXCEPTION_text_of_reads_only_the_three_columns():
    # 회사 이름과 지역명이 낱말을 품는다 — `에스아이알소프트`·`넥스에스아이`.
    row = _row(기업명="넥스에스아이(주) SI", 근무지="파견로 3", 기술스택="SI",
               지원자격="Java")
    check_equal(filter_words.banned_words(filter_words.text_of(row)), [],
                "**지정한 세 칸 밖은 보지 않는다**")


# ── 경계 ────────────────────────────────────────────────────────────────

def test_BOUNDARY_SI_inside_an_english_word_is_not_SI():
    # 실측 오탐 후보. 이것들이 걸리면 멀쩡한 공고가 사라진다.
    for word in ("SIEMENS", "SIEM", "SIMPAC", "ASIC", "SSIM", "VLSI설계", "WSI",
                 "Vision", "Design", "Business", "assignment", "Ansible"):
        check_equal(filter_words.banned_words("우대 %s 경험" % word), [],
                    "%s 는 SI 가 아니다" % word)


def test_BOUNDARY_SM_inside_an_english_word_is_not_SM():
    for word in ("ISMS", "HSM", "SMS", "Smart", "Prisma", "LangSmith", "smoothing"):
        check_equal(filter_words.banned_words("우대 %s 경험" % word), [],
                    "%s 는 SM 이 아니다" % word)


def test_BOUNDARY_hangul_glued_to_SI_still_counts():
    # 파이썬의 `\b` 는 한글도 낱말 문자로 봐서 이것들을 **놓친다.** 그래서 안 쓴다.
    for text in ("SI프로젝트 수행", "SI업체 경력자 우대", "SM사업부 3명", "ㆍSI & 차세대"):
        hits = [name for name, _ in filter_words.banned_words(text)]
        check(hits, "«%s» 는 걸려야 한다" % text)


def test_BOUNDARY_lowercase_si_is_not_a_hit():
    # 대소문자를 무시하면 vision·design·business 까지 걸려 실측 110행이 사라졌다.
    check_equal(filter_words.banned_words("si 는 소문자다"), [], "소문자는 안 잡는다")


def test_BOUNDARY_military_spelling_actually_used():
    check(filter_words.banned_words("병역 특례 대상자"), "띄어 써도 걸려야 한다")
    check(filter_words.banned_words("전문 연구 요원 편입"), "전문연구요원도 마찬가지")
    check_equal(filter_words.banned_words("병영 생활관 관리"), [],
                "`병영` 은 `병역` 이 아니다 — 붙잡으면 엉뚱한 공고가 사라진다")


def test_BOUNDARY_interchangeable_symbols_are_the_same_posting():
    """사이트마다 기호를 달리 쓴다. 실측 707행에서 세 쌍이 이것 하나로 갈렸다."""
    same = [
        ("백엔드 개발자 (신입 - 3년)", "백엔드 개발자 (신입 ~ 3년)"),
        ("… (LLM 파이프라인 · 대규모 수집)", "… (LLM파이프라인/대규모 수집)"),
        ("IT 해내는 개발자(마크업) 채용", "[IT] 해내는 개발자(마크업) 채용"),
    ]
    for left, right in same:
        check_equal(filter_words.title_key(left), filter_words.title_key(right),
                    "기호만 다른 같은 공고다: %r vs %r" % (left, right))


def test_BOUNDARY_bracket_contents_still_separate_postings():
    """**괄호는 문자만 지우고 안쪽 글은 남긴다.**

    결함이 될 뻔한 곳: 대괄호를 통째로 떼면 `[인턴] Backend Engineer` 가
    `Backend Engineer` 와 같아져 **다른 자리를 하나로 뭉갠다.** 인턴 자리가 조용히
    사라지는데, 지워진 공고는 있었다는 사실조차 안 남는다.
    """
    for left, right in (("[인턴] Backend Engineer", "Backend Engineer"),
                        ("[신입] Java 개발자", "Java 개발자"),
                        ("[경력] 서버 개발", "[신입] 서버 개발")):
        check(filter_words.title_key(left) != filter_words.title_key(right),
              "**다른 자리다**: %r vs %r" % (left, right))


def test_BOUNDARY_full_width_symbols_normalize_to_half_width():
    # 사람인은 전각을 섞어 쓴다. NFKC 를 안 걸면 같은 공고가 갈린다.
    check_equal(filter_words.title_key("백엔드（신입）"), filter_words.title_key("백엔드(신입)"),
                "전각 괄호")
    check_equal(filter_words.title_key("Ａ개발자"), filter_words.title_key("A개발자"),
                "전각 영문")


def test_BOUNDARY_symbol_rule_does_not_merge_different_levels():
    # 기호를 지운 뒤에도 **글자가 다르면 다른 공고**여야 한다.
    for left, right in (("개발자 3년", "개발자 5년"),
                        ("백엔드 개발자", "프론트엔드 개발자")):
        check(filter_words.title_key(left) != filter_words.title_key(right),
              "%r 과 %r 은 달라야 한다" % (left, right))


def test_BOUNDARY_company_key_does_not_merge_different_companies():
    """**법인 표기를 지운 뒤에도 이름이 다르면 다른 회사**여야 한다.

    여기가 헐거워지면 서로 무관한 회사의 공고가 중복으로 묶여 한쪽이 사라진다.
    """
    for left, right in (("에스아이알소프트", "넥스에스아이"),
                        ("한성컴퓨터", "한성"),
                        ("(주)모아교육그룹", "㈜모아교육")):
        check(filter_words.company_key(left) != filter_words.company_key(right),
              "**다른 회사다**: %r vs %r" % (left, right))
