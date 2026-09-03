# job-helper

여러 채용 사이트에서 **같은 스키마의 CSV** 를 뽑는 수집 파이프라인.

사이트마다 API 도 코드표도 다르지만, 결과물은 한 벌로 합쳐 볼 수 있어야 한다.
그래서 사이트가 공유하는 계층(`job_sites/_common/`)을 두고, 사이트는 자기 응답 구조를
푸는 코드만 짠다.

## 결과물

```
기업명, 마감일, 지원자격, 우대사항, 경력, URL, 연봉, 기술스택, 근무지, 사이트명, 최초수집일, 최종확인일
```

주기로 돌리는 것을 전제로 한다. **덮어쓰지 않고 쌓는다** — 공고 URL 을 키로 병합하고,
마감돼 내려간 공고도 30일까지 남긴다. `최초수집일` 로 오늘 새로 뜬 것을,
`최종확인일` 로 지금도 열려 있는지를 가린다.

## 지금 상태

| 사이트 | |
|---|---|
| `wanted` | 구현됨 |
| `saramin` `job_korea` `jumpit` `job_planet` `pathsdog` | 예정 |

## 실행

```bash
# 저장소 루트에 .env 를 직접 만든다. 항목은 사이트 README 에 있다.
# .env 는 추적되지 않고 예시 파일도 없다 — 없으면 안 도는 것이 맞다.
$EDITOR .env

cd job_sites/wanted
python3 wanted.py        # 수집 → csv/wanted_post.csv
python3 tests/run.py     # 테스트 88건
```

`requests` `tqdm` `python-dotenv` 가 필요하다.

## 문서

| | |
|---|---|
| [docs/convention/](docs/convention/) | **수집 규약.** 새 사이트를 붙일 때 여기부터 읽는다 |
| [docs/convention/03-adding-a-site.md](docs/convention/03-adding-a-site.md) | 새 사이트 체크리스트 |
| [docs/convention/06-decisions.md](docs/convention/06-decisions.md) | 결정 12건과 실측 근거 |
| [job_sites/_common/README.md](job_sites/_common/README.md) | 사이트 공통 계층 |
| [job_sites/wanted/README.md](job_sites/wanted/README.md) | Wanted 스크래퍼 · 코드표 |
