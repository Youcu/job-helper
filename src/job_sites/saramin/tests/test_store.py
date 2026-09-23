"""병합 결과를 사람이 읽을 줄로 옮기는 일.

**`_common` 의 것을 여기서 시험한다.** 세 사이트가 함께 쓰는 코드라 어느 한 사이트에
붙여 두면, 그 사이트를 지웠을 때 시험도 같이 사라진다.

`save()` 가 돌려주는 값의 짝이라 `store.py` 에 둔다 — 세는 규칙이 바뀌면 찍는 말도
같이 바뀌어야 하는데, 사이트마다 사본을 두면 한 곳만 고치고 지나가기 쉽다.
"""
from __future__ import annotations

from _common.store import RETENTION_DAYS, merge_lines

from .helpers import check, check_equal


class Counts:
    def __init__(self, added=0, updated=0, unseen=0, expired=0, undated=0):
        self.added, self.updated = added, updated
        self.unseen, self.expired, self.undated = unseen, expired, undated


def test_NORMAL_always_shows_new_and_seen_again():
    lines = merge_lines(Counts(added=3, updated=4))
    check_equal(len(lines), 2, "0 인 항목은 줄을 만들지 않는다: %r" % lines)
    check("3건" in lines[0] and "새로 뜬" in lines[0], lines[0])
    check("4건" in lines[1] and "이번에도" in lines[1], lines[1])


def test_NORMAL_shows_every_nonzero_counter():
    text = "\n".join(merge_lines(Counts(1, 2, 3, 4, 5)))
    for word in ("새로 뜬", "이번에도", "안 보인", "넘게 안 보여 뺀", "최종확인일을 알 수 없어"):
        check(word in text, "'%s' 가 빠졌다:\n%s" % (word, text))


def test_BOUNDARY_zero_counters_are_hidden():
    # 늘 찍으면 정상인 실행이 0 으로 가득 차 보여서, 진짜 볼 것이 묻힌다.
    for field in ("unseen", "expired", "undated"):
        lines = merge_lines(Counts(**{field: 0}))
        check_equal(len(lines), 2, "%s 가 0 이면 줄이 없어야 한다: %r" % (field, lines))
        lines = merge_lines(Counts(**{field: 1}))
        check_equal(len(lines), 3, "%s 가 1 이면 줄이 생겨야 한다: %r" % (field, lines))


def test_BOUNDARY_retention_days_appears_in_the_expiry_line():
    # 며칠 만에 빠졌는지 안 적으면, 사라진 공고를 보고 사람이 규칙을 되짚어야 한다.
    text = "\n".join(merge_lines(Counts(expired=2), retention_days=45))
    check("45일" in text, text)
    text = "\n".join(merge_lines(Counts(expired=2)))
    check("%d일" % RETENTION_DAYS in text, "기본값을 쓴다: %s" % text)


def test_BOUNDARY_all_zero_still_reports_the_two_basics():
    lines = merge_lines(Counts())
    check_equal(len(lines), 2, "아무것도 없어도 두 줄은 나온다")
    check("0건" in lines[0], lines[0])


def test_BOUNDARY_lines_are_indented_for_the_summary_block():
    # 요약 블록 안에 들어가는 줄이라 들여쓰기가 어긋나면 눈에 띄게 흐트러진다.
    for line in merge_lines(Counts(1, 2, 3, 4, 5)):
        check(line.startswith("  "), "들여쓰기가 없다: %r" % line)
