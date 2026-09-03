# 구조 — 무엇이 공통이고 무엇이 사이트 것인가

## 두 층

```
job_sites/
├── _common/          사이트가 공유하는 것. 여기를 고치면 모든 사이트가 바뀐다
└── <사이트>/          그 사이트만의 것
```

경계를 가르는 질문은 하나다.

> **사이트를 하나 더 붙일 때 이 코드를 다시 써야 하나?**

다시 써야 하면 `_common/` 으로 올린다. 그렇지 않으면 사이트 안에 둔다.

## `_common/` 에 있는 것

| 모듈 | 하는 일 |
|---|---|
| `dictionaries.py` | **사전 파일을 읽는 유일한 곳.** 형식을 아는 데가 여기 하나여야 사이트마다 파싱이 복제되지 않는다 |
| `normalize.py` | 기술 이름을 표준 표기로 (`canonical()` `kind_of()`) |
| `skills.py` | 산문에서 기술 이름을 찾는 엔진. 사이트는 **자기 어휘만** 넘긴다 |
| `store.py` | CSV 스키마 12컬럼 · 누적 병합 · 30일 보존 · 원자적 쓰기 |
| `runlock.py` | 실행 락. 겹쳐 도는 실행을 막는다 |

사전 파일(`tech_corpus.json` `tech_aliases.json` `tech_blocklist.txt`
`tech_ko_allowlist.txt`)도 여기 있다. 사이트마다 두면 같은 오탐을 여러 번 고치게 된다.

## 사이트 안에 있는 것

`wanted/` 를 예로 들면 이렇다. **다른 사이트도 같은 모양을 지킨다.**

| 모듈 | 하는 일 | 사이트마다 다른가 |
|---|---|---|
| `wanted.py` | 엔트리포인트. 조건 읽기 → 수집 → 병합 → 저장 | 흐름은 같고 이름만 다르다 |
| `lib/config.py` | `.env` 읽기와 검증 | 항목이 겹치므로 거의 같다 |
| `lib/filters.py` | 수집 조건 → 그 사이트의 API 코드 | **다르다** — 코드표가 사이트마다 다르다 |
| `lib/client.py` | HTTP. 차단 감지·재시도·백오프 | **다르다** — 차단 방식이 사이트마다 다르다 |
| `lib/collect.py` | 목록 페이지네이션과 상세 수집 | **다르다** — 페이지네이션 방식이 다르다 |
| `lib/skills.py` | 그 사이트의 스킬 어휘와 태그 풀이 | **다르다** — 어휘와 응답 구조가 다르다 |
| `lib/record.py` | 응답 → CSV 한 줄 | **다르다** — 필드 이름이 다르다 |
| `tags/` | 그 사이트의 코드표 원본 | **다르다** |
| `fixtures/` | 테스트용으로 떠 놓은 실제 응답 | **다르다** |
| `tests/` | 갈래별 테스트 + `run.py` | 구조는 같다 |

## 사이트가 새로 짤 코드는 얼마나 되나

기술 이름 찾기를 예로 들면, 공통 엔진이 생기기 전에는 **151줄**을 다시 써야 했다.
지금은 **27줄**이다.

```python
# <사이트>/lib/skills.py — 이 정도면 끝이다
from _common.normalize import canonical
from _common.skills import build_matcher

@lru_cache(maxsize=1)
def _matcher():
    return build_matcher(site_terms=_site_skill_names())   # 자기 어휘만 넘긴다

def find_skills_in_text(text: str) -> list[str]:
    return _matcher().find(text)
```

찾는 규칙(단어경계·버전 숫자·짧은 이름·한글 낱말 경계)과 표기 통일은 전부 공통이다.

## import 방향

```
사이트 ──→ _common          (허용)
_common ──→ 사이트          (금지)
```

`_common/` 은 어느 사이트도 몰라야 한다. 안다면 그건 공통이 아니다.

## 실행 경로

```
wanted.py
  ├─ config.load_config()          .env 파일 하나만 읽는다
  ├─ filters.resolve_locations()   한글 → API 코드
  ├─ runlock.run_lock()            겹친 실행 차단
  ├─ collect.fetch_listings()      목록. 끝까지
  ├─ collect.fetch_details()       상세. 병렬
  ├─ record.to_row()               응답 → CSV 한 줄
  ├─ store.merge()                 쌓아 둔 것과 병합 · 30일 보존
  └─ store.write_csv()             원자적 쓰기
```

## 저장소에 들어가지 않는 것

| | 왜 |
|---|---|
| `.env` | 민감 정보를 막으려고 있는 파일이다. **예시 파일도 두지 않는다** — 항목은 사이트 `README.md` 에 적는다 |
| `<사이트>/csv/` | 수집 산출물. 사람마다 스크랩 대상이 다르다 |
| `<사이트>/docs/` | 그 단계를 **만들어 가는 중간 확인용** 문서다. 보는 대상이 만드는 사람과 에이전트라, 완제품을 쓰는 사람에게는 쓸모가 없다 |
| `.venv` · `__pycache__` | 빌드 산물 |

루트 `docs/` 만 추적한다 — 규약은 쓰는 사람에게도 필요하다.
