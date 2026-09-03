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
    """블록리스트는 소문자로 모은다 — `SaaS` 와 `saas` 가 갈리면 반쪽만 걸린다."""
    assert "saas" in dictionaries.blocklist()
    assert "ir" in dictionaries.blocklist()
