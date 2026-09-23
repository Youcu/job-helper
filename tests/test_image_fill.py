"""읽어 낸 것을 행에 채운다. **덮지 않고 보강한다.**

그림 공고인데 자격요건이 이미 차 있는 경우가 있다(29건 중 6건). 사람인 모집조건 표에서 온
값이라 성격이 다르다 — 학력·경력 조건이다. 덮어쓰면 그것을 잃고, 통째로 이으면 같은 말이
두 번 들어간다. 그래서 **없는 것만 더한다.**

편집거리는 안 쓴다(D-04). `REST`/`Rust` 를 같은 것으로 볼 위험이 여기서도 같다.
애매하면 더하는 쪽으로 기운다 — 중복은 거슬리는 정도지만, 빠뜨린 자격요건은 그 공고를
잘못 판단하게 만든다.
"""
from __future__ import annotations

from image_process import fill

from .helpers import check, check_equal


def _row(**fields) -> dict:
    row = {"기업명": "회사", "URL": "https://example.com/1", "사이트명": "jobkorea",
           "기술스택": "https://img/1.png", "지원자격": "", "우대사항": ""}
    row.update(fields)
    return row


def test_NORMAL_tech_column_replaces_the_url():
    got = fill.apply(_row(), {"기술스택": ["Java", "Spring"], "자격요건": [], "우대사항": []})
    check_equal(got["기술스택"], "Java, Spring", "주소를 걷어내고 기술로 바꾼다")


def test_NORMAL_empty_columns_are_filled():
    got = fill.apply(_row(), {"기술스택": [], "자격요건": ["3년 이상"], "우대사항": ["석사"]})
    check("3년 이상" in got["지원자격"], "자격요건: %r" % got["지원자격"])
    check("석사" in got["우대사항"], "우대사항: %r" % got["우대사항"])


def test_NORMAL_existing_text_is_kept_and_extended():
    row = _row(지원자격="• 신입 / 경력 (연수 무관)\n• 대학교졸업(4년)이상")
    got = fill.apply(row, {"기술스택": [], "자격요건": ["AWS 운영 경험 1년 이상"], "우대사항": []})
    check("대학교졸업(4년)이상" in got["지원자격"], "기존을 지켜야 한다")
    check("AWS 운영 경험 1년 이상" in got["지원자격"], "새 것을 더해야 한다")


def test_NORMAL_original_row_is_not_mutated():
    row = _row()
    fill.apply(row, {"기술스택": ["Java"], "자격요건": [], "우대사항": []})
    check_equal(row["기술스택"], "https://img/1.png", "원본을 고치면 안 된다")


def test_EXCEPTION_identical_item_is_not_added_twice():
    row = _row(지원자격="• 대학교졸업(4년)이상")
    got = fill.apply(row, {"기술스택": [], "자격요건": ["대학교졸업(4년)이상"], "우대사항": []})
    check_equal(got["지원자격"].count("대학교졸업"), 1, "같은 말은 한 번만: %r" % got["지원자격"])


def test_EXCEPTION_item_already_inside_the_existing_text_is_skipped():
    # 겹쳐 자른 조각에서 같은 줄이 두 번 나오는 것을 여기서 걸러 준다.
    row = _row(지원자격="• AWS 인프라 운영 경험이 1년 이상 5년 미만이신 분")
    got = fill.apply(row, {"기술스택": [], "자격요건": ["AWS 인프라 운영 경험"], "우대사항": []})
    check_equal(got["지원자격"].count("AWS"), 1, "이미 든 말은 안 더한다: %r" % got["지원자격"])


def test_BOUNDARY_bullet_and_spacing_differences_are_ignored():
    row = _row(지원자격="- 대학교졸업(4년) 이상")
    got = fill.apply(row, {"기술스택": [], "자격요건": ["• 대학교졸업(4년)이상"], "우대사항": []})
    check_equal(got["지원자격"].count("대학교졸업"), 1, "글머리표·띄어쓰기만 다른 것: %r"
                % got["지원자격"])


