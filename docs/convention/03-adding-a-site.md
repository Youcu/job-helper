# 새 사이트 붙이기

`job_sites/saramin/` 같은 빈 자리에 스크래퍼를 만드는 절차다.
`job_sites/wanted/` 를 본보기로 삼되, **베끼지 말고 이 순서를 따른다.**

## 0. 먼저 API 를 찾는다

브라우저 개발자도구로 목록·상세 요청을 찾는다. 확인할 것은 넷이다.

- [ ] **목록 API** 와 페이지네이션 방식 (offset? cursor? page?)
- [ ] **상세 API** 와 그 안에 필요한 필드가 다 있는지
- [ ] **차단 조건** — UA? 쿠키? 토큰? 레이트리밋?
- [ ] **필터 코드표** — 직군·직무·지역을 어떤 코드로 받는지

> Wanted 에서는 목록 API 의 `limit` 이 **최대**지 요구 수량이 아니었고, 페이지가 꽉 차도
> 남은 게 없으면 `links.next` 가 `null` 이었다. **추측하지 말고 직접 찔러 확인한다.**
> 경계에서 어떻게 나오는지 표로 정리해 두면 나중에 페이지네이션 로직의 근거가 된다.

### 상세 API 가 화면과 같은지 확인한다

공고 페이지의 `__NEXT_DATA__` 같은 embedded JSON 과 상세 API 응답을 **여러 건 대조**한다.
Wanted 는 20건 전수에서 본문 7필드가 바이트 단위로 같았다 — 그래서 API 만 쓴다.
다르면 무엇이 부족한지 기록하고 판단한다.

## 1. 디렉터리를 만든다

```
saramin/
├── saramin.py           엔트리포인트
├── lib/
│   ├── __init__.py
│   ├── config.py        .env 읽기 (wanted 것을 거의 그대로 쓸 수 있다)
│   ├── filters.py       수집 조건 → 그 사이트 코드
│   ├── client.py        HTTP. 차단 회피
│   ├── collect.py       페이지네이션 · 상세 수집
│   ├── skills.py        그 사이트 스킬 어휘 + 태그 풀이
│   └── record.py        응답 → CSV 한 줄
├── tags/                코드표 원본
├── fixtures/            테스트용 실제 응답
├── tests/
│   ├── run.py · helpers.py
│   └── test_<모듈>.py
├── csv/                 산출물
└── README.md
```

## 2. `_common/` 에서 가져다 쓴다

**다시 짜지 마라.** 아래는 전부 공통이다.

```python
from _common.normalize import canonical, kind_of
from _common.skills import build_matcher
from _common.store import COLUMNS, RETENTION_DAYS, merge, read_csv, write_csv
from _common.runlock import LockedError, run_lock
```

기술 이름 찾기는 이게 전부다.

```python
# lib/skills.py
@lru_cache(maxsize=1)
def _matcher():
    return build_matcher(site_terms=_site_skill_names())   # 자기 어휘만 넘긴다

def find_skills_in_text(text: str) -> list[str]:
    return _matcher().find(text)
```

## 3. 체크리스트

### 설정
- [ ] `.env` 항목이 기존과 겹치면 **같은 이름**을 쓴다. 사이트마다 다른 이름을 붙이지 않는다
- [ ] 새 항목이 필요하면 **`README.md` 에 적는다.** `.env.example` 은 만들지 않는다
- [ ] `dotenv_values()` 로 **파일만** 읽는다. `load_dotenv()` 는 셸 환경변수가 새어 든다

### 차단 회피
- [ ] 실제 브라우저와 같은 헤더 묶음
- [ ] 세션 하나를 재사용
- [ ] 요청 사이에 지터
- [ ] 차단 응답(403 등)은 **재시도하지 않고 즉시 멈춘다.** 재시도하면 차단만 깊어진다
- [ ] 그때 **무엇을 의심해야 하는지** 메시지에 적는다

### 페이지네이션
- [ ] 끝 판정을 **여러 신호로** 한다 (빈 응답 / 다음 링크 없음 / 새 항목 0건)
- [ ] 서버가 offset 을 무시해 같은 페이지를 반복하면 멈춘다
- [ ] 폭주 방지 상한
- [ ] **종료 사유를 출력한다**
- [ ] 중간에 실패해도 앞서 모은 것을 돌려준다

### CSV
- [ ] `_common/store.py` 의 `COLUMNS` 를 그대로 쓴다. 사이트에 없는 값도 **빈칸으로 남긴다**
- [ ] `사이트명` 을 그 사이트 이름으로 고정
- [ ] `record.to_row()` 는 앞 10칸만. 이력 두 칸은 `merge()` 가 채운다
- [ ] URL 이 없는 응답은 행을 만들지 않는다
- [ ] 기술스택이 하나도 없으면 행을 뺀다. 뺀 개수를 알린다

### 저장
- [ ] `merge()` → `write_csv()`. 덮어쓰지 않는다
- [ ] `run_lock()` 으로 감싼다
- [ ] 신규 / 갱신 / 안 보임 / 만료 건수를 출력한다

### 테스트
- [ ] [05-testing.md](05-testing.md) 를 따른다
- [ ] 코드를 적대적으로 읽고 **먼저 찔러 본 뒤** 테스트를 쓴다
- [ ] 일반 / 예외 / 경계. 예외와 경계가 일반보다 많아야 한다
- [ ] 네트워크를 타지 않는다. 픽스처는 **실제 응답을 떠서** 쓴다
- [ ] 문장 커버리지 100%

### 문서
- [ ] `README.md` — 실행법 · CSV 컬럼 · **`.env` 항목 목록** · **코드표** · 차단 회피 · API
- [ ] 사이트 고유의 함정을 적는다. Wanted 는 UA 하나가 게이트였다

## 4. 공통으로 올려야 할 때

새 사이트를 만들다 **`_common/` 에 있는 것과 같은 코드를 다시 쓰고 있다면**, 그건 공통으로
올려야 한다는 신호다. 복제하지 말고 `_common/` 을 고친다.

반대로 사이트 하나에만 필요한 것을 `_common/` 에 넣지 않는다.
판단 기준은 [01-architecture.md](01-architecture.md) 의 질문 하나다 —
**사이트를 하나 더 붙일 때 이 코드를 다시 써야 하나?**

## 5. 사전은 공유한다

`tech_blocklist.txt` `tech_ko_allowlist.txt` `tech_corpus.json` `tech_aliases.json` 은
사이트가 함께 쓴다. 새 사이트에서 오탐이나 누락을 보면 **`_common/` 의 그 파일**을 고친다.
사이트마다 사본을 두면 같은 오탐을 여러 번 고치게 된다.
