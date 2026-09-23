# job-helper

다섯 채용 사이트에서 **같은 스키마의 CSV** 를 뽑는 수집 파이프라인.

사이트마다 API 도 코드표도 다르지만, 결과물은 한 벌로 합쳐 볼 수 있어야 한다.
그래서 사이트가 공유하는 계층(`src/job_sites/_common/`)을 두고, 사이트는 자기 응답 구조를
푸는 코드만 짠다.

## 배치

```
job_crawling_ochestrator.py   오케스트레이터. **루트에는 이것과 README 뿐이다**
README.md  requirements.txt

src/            단계 코드와 패키지
  paths.py        저장소 안의 자리를 **한 곳에서** 정한다
  filter.py  role.py  career.py  nuance.py  core_stack.py  history.py  report.py
  filter_words.py  role_words.py  career_words.py      ← 말 규칙 (바뀌는 이유가 다르다)
  jobplanet_rating.py  job_image_process.py
  job_sites/      수집기 다섯과 공용 계층
  image_process/  그림 판독
  templates/      리포트 HTML 틀
docs/           README 가 아닌 문서 (`docs/stages/` 가 단계별 설명)
scripts/        손으로 돌리는 셸
tests/          시험
csv/ cache/ history/ context/   실행이 만든 자료
```

**코드와 산출물을 섞지 않는다.** `csv/`·`cache/`·`history/` 가 뿌리에 있는 이유다 —
`src/` 안에 두면 무엇이 손으로 쓴 것이고 무엇이 만들어진 것인지 `git status` 로 안 갈린다.

## 결과물

```
기업명, 공고명, 마감일, 지원자격, 우대사항, 경력, URL, 연봉, 기술스택, 근무지, 사이트명, 최초수집일, 최종확인일
```

주기로 돌리는 것을 전제로 한다. **덮어쓰지 않고 쌓는다** — 공고 URL 을 키로 병합하고,
마감돼 내려간 공고도 30일까지 남긴다. `최초수집일` 로 오늘 새로 뜬 것을,
`최종확인일` 로 지금도 열려 있는지를 가린다.

다섯이 다 돌면 수집 뒤 단계 넷이 이어서 돈다.

```
csv/merged.csv  ─그림 판독─▶  csv/merged_read.csv  ─거르기─▶  csv/merged_filtered.csv
      ─평점─▶  csv/merged_rated.csv  ─핵심 기술─▶  csv/merged_core.csv
      ─경력─▶  csv/merged_career.csv   ← 최종
                                        └─이력─▶  history/  (누적)
```

**그림 판독** — 사람인·잡코리아 일부는 본문이 그림 한 장이라 `기술스택` 칸에 그림 주소만
남는다(수집은 순수 HTTP 만 하기 때문이다). 그 그림을 읽어 채운 결과가 `merged_read.csv` 다.
[src/image_process/README.md](src/image_process/README.md).

**직군 가리기** — 회사가 여러 자리를 한 공고에 담으면 기술스택은 **전 부문의 합집합**이
되고 지원자격은 **첫 부문 것만** 남는다(나라스페이스 실측: 기술 53개, 자격은 PM 부문 것).
제목·본문 낱말로 그런 공고를 기계가 고르고(실측 8%), 그것만 `claude` 에게 물어 `.env` 의
`JOB_ROLES` 에 맞는 부문만 남긴다. 회사가 공고를 어떻게 쓸지 모르므로 기계로는 못 가른다.
[docs/stages/ROLE.md](docs/stages/ROLE.md).

**거르기** — 같은 공고를 한 행으로 묶고, 정해진 낱말(SI · SM · 병역특례 · 고객사 · 파견 …)이
든 공고를 뺀다. **뺀 것은 전량 `csv/filter_report.csv` 에 이유와 함께 남는다** — 낱말
규칙은 반드시 오탐을 내므로 무엇을 잃었는지 되짚을 수 있어야 한다.
[docs/stages/FILTER.md](docs/stages/FILTER.md).

**평점 거르기** — 잡플래닛에서 회사 평점을 걷어 **2.9 미만 · 평점 없음 · 검색 안 됨**을
뺀다. [docs/stages/RATING.md](docs/stages/RATING.md).