def test_BOUNDARY_has_anything_needs_only_one_of_three():
    check(not fill.has_anything({"기술스택": [], "자격요건": [], "우대사항": [], "본문": ""}), "셋 다 비면 없다")
    check(fill.has_anything({"기술스택": ["Java"], "자격요건": [], "우대사항": []}), "기술만 있어도")
    check(fill.has_anything({"기술스택": [], "자격요건": ["3년"], "우대사항": []}), "자격만 있어도")
    check(fill.has_anything({"기술스택": [], "자격요건": [], "우대사항": ["석사"]}), "우대만 있어도")


def test_BOUNDARY_empty_tech_leaves_the_column_blank_not_the_url():
    # 자격요건을 얻어 행은 살아남지만 기술은 못 얻은 경우. **주소는 기술이 아니다.**
    got = fill.apply(_row(), {"기술스택": [], "자격요건": ["3년 이상"], "우대사항": []})
    check_equal(got["기술스택"], "", "주소를 남기면 다음 단계가 기술로 착각한다")


def test_BOUNDARY_blank_and_whitespace_items_are_dropped():
    got = fill.apply(_row(), {"기술스택": ["Java", "", "   "], "자격요건": [], "우대사항": []})
    check_equal(got["기술스택"], "Java", "빈 항목은 버린다")


def test_EXCEPTION_seam_between_unrelated_bullets_is_not_a_match():
    # 서로 다른 두 줄을 통째로 이어 붙여 견주면, 실제로는 없는 문구가 두 줄의
    # 이음매를 걸치고 있다는 이유만으로 "이미 있다" 로 잘못 판정된다.
    row = _row(지원자격="• 자바 스프링부트 우대\n• 3년차 프론트엔드 경험")
    got = fill.apply(row, {"기술스택": [], "자격요건": ["우대 3년차"], "우대사항": []})
    check("우대 3년차" in got["지원자격"],
          "줄 경계를 걸친 것은 원문에 없던 말이다 — 더해야 한다: %r" % got["지원자격"])


def test_BOUNDARY_punctuation_only_item_does_not_count_as_content():
    check(not fill.has_anything({"기술스택": ["..."], "자격요건": [], "우대사항": []}),
          "점만 있는 항목은 내용이 아니다")
    check(not fill.has_anything({"기술스택": ["•"], "자격요건": [], "우대사항": []}),
          "글머리표만 있는 항목도 내용이 아니다")


def test_BOUNDARY_punctuation_only_item_is_not_written_to_empty_column():
    got = fill.apply(_row(), {"기술스택": [], "자격요건": ["•"], "우대사항": []})
    check_equal(got["지원자격"], "",
                "점·글머리표만 있는 항목은 빈 칸에도 쓰면 안 된다: %r" % got["지원자격"])


def test_EXCEPTION_items_are_compared_against_each_other_too():
    """읽어 낸 항목끼리도 견준다. **빈 칸에 채울 때가 구멍이었다.**

    실제로 났다 — `㈜도루코` 는 자격요건이 비어 있어 첫 채우기 경로로 갔는데, 그 경로가
    항목끼리 안 견줘서 띄어쓰기만 다른 두 줄이 다 들어갔다.

        • 실제 운전 가능하신 분(2종 보통 면허 이상)
        • 실제 운전 가능하신 분 (2종 보통 면허 이상)

    한 공고에 모집분야가 여럿이면 모델이 같은 조건을 여러 번 읽어 낸다. 흔한 일이다.
    """
    got = fill.add_missing("", ["실제 운전 가능하신 분(2종 보통 면허 이상)",
                                "실제 운전 가능하신 분 (2종 보통 면허 이상)"])
    check_equal(got.count("실제 운전"), 1, "한 번만 들어가야 한다: %r" % got)


def test_EXCEPTION_items_are_deduped_when_the_base_is_not_empty_either():
    got = fill.add_missing("• 이미 있던 줄", ["새 조건입니다", "새 조건 입니다"])
    check_equal(got.count("새 조건"), 1, "채워진 칸에서도 한 번만: %r" % got)
    check("이미 있던 줄" in got, "기존은 남아야 한다")


def test_BOUNDARY_tech_names_that_normalize_alike_are_all_kept():
    """**기술 이름에는 이 대조를 쓰면 안 된다.**

    `normalize` 는 문장부호를 지우므로 `C` · `C#` · `C++` 이 전부 `c` 가 된다. 문장에는
    안전한 규칙이 기술 이름에서는 서로 다른 언어를 하나로 뭉갠다.
    """
    got = fill.apply(_row(), {"기술스택": ["C", "C#", "C++"], "자격요건": [], "우대사항": []})
    for one in ("C#", "C++"):
        check(one in got["기술스택"], "%s 가 사라졌다: %r" % (one, got["기술스택"]))
    check_equal(len([p for p in got["기술스택"].split(",") if p.strip()]), 3, got["기술스택"])


