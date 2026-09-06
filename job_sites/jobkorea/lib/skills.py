"""잡코리아 공고에서 기술 이름을 찾는다.

**여기는 구조화 소스가 없다.** Wanted 는 `skill_tags`, 사람인은 `#태그`(65%)가 받쳐
줬는데, 잡코리아의 `스킬` 필드는 표본 10건 중 **1건**만 채워져 있었고 그마저
`', Lms'` 로 깨져 있었다. 그래서 **산문 매칭이 사실상 전부**다.

    공고 67건 실측 — 본문에서 이름이 잡힌 공고 43건(64%),
    공통 코퍼스로 살아남은 것 42건(63%). 개수 중앙값 3개.

사람인 91% 에 못 미친다. 그림 본문이 24% 라 더 올라가기 어렵다.

## 어휘를 통째로 쓰지 않는 이유

잡코리아가 스킬 코드표를 공개한다 (`hard_skill` 1,158개). 그런데 그것은
**전 직군 어휘**다 — 1종보통운전면허·간호사 면허·건축기사·검도가 섞여 있고,
`자격`·`면허` 로 끝나는 것만 251개다. 공통 코퍼스로 풀리는 것은 217개(19%)뿐이다.

그래서 그 1,158개를 산문 매칭 어휘로 쓰면 IT 공고에서 엉뚱한 말을 기술로 집는다.
**공통 코퍼스를 어휘로 쓴다.** 사이트가 아는데 코퍼스에 없는 이름은
`corpus_candidates` 로 올라가고, 사람이 승인하면 다음 실행부터 잡힌다 (D-14).
"""
from __future__ import annotations

from _common.skills import clear_corpus_matcher, find_in_corpus

from .body import visible_body


def clear_caches() -> None:
    """사전을 다시 읽게 한다. 테스트가 파일을 갈아 끼울 때 쓴다."""
    clear_corpus_matcher()


def find_skills_in_text(text: str) -> list[str]:
    """산문에서 기술 이름 찾기. 엔진은 `_common` 것을 그대로 쓴다."""
    return find_in_corpus(text)


def extract_skills(body_html: str) -> list[str]:
    """본문에서 기술 이름을 뽑는다. 없으면 빈 목록 — 채워 넣지 않는다.

    **그림 판독은 여기 없다.** 수집이 끝난 뒤 도는 별도 단계의 일이다 (D-13).
    이 함수는 순수해서 같은 입력에 늘 같은 값을 낸다.
    """
    seen: dict[str, None] = {}
    for name in find_skills_in_text(visible_body(body_html)):
        if name:
            seen.setdefault(name, None)
    return list(seen)
