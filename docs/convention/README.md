# 채용공고 수집 — 규약

여러 채용 사이트에서 **같은 모양의 결과물**을 뽑기 위한 규약이다.
사이트가 늘어도 CSV 한 벌로 합쳐 볼 수 있어야 하고, 코드가 늘어도 읽는 방식이 같아야 한다.

다섯이 구현돼 있다 — `wanted` `saramin` `jobkorea` `jobplanet` `jumpit`.
**이 문서들은 여섯 번째를 붙일 때 기준이 되고, 다섯이 서로 어긋나지 않게 붙잡는다.**

## 어디부터 읽나

| 언제 | 무엇 |
|---|---|
| 전체 그림이 궁금하다 | [01-architecture.md](01-architecture.md) — 무엇이 공통이고 무엇이 사이트 것인가 |
| **새 사이트를 붙인다** | [03-adding-a-site.md](03-adding-a-site.md) — 순서대로 따라가는 체크리스트 |
| CSV 컬럼을 채워야 한다 | [02-data-contract.md](02-data-contract.md) — 13컬럼의 정의와 채우는 규칙 |
| 코드를 쓴다 | [04-code-conventions.md](04-code-conventions.md) — 이름·경계·주석·실패 처리 |
| 테스트를 쓴다 | [05-testing.md](05-testing.md) — 통과용 테스트를 막는 규칙 |
| **왜 이렇게 했는지** 알고 싶다 | [06-decisions.md](06-decisions.md) — 결정과 그 근거 |

## 한 줄로 줄이면

> **모르는 것을 아는 척하지 않는다.**

이 규약의 대부분은 그 한 줄에서 나온다. 사전에 없는 이름은 억지로 가까운 것에 붙이지 않고,
날짜를 모르는 행은 오래됐다고 단정해 지우지 않고, 조용히 실패하는 대신 왜 멈췄는지 찍는다.
근거는 [06-decisions.md](06-decisions.md) 에 사례별로 적혀 있다.

## 실행

```bash
# 저장소 루트에 .env 를 직접 만든다. 항목은 사이트 README 에 있다.
# .env 는 추적되지 않고 예시 파일도 없다 — 없으면 안 도는 것이 맞다.
$EDITOR .env

cd job_sites/wanted
python3 wanted.py           # 수집 → csv/wanted_post.csv (추적 안 됨)
python3 tests/run.py        # 테스트
```