def test_BOUNDARY_o_is_a_bullet_only_when_a_space_follows():
    """**결함이었다.** `lstrip("•-·※*▪◦o")` 는 문자 집합을 벗기므로 `o` 로 시작하는
    멀쩡한 낱말이 깎였다 — 실측 `oracle 경험` → `racle경험`, `o365 운영` → `365운영`.

    이 값은 "이미 있는 항목인가" 를 견주는 데 쓰인다. 깎인 쪽과 안 깎인 쪽이 달라지면
    **같은 항목이 두 번 들어간다.** 저장되는 글은 멀쩡해서 눈으로는 안 보인다.
    """
    check_equal(fill.normalize("oracle 경험"), fill.normalize("Oracle 경험"),
                "대소문자만 다른 같은 항목이어야 한다")
    check_equal(fill.normalize("o365 운영"), "o365운영", "`o365` 의 o 는 낱말의 일부다")
    check_equal(fill.normalize("OpenStack"), "openstack", "낱말이 깎이면 안 된다")
    check_equal(fill.normalize("o 자바 경험"), "자바경험", "뒤에 공백이 오면 글머리표다")


def test_BOUNDARY_symbol_bullets_are_stripped():
    for marked, bare in (("• Java", "java"), ("- 3년", "3년"), ("※ 필수", "필수"),
                         ("◦ Python", "python"), ("· Go", "go")):
        check_equal(fill.normalize(marked), bare, "%r 의 글머리표" % marked)


def test_BOUNDARY_bullet_only_item_normalizes_to_empty():
    # `_clean` 이 이것으로 "내용이 아닌 것" 을 걸러 낸다.
    for junk in ("•", "-", "· ·", "   "):
        check_equal(fill.normalize(junk), "", "%r 은 내용이 아니다" % junk)


def test_BOUNDARY_blocked_names_from_the_image_never_enter():
    """**그림에서 읽은 이름도 차단을 지난다.**

    오래 안 지났다 — 수집기의 두 경로(태그·산문)는 `tech_blocklist.txt` 를 보는데
    여기만 안 봤다. 실측으로 `ORM` 이 그림을 타고 최종본까지 들어왔다
    (2026-09-14, `(주)엔디소프트`). 모델은 공고에 적힌 말을 그대로 읽으므로,
    거기 `ORM`·`풀스택` 이 쓰여 있으면 그대로 가져온다.
    """
    row = {"기술스택": "Java", "지원자격": "", "우대사항": ""}
    got = fill.apply(row, {"기술스택": ["ORM", "Docker", "풀스택", "컨테이너", "JPA"],
                           "자격요건": [], "우대사항": []})["기술스택"]
    names = [one.strip() for one in got.split(",")]
    check_equal(names, ["Java", "Docker", "JPA"], "기술만 남아야 한다: %r" % got)


def test_BOUNDARY_the_row_keeps_its_own_blocked_names():
    """**이미 행에 있던 것은 안 건드린다.** 이 함수의 일은 그림을 더하는 것이다.

    행에 든 것을 여기서 지우면 "무엇이 언제 빠졌나" 를 되짚을 수 없다. 수집기 쪽에서
    이미 막았으므로 새 실행에서는 애초에 안 들어온다.
    """
    row = {"기술스택": "Java, ORM", "지원자격": "", "우대사항": ""}
    got = fill.apply(row, {"기술스택": ["Docker"], "자격요건": [], "우대사항": []})["기술스택"]
    check("ORM" in got, "행에 있던 것은 그대로: %r" % got)


