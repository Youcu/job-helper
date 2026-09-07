# job-helper

여섯 채용 사이트에서 **같은 스키마의 CSV** 를 뽑는 수집 파이프라인.

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

여섯이 다 돌면 이어서 `csv/merged_read.csv` 가 하나 더 나온다. 사람인·잡코리아 일부는
본문이 그림 한 장이라 `기술스택` 칸에 그림 주소만 남는데(수집은 순수 HTTP 만 하기
때문이다), 그 그림을 읽어 채운 결과다. `merged.csv` 는 손대지 않는다 — 자세한 것은
[image_process/README.md](image_process/README.md).

## 사이트

| 폴더 | 사이트 | 걷는 방법 |
|---|---|---|
| `job_sites/wanted` | 원티드 | 내부 JSON API |
| `job_sites/saramin` | 사람인 | 검색 HTML |
| `job_sites/jobkorea` | 잡코리아 | 검색 HTML |
| `job_sites/jobplanet` | 잡플래닛 | 내부 JSON API. **자체 공고만** — 97%가 잡코리아 중계다 |
| `job_sites/jumpit` | 점핏 | 내부 JSON API |
| `job_sites/pathsdog` | Pathsdog | **MCP** (JSON-RPC over HTTP) |

## 실행

```bash
# 저장소 뿌리에 .env 를 직접 만든다. 항목은 아래 "조건" 절에 있다.
# .env 는 추적되지 않고 예시 파일도 없다 — 없으면 안 도는 것이 맞다.
$EDITOR .env

python3 job_crawling_ochestrator.py   # 수집부터 이미지 판독까지 한 번에 → csv/merged.csv, csv/merged_read.csv
python3 job_image_process.py          # 이미 있는 csv/merged.csv 의 그림만 다시 처리
```

수집은 8~10분이지만 이미지 판독만 다시 돌려 보고 싶을 때가 있다 — 캐시를 지웠을 때,
모델을 바꿔 볼 때. 그때는 두 번째 명령만 쓰면 된다. 자세한 것은
[image_process/README.md](image_process/README.md).

한 사이트만 돌리려면 그 폴더에서 부른다.

```bash
cd job_sites/wanted
python3 wanted.py            # 수집 → csv/wanted_post.csv
python3 tests/run.py         # 테스트
```

`requests` `tqdm` `python-dotenv` 가 필요하다. 이미지 판독 단계는 **Pillow** 도 쓴다.

```bash
.venv/bin/pip install Pillow
```

## 조건은 **한 벌**이다

사이트마다 코드 체계가 달라도 사람은 한 번만 적는다. 각 사이트가
`tags/<사이트>_role_map.json` 으로 자기 코드를 찾는다.

```bash
JOB_ROLES=백엔드,웹                # 직무. 이름으로 적는다 (_common/roles.json)
YOE=0                             # 신입=0, N년차=N, 전체=-1
HOME_LOCATIONS=서울,성남시          # 비우면 전국
EMPLOYMENT_TYPES=regular,intern
EDUCATION=                        # 비워 둔다 — 걸면 공고가 3분의 1로 준다
TECH_STACKS=                      # 아직 안 건다
HOPE_ANNUAL_SALARY=               # 아직 안 건다
```

같은 항목이 사이트마다 다르게 쓰인다 — 잡플래닛은 학력을 안 걸고, 점핏은 기술을 안 걸고,
Pathsdog 는 근무지를 서버가 못 거른다. 각 사이트 README 에 무엇을 어떻게 쓰는지 있다.

이미지 판독 단계에는 **손잡이가 따로 셋** 있다. 검색 조건이 아니라 운영값이라 안 적어도
기본값으로 돈다 — 자세한 것은 [image_process/README.md](image_process/README.md) 에 있다.

```bash
IMAGE_MODEL=                      # 기본 sonnet
IMAGE_CLAUDE_WORKER=              # 기본 4. 동시에 띄울 claude 개수
IMAGE_TIMEOUT=                    # 기본 300초
```

## 테스트

```bash
python3 tests/run.py                              # 오케스트레이터 + 이미지 판독 130건
cd job_sites/<사이트> && python3 tests/run.py       # 사이트별
```

합쳐 916건. 네트워크도 `claude` 도 타지 않는다 — 떠 놓은 실제 응답을 쓰고, 이미지는
Pillow 로 그 자리에서 그려서 쓴다.

| wanted | saramin | jobkorea | jobplanet | jumpit | pathsdog | 루트(오케스트레이터+이미지 판독) |
|---|---|---|---|---|---|---|
| 88 | 255 | 103 | 119 | 110 | 111 | 130 |

사람인이 많은 것은 **`_common` 의 테스트가 거기 있기** 때문이다 — 어느 한 사이트에 붙여
두면 그 사이트를 지웠을 때 시험도 같이 사라진다. 루트의 130건은 오케스트레이터·합치기 41건과
이미지 판독 89건을 합친 것이다 — 이미지 판독은 `job_sites/` 아래에 있지 않으므로 여기서
돈다.

## 문서

| | |
|---|---|
| [ORCHESTRATOR.md](ORCHESTRATOR.md) | 여섯을 병렬로 돌리고 합치는 일 · **종료 코드 계약** |
| [image_process/README.md](image_process/README.md) | 그림 본문을 읽어 채우는 단계 |
| [docs/convention/](docs/convention/) | **수집 규약.** 새 사이트를 붙일 때 여기부터 읽는다 |
| [docs/convention/03-adding-a-site.md](docs/convention/03-adding-a-site.md) | 새 사이트 체크리스트 |
| [docs/convention/06-decisions.md](docs/convention/06-decisions.md) | 결정과 실측 근거 |
| [job_sites/_common/README.md](job_sites/_common/README.md) | 사이트 공통 계층 |
| `job_sites/<사이트>/README.md` | 그 사이트의 조건·코드표·제약 |