**핵심 기술** — `.env` 의 `CORE_TECH_STACKS` 가 `기술스택` · `지원자격` · `우대사항`
**어느 한 곳에라도** 있는 공고만 남긴다. 세 칸을 다 보는 이유는, **채용 사이트의 검색
조건에는 안 잡히는데 본문에는 적혀 있는 공고가 있기** 때문이다.

**이력** — 파이프라인이 끝나면 `csv/merged_read.csv`(전처리 이전)와
`csv/merged_career.csv`(최종본), 그리고 리포트를 `history/` 에 **누적**하고 사이트별
수집본을 지운다. `./csv` 에는 **이번 실행의 산출물만** 남는다 — 사람이 보고 싶은 것은
지금 돌린 결과이기 때문이다. [docs/stages/HISTORY.md](docs/stages/HISTORY.md).

**화면 그리기** — 마지막으로 최종본을 `csv/report.html` 로 그린다. **CSV 는 분석용이고,
지원할지 말지는 공고를 하나씩 읽어 정하는 일이라** 읽는 화면이 따로 필요하다. 검색·정렬·
기술 거르기·지원 조건 펼치기가 된다. **단계가 아니다** — 그물도 모델도 안 타므로
(D-25), 실패해도 파이프라인을 실패로 만들지 않고 `python3 src/report.py` 로 다시 그린다.
[docs/stages/REPORT.md](docs/stages/REPORT.md).

**앞 단계의 파일은 손대지 않는다.** 네 단계 다 행을 없애므로, 제자리에서 고치면 없어진
행의 원본이 사라진다. 뺀 것은 단계마다 `*_report.csv` 에 이유와 함께 남는다.

## 사이트

| 폴더 | 사이트 | 걷는 방법 |
|---|---|---|
| `src/job_sites/wanted` | 원티드 | 내부 JSON API |
| `src/job_sites/saramin` | 사람인 | 검색 HTML |
| `src/job_sites/jobkorea` | 잡코리아 | 검색 HTML |
| `src/job_sites/jobplanet` | 잡플래닛 | 내부 JSON API. **자체 공고만** — 97%가 잡코리아 중계다 |
| `src/job_sites/jumpit` | 점핏 | 내부 JSON API |

## 실행

**Python 3.10 이상.** CI 가 3.10 과 3.13 양쪽에서 테스트를 돈다.

코드만 보면 3.8 에서도 돌지만(`runlock.py` 의 `unlink(missing_ok=True)` 가 그 하한),
**의존성 셋이 3.10 이상을 요구한다** — `requests` · `python-dotenv` · `Pillow`.
실제 하한은 둘 중 높은 쪽이다.

```bash
# 1) 가상환경과 의존성 — clone 직후 이것부터 한다
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2) 그림 본문을 읽는 데 `claude` CLI 를 쓴다
#    **없으면 거르기·평점·핵심 기술 세 단계가 통째로 안 돈다** — 이미지 판독이
#    실패하면 뒤를 안 부르기 때문이다. csv/merged.csv 까지만 나오고 종료 코드 1 이다.
#    설치: https://claude.com/claude-code  (설치 뒤 `claude` 로 한 번 로그인)

# 3) 저장소 뿌리에 .env 를 직접 만든다. 항목은 아래 "조건" 절에 있다.
#    .env 는 추적되지 않고 예시 파일도 없다 — 없으면 안 도는 것이 맞다.
$EDITOR .env

# 4) 돌린다
.venv/bin/python3 job_crawling_ochestrator.py   # 수집부터 최종본까지 한 번에
.venv/bin/python3 src/job_image_process.py          # 이미 있는 csv/merged.csv 의 그림만 다시
.venv/bin/python3 src/filter.py                     # 이미 있는 csv/merged_read.csv 만 다시 거른다
.venv/bin/python3 src/jobplanet_rating.py           # 평점만 다시 (캐시가 차 있으면 요청 0건)
.venv/bin/python3 src/core_stack.py                 # .env 를 고치고 핵심 기술만 다시 거른다
.venv/bin/python3 src/history.py                    # 이력만 쌓고 사이트 CSV 를 치운다
```

