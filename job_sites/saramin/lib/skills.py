"""사람인 공고에서 기술스택을 뽑는다.

Wanted 와 같은 구조다 — **구조화 태그 ① 과 본문 매칭 ② 를 합친다.** 어느 한쪽도
다른 쪽을 덮지 못한다는 것을 공고 131건으로 재고 정했다.

    ① 구조화 태그만으로 채워짐   85건 (65%)
    ② 본문 매칭만으로 채워짐     94건 (72%)
    ①∪② 최종 채워짐            119건 (91%)
    ① 에만 있는 이름을 가진 공고  79건 (60%)
    ② 에만 있는 이름을 가진 공고  87건 (66%)

## ① 구조화 태그

상세 페이지 아래쪽 `#태그` 목록이다.

    <a href="/zf_user/jobs/list/job-category?cat_kewd=235" ...>#Java</a>

`cat_kewd` 는 사람인의 직무 분류 코드고, 그중 **기술스택 축**(140개)만 골라 쓴다.
같은 목록에 `직무·직업`(백엔드/서버개발)과 `전문분야`(딥러닝, 임베디드)도 섞여 있는데
그건 기술스택이 아니다.

**이름이 아니라 코드로 맞춘다.** Wanted 에서 `GitHub`/`Github`, `PyTorch`/`Pytorch` 처럼
사이트 표기가 흔들리는 것을 겪었다. 코드는 안 흔들린다.

## ② 본문 매칭

본문 `<div class="user_content jobsViewDetail_{rec_idx}">` 의 **보이는 글**만 쓴다.
안 보이는 글을 섞으면 화면에 글자가 하나도 없는 공고에서 기술 61개가 나온다
(`_common/html_text.py` 참고).

## 이 모듈이 안 하는 것

**본문을 잘라 내는 일은 `body.py` 가 한다.** 그림 본문 판정과 그림 주소도 거기 있다.
여기는 "본문 글이 주어졌을 때 기술 이름을 뽑는 일" 만 한다.

**그림은 아무도 여기서 읽지 않는다.** 읽는 것은 수집이 끝난 뒤 도는 별도 단계의 일이다
(D-13). 그래서 이 모듈은 네트워크도 외부 호출도 타지 않고, 같은 입력에 늘 같은 값을 낸다.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from _common.normalize import canonical
from _common.skills import build_matcher

from .body import visible_body

TAGS_DIR = Path(__file__).resolve().parent.parent / "tags"
SKILL_FILE = TAGS_DIR / "saramin_skill.json"

# 상세 아래쪽 `#태그` 링크. 여기서 cat_kewd 코드를 얻는다.
CATEGORY_TAG = re.compile(
    r'/zf_user/jobs/list/job-category\?cat_kewd=(\d+)"[^>]*?>#([^<]{1,40})</a>'
)


@lru_cache(maxsize=1)
def _tech_codes() -> dict[str, str]:
    """기술스택 코드 → 사람인 표기 이름."""
    data = json.loads(SKILL_FILE.read_text(encoding="utf-8"))
    return {entry["code"]: entry["name"] for entry in data["tech"]}


@lru_cache(maxsize=1)
def _matcher():
    return build_matcher(site_terms=list(_tech_codes().values()))


def clear_caches() -> None:
    """사전을 다시 읽게 한다. 테스트가 파일을 갈아 끼울 때 쓴다."""
    _tech_codes.cache_clear()
    _matcher.cache_clear()


def structured_skills(page: str) -> list[str]:
    """① `#태그` 중 기술스택 축만 골라 표준 이름으로."""
    codes = _tech_codes()
    found = []
    for code, _label in CATEGORY_TAG.findall(page or ""):
        if code in codes:
            found.append(canonical(codes[code]))
    return _unique(found)


def find_skills_in_text(text: str) -> list[str]:
    """② 산문에서 기술 이름 찾기. 엔진은 `_common` 것을 그대로 쓴다."""
    return _matcher().find(text or "")


def extract_skills(page: str) -> list[str]:
    """①∪② 기술스택. 둘 다 비면 빈 목록 — 채워 넣지 않는다.

    **③(이미지 판독)은 여기 없다.** 수집이 끝난 뒤 도는 별도 단계의 일이다.
    이 함수는 순수해서 같은 입력에 늘 같은 값을 낸다.
    """
    return _unique(structured_skills(page) + find_skills_in_text(visible_body(page)))


def _unique(names: list[str]) -> list[str]:
    """순서를 지키며 중복을 없앤다. 빈 이름은 버린다."""
    seen: dict[str, None] = {}
    for name in names:
        if name:
            seen.setdefault(name, None)
    return list(seen)