def test_BOUNDARY_what_the_model_read_passes_the_corpus():
    """**그림 판독도 모델이 낸 이름이다.** 차단 목록만으로는 모자랐다 —
    `AI 기반 개발도구` 가 그렇게 최종본까지 들어왔다 (2026-09-18 실측,
    `(주)유비즈` 공고). 공고 본문에 실제로 적힌 말이라 "지어냈다" 도 아니다.

    그런 말은 무한해서 목록으로는 못 따라간다. 아는 이름만 통과시킨다.
    """
    row = {"기술스택": "Java, Spring", "URL": "https://x/1"}
    read = {"기술스택": ["Redis", "AI 기반 개발도구", "ORM", "GCP"],
            "자격요건": [], "우대사항": []}
    got = fill.apply(row, read)["기술스택"]
    check_equal(got, "Java, Spring, Redis, Google Cloud",
                "corpus 가 아는 것만 더해야 한다 (GCP 는 표준 표기로)")


def test_BOUNDARY_what_the_collector_already_had_is_not_re_filtered():
    """**수집기가 넣어 둔 것은 손대지 않는다.** 여기서 하는 일은 *더하는* 것이고,
    이미 있는 값은 그 경로가 제 규칙으로 걸러 놓은 것이다. 여기서 또 거르면
    이 함수가 두 가지 일을 하게 된다.

    그림 주소는 빠진다 — 그건 "아직 안 읽었다" 는 표시였고 방금 읽었기 때문이다.
    """
    row = {"기술스택": "https://img/1.png, 듣도보도못한DB", "URL": "https://x/1"}
    got = fill.apply(row, {"기술스택": [], "자격요건": [], "우대사항": []})["기술스택"]
    check_equal(got, "듣도보도못한DB",
                "이미 있던 값은 그대로 두고, 읽은 뒤의 그림 주소만 뺀다")


# ── 인재상 별도표기 ──────────────────────────────────────────────────────
#
# 인재상은 `지원자격` 칸 안에 머리말과 함께 들어간다 (2026-09-22 사용자). 버리지
# 않는 이유는 분석에 쓰기 때문이고, 섞지 않는 이유는 무엇이 **요구**이고 무엇이
# **바람**인지 갈려야 하기 때문이다.

def test_NORMAL_values_go_under_their_own_heading():
    got = fill.apply(_row(지원자격="• 전문대졸이상"),
                     {"기술스택": [], "자격요건": ["경력 3년이상"], "우대사항": [],
                      "인재상": ["도전을 좋아하시는 분", "협업을 즐기시는 분"]})
    lines = got["지원자격"].split("\n")
    check_equal(lines[0], "• 전문대졸이상", "원래 것이 맨 앞에 남는다")
    check(fill.VALUES_HEADING in lines, "머리말이 들어간다")
    check(lines.index("• 경력 3년이상") < lines.index(fill.VALUES_HEADING),
          "**진짜 자격요건이 인재상보다 앞이다** — 읽는 쪽도 기계도 앞부터 본다")


def test_EXCEPTION_no_values_means_no_heading():
    """**빈 머리말을 남기지 않는다.** 남기면 사람이 내용이 잘렸다고 읽는다."""
    for values in ([], None, ["", "  "]):
        got = fill.apply(_row(지원자격="• 전문대졸이상"),
                         {"기술스택": [], "자격요건": [], "우대사항": [], "인재상": values})
        check(fill.VALUES_HEADING not in got["지원자격"],
              "인재상이 없으면 머리말도 없다: %r" % (values,))


def test_BOUNDARY_running_twice_does_not_stack_the_heading():
    """이 단계는 **매 실행 다시 돈다.** 사람이 결과물을 되먹이는 일도 있다.

    두 번 붙으면 머리말이 쌓이고, 그 칸을 읽는 다음 단계가 같은 인재상을 두 번 본다.
    """
    read = {"기술스택": [], "자격요건": [], "우대사항": [], "인재상": ["도전하시는 분"]}
    once = fill.apply(_row(), read)
    twice = fill.apply(once, read)
    check_equal(twice["지원자격"].count(fill.VALUES_HEADING), 1, "머리말은 한 번뿐")


def test_BOUNDARY_the_heading_is_the_shared_one():
    """**글자를 여기 따로 적어 두면 안 된다.**

    이것을 아는 곳이 셋이다 — 붙이는 `fill`, 지켜야 하는 `role.py`, 보여 주는
    리포트. 각자 적으면 한 곳만 고치는 일이 반드시 생긴다.
    """
    from _common.sections import VALUES_HEADING
    check_equal(fill.VALUES_HEADING, VALUES_HEADING, "공용 자리에서 온 것이다")