수집은 8~10분이지만 뒤 단계만 다시 돌려 보고 싶을 때가 있다 — 캐시를 지웠을 때, 모델을
바꿔 볼 때, **낱말표나 `CORE_TECH_STACKS` 를 고쳐 몇 건이 빠지는지 보고 싶을 때**.
그래서 단계마다 혼자 도는 명령이 있다. 거르기는 실측 710행에 0.02초다.

**단계를 혼자 돌리면 입력이 낡았는지 물어본다.** 앞 단계를 안 돌린 채 뒤만 돌리면 지난
실행의 데이터로 오늘 결과를 내는데, 그건 터지지 않아서 알아채기 어렵다.

```
merged_read.csv 는 11일 16시간 전 것입니다 (2026-09-01 00:00).
  지금 돌리면 **그때 걷은 데이터**로 결과를 냅니다.
  계속할까요? [y/N]
```

**막지는 않는다** — 중간 단계를 일부러 다시 돌리는 것은 정상 용법이다. 모르고 돌리는
일만 없게 한다. 오케스트레이터가 부를 때는 묻지 않고(방금 앞 단계가 만든 파일이다),
**cron·CI 처럼 터미널이 아닌 자리에서는 묻지 않고 멈춘다** — 물으면 영영 매달린다.
그때는 `--yes` 를 준다.

한 사이트만 돌리려면 그 폴더에서 부른다.

```bash
cd job_sites/wanted
../../.venv/bin/python3 wanted.py       # 수집 → csv/wanted_post.csv
../../.venv/bin/python3 tests/run.py    # 이 사이트 테스트만
```

의존성은 `requirements.txt` 에 **버전이 박힌 채로** 있다 — `requests` `tqdm`
`python-dotenv` `Pillow` 넷뿐이다.

**`.venv` 를 보고 베끼지 마라.** 거기에는 `pandas`·`numpy`·`rapidfuzz` 가 섞여 있는데
추적되는 코드 중 어느 것도 그것들을 import 하지 않는다. 옛 실험이 남긴 것이다.

**`Pillow` 는 선택이 아니다.** 이미지 단계를 안 쓸 사람도 깔아야 한다 — 루트 테스트가
`test_image_*` 를 담고 있어서, 없으면 import 단계에서 통째로 죽는다.

## 조건은 **한 벌**이다

사이트마다 코드 체계가 달라도 사람은 한 번만 적는다. 각 사이트가
`tags/<사이트>_role_map.json` 으로 자기 코드를 찾는다.

```bash
JOB_ROLES=백엔드,웹                # 직무. 이름으로 적는다 (_common/roles.json)
YOE=0                             # 신입=0, N년차=N, 전체=-1
HOME_LOCATIONS=서울,성남시          # 비우면 전국
EMPLOYMENT_TYPES=regular,intern
EDUCATION=                        # 비워 둔다 — 걸면 공고가 3분의 1로 준다
TECH_STACKS=                      # 수집기는 아직 안 건다
CORE_TECH_STACKS=Spring, FastAPI  # **마지막에** 이것이 없는 공고를 뺀다 (아래)
HOPE_ANNUAL_SALARY=               # 아직 안 건다
```

**`TECH_STACKS` 와 `CORE_TECH_STACKS` 는 다른 것이다.** 앞은 수집기가 걷을 때 쓰라고 둔
자리인데 아직 아무 사이트도 안 건다. 뒤는 **다 걷어 온 뒤 마지막에** 거르는 기준이다.

거르는 자리를 뒤로 둔 이유가 있다. 수집기에 걸면 **채용 사이트의 검색 조건에 안 잡히는
공고를 아예 안 걷게 되는데**, 그중에는 지원자격·우대사항에 그 기술이 적혀 있는 공고가
있다. 걷어 두고 마지막에 거르면 `.env` 한 줄을 고치고 `python3 src/core_stack.py` 만 다시
돌리면 된다 — 다시 걷을 필요가 없다.

`Spring` 과 `Spring Boot` 는 **서로를 잡는다.** `Spring Boot` 로 검색하면 잘 안 나와서
`Spring` 이라고 적어 두는데, 공고는 둘 중 아무 쪽으로나 쓰기 때문이다.

같은 항목이 사이트마다 다르게 쓰인다 — 잡플래닛은 학력을 안 걸고, 점핏은 기술을 안 건다.
각 사이트 README 에 무엇을 어떻게 쓰는지 있다.

