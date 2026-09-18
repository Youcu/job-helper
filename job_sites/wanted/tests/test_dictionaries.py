"""공유 사전 파일 읽기.

사용자가 직접 고치는 파일들이다 — README 가 "오탐 보이면 blocklist 에 한 줄 추가" 라고
안내하므로 손편집은 일어난다. 지워지거나 잘못 쓰여도 수집은 계속 돌아야 한다.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from _common import dictionaries
from lib import skills


def _with_dict_dir(directory: Path):
    """사전 디렉터리를 잠시 바꿔 끼운다."""
    dictionaries.DICT_DIR = directory
    dictionaries.clear_caches()
    skills.clear_caches()


def _restore(original: Path):
    dictionaries.DICT_DIR = original
    dictionaries.clear_caches()
    skills.clear_caches()


def test_EXCEPTION_missing_dictionary_files_degrade_gracefully():
    """사전 파일이 없어도(부분 체크아웃 등) 크래시 대신 빈 사전으로 돈다."""
    original = dictionaries.DICT_DIR
    try:
        with tempfile.TemporaryDirectory() as empty:
            _with_dict_dir(Path(empty))
            assert dictionaries.corpus() == {}
            assert dictionaries.aliases() == {}
            assert dictionaries.corpus_names() == []
            assert dictionaries.alias_spellings() == []
            assert dictionaries.blocklist() == frozenset()
            assert dictionaries.korean_terms() == {}
            # 공통 사전이 없어도 사이트 어휘만으로 계속 찾는다
            assert "Python" in skills.find_skills_in_text("Python 경험")
    finally:
        _restore(original)


def test_EXCEPTION_hand_edited_dictionary_files():
    """주석만 남기거나 줄을 잘못 써도 버텨야 한다."""
    original = dictionaries.DICT_DIR
    try:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            # 한글 사전에 빈 왼쪽(`= 표준`)과 주석·빈 줄이 섞였다
            (tmp / "tech_ko_allowlist.txt").write_text(
                "# 주석\n\n마이크로서비스\n = 마이크로서비스\n마이크로 서비스 = 마이크로서비스\n",
                encoding="utf-8",
            )
            _with_dict_dir(tmp)
            assert dictionaries.korean_terms() == {
                "마이크로서비스": "마이크로서비스", "마이크로 서비스": "마이크로서비스",
            }
            assert "마이크로서비스" in skills.find_skills_in_text("마이크로 서비스 설계 경험")
    finally:
        _restore(original)


def test_BOUNDARY_blocklist_is_case_insensitive():
    """두 목록 다 소문자로 모은다 — `Lambda` 와 `lambda` 가 갈리면 반쪽만 걸린다."""
    assert "lambda" in dictionaries.blocklist()
    assert "storm" in dictionaries.blocklist()
    assert "saas" in dictionaries.rejected()


def test_BOUNDARY_the_two_lists_mean_different_things():
    """**`blocklist` 와 `rejected` 는 막는 자리가 다르다.** 섞으면 둘 다 망가진다.

    | 파일 | 무엇 | 막는 곳 |
    |---|---|---|
    | `tech_blocklist.txt` | **진짜 기술인데 산문에서 오탐** (`Lambda` · `S3` · `Storm`) | 산문만 |
    | `tech_rejected.txt` | **애초에 기술스택이 아님** (`SaaS` · `풀스택` · `CI/CD`) | 산문 + 태그 |

    태그로 온 `Lambda` 까지 막으면 멀쩡한 기술이 사라지고, 태그로 온 `SaaS` 를 안
    막으면 사업 용어가 기술스택 칸에 남는다. 실측으로 둘 다 겪었다 (2026-09-14).
    """
    from _common.skills import blocked

    for name in ("Lambda", "S3", "Storm", "Docker"):
        assert not blocked(name), "태그로 오면 살려야 한다: %s" % name
    for name in ("SaaS", "풀스택", "CI/CD", "Figma", "컨테이너"):
        assert blocked(name), "태그로 와도 막아야 한다: %s" % name


def test_BOUNDARY_prose_reads_both_lists():
    """**산문은 두 목록을 다 본다.** `rejected` 는 애초에 기술이 아니므로 산문에서도
    잡으면 안 된다.

    이 시험이 없을 때 산문이 `rejected` 를 빼먹어도 아무도 못 잡았다 — 되돌려 보니
    1042건이 그대로 통과했다 (2026-09-14).
    """
    from _common.skills import find_in_corpus

    got = find_in_corpus("SaaS 플랫폼에서 Docker 와 CI/CD 경험, 풀스택 개발")
    assert "Docker" in got, got
    for name in ("SaaS", "CI/CD", "풀스택"):
        assert name not in got, "산문에서 잡히면 안 된다: %s (%r)" % (name, got)


def test_BOUNDARY_a_dropped_comment_marker_is_caught():
    """**설명 줄에서 `#` 이 떨어지면 그 문장이 통째로 한 항목이 된다.**

    실제로 그랬다 — `PowerPoint 는 wanted 작업 때 산문에서 관측돼…` 한 줄이 항목이
    되어, 정작 `PowerPoint` 는 어디에도 없어 안 막혔다 (2026-09-14 실측). 목록이
    길어질수록 눈으로는 안 보인다.

    기술 이름은 짧고, 문장 부호나 조사로 끝나지 않는다. 그것만 본다.
    """
    for name, entries in (("blocklist", dictionaries.blocklist()),
                          ("rejected", dictionaries.rejected())):
        for entry in entries:
            assert not entry.endswith("."), "%s 에 문장이 섞였다: %r" % (name, entry)
            assert len(entry.split()) <= 4, "%s 에 문장이 섞였다: %r" % (name, entry)


def test_BOUNDARY_no_name_sits_in_two_places_at_once():
    """**한 이름이 두 자리를 차지하면 셋 중 하나는 거짓말이다.**

    | 겹침 | 무엇이 틀렸나 |
    |---|---|
    | corpus ∩ rejected | 사전은 "기술이다" 라 하고 차단 목록은 "아니다" 라 한다 |
    | blocklist ∩ rejected | "진짜 기술인데 오탐" 과 "애초에 기술 아님" 을 동시에 주장한다 |
    | 같은 파일 안 중복 | 한 곳만 고치고 지나가면 다른 곳이 남아 조용히 되살아난다 |

    셋 다 실제로 있었다 (2026-09-18 점검). 동작은 안 틀렸다 — 어차피 막히니까.
    **틀린 것은 근거다.** 사전을 읽고 판단하는 다음 사람이 반대 결론을 얻는다.
    """
    import collections
    import json

    corpus = json.loads((dictionaries.DICT_DIR / "tech_corpus.json").read_text("utf-8"))
    names = {tech["name"].lower() for tech in corpus["tech"]}
    blocklist, rejected = dictionaries.blocklist(), dictionaries.rejected()

    assert not names & rejected, "corpus 와 rejected 가 겹친다: %s" % sorted(names & rejected)
    assert not blocklist & rejected, \
        "blocklist 와 rejected 가 겹친다: %s" % sorted(blocklist & rejected)

    for name in ("tech_blocklist.txt", "tech_rejected.txt"):
        lines = [line.strip() for line in (dictionaries.DICT_DIR / name).read_text("utf-8").splitlines()
                 if line.strip() and not line.startswith("#")]
        counted = collections.Counter(line.lower() for line in lines)
        twice = sorted(word for word, times in counted.items() if times > 1)
        # 철자만 다른 것(`GitHub`/`Github`)은 관측 기록이라 남긴다. 똑같은 줄만 잡는다.
        same = sorted(word for word in twice if lines.count(word) > 1 or
                      len({line for line in lines if line.lower() == word}) == 1)
        assert not same, "%s 안에 똑같은 줄이 두 번: %s" % (name, same)


def test_BOUNDARY_the_corpus_header_counts_match_the_entries():
    """`_counts` 는 손으로 적는 값이다 — 항목을 지우고 안 고치면 바로 어긋난다."""
    import collections
    import json

    corpus = json.loads((dictionaries.DICT_DIR / "tech_corpus.json").read_text("utf-8"))
    kinds = collections.Counter(tech["kind"] for tech in corpus["tech"])
    assert corpus["_counts"]["총"] == len(corpus["tech"])
    for kind, times in kinds.items():
        assert corpus["_counts"][kind] == times, "%s: 적힌 값 %s · 실제 %s" % (
            kind, corpus["_counts"].get(kind), times)