이미지 판독 단계에는 **손잡이가 따로 셋** 있다. 검색 조건이 아니라 운영값이라 안 적어도
기본값으로 돈다 — 자세한 것은 [src/image_process/README.md](src/image_process/README.md) 에 있다.

```bash
IMAGE_MODEL=                      # 기본 sonnet
IMAGE_CLAUDE_WORKER=              # 기본 4. 동시에 띄울 claude 개수
                                  # 하나가 300~600MB 다 — 코어가 아니라 남은 메모리로 정한다
IMAGE_TIMEOUT=                    # 기본 300초
```

## 테스트

```bash
.venv/bin/python3 tests/run_all.py       # **전부.** 러너 여섯을 차례로 부르고 합계를 낸다
.venv/bin/python3 tests/run.py           # 루트만 (파이프라인 단계들)
cd job_sites/<사이트> && ../../.venv/bin/python3 tests/run.py   # 사이트 하나만
```

**건수는 여기 안 적는다.** 돌리면 묶음별 건수와 합계가 찍힌다. 예전에는 문서에 손으로
적어 뒀는데 전부 틀어졌다 — 문서 824건, 실제 942건. 숫자를 두 곳에서 관리하면 반드시
갈라진다.

네트워크도 `.env` 도 `claude` 도 타지 않는다 — 떠 놓은 실제 응답과 가짜 opener 를 쓰고,
이미지는 Pillow 로 그 자리에서 그린다. **그래서 CI 에서 그대로 돈다**
(`.github/workflows/test.yml`, 3.10 과 3.13 양쪽).

러너가 여섯인 것은 사이트마다 `sys.path` 를 자기 쪽으로 밀기 때문이다 — 한 프로세스에서
이어 부르면 나중 것이 앞 것의 `lib` 를 집는다. `run_all.py` 가 프로세스를 나눠 부른다.

사람인 묶음이 가장 큰 것은 **`_common` 의 테스트가 거기 있기** 때문이다 — 어느 한 사이트에
붙여 두면 그 사이트를 지웠을 때 시험도 같이 사라진다. 루트 묶음에는 파이프라인 단계
다섯(합치기·이미지 판독·거르기·평점·핵심 기술)의 테스트가 들어 있다.

## 문서

| | |
|---|---|
| [docs/stages/ORCHESTRATOR.md](docs/stages/ORCHESTRATOR.md) | 다섯을 병렬로 돌리고 합치는 일 · **종료 코드 계약** |
| [src/image_process/README.md](src/image_process/README.md) | ① 그림 본문을 읽어 채우는 단계 |
| [docs/stages/ROLE.md](docs/stages/ROLE.md) | ② 직군 가리기 — 여러 직군이 섞인 공고에서 내 부문만 |
| [docs/stages/FILTER.md](docs/stages/FILTER.md) | ③ 중복 제거 · 낱말 제외 |
| [docs/stages/RATING.md](docs/stages/RATING.md) | ④ 잡플래닛 평점 게이트 · **차단을 다루는 법** |
| [docs/stages/CORE_STACK.md](docs/stages/CORE_STACK.md) | ⑤ 핵심 기술 거르기 |
| [docs/stages/CAREER.md](docs/stages/CAREER.md) | ⑥ 경력 거르기 — 신입이라 적고 경력을 요구하는 공고 |
| [docs/stages/HISTORY.md](docs/stages/HISTORY.md) | ⑦ 이력 쌓기와 뒷정리 |
| [docs/stages/REPORT.md](docs/stages/REPORT.md) | 최종본을 읽는 화면으로 그리기 — **단계가 아니다** |
| [docs/convention/](docs/convention/) | **수집 규약.** 새 사이트를 붙일 때 여기부터 읽는다 |
| [docs/convention/03-adding-a-site.md](docs/convention/03-adding-a-site.md) | 새 사이트 체크리스트 |
| [docs/convention/06-decisions.md](docs/convention/06-decisions.md) | 결정과 실측 근거 — **새 단계를 만들 기준은 D-25** |
| [src/job_sites/_common/README.md](src/job_sites/_common/README.md) | 사이트 공통 계층 |
| `src/job_sites/<사이트>/README.md` | 그 사이트의 조건·코드표·제약 |
