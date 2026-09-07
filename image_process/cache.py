"""읽은 결과를 **공고 하나 단위로** 기억한다.

사이트별 CSV 는 30일 누적이라 같은 공고가 30일 동안 계속 대상에 잡힌다. 캐시가 없으면
같은 그림을 한 달에 서른 번 읽고 그만큼 돈을 낸다. 두 번째 실행부터 이 단계는 수 초에
끝나고 돈이 안 든다.

## 열쇠는 **주소 하나가 아니라 그 공고의 주소 목록 전체**다

한 공고가 그림 여러 장이면 우리는 그 장들을 **합쳐 한 번 읽는다.** 그 답은 그 조합의
답이지 낱장의 답이 아니다. 그런데 낱장 주소마다 그 답을 넣어 두면, 같은 주소를 쓰는
다른 공고가 **남의 자격요건을 자기 것으로 받아 간다** — 이름은 B 회사인데 내용은 A
회사인 행이 버려지지도 않고 캐시에까지 남는다.

가정이 아니다. 실제로 걷은 데이터에서 `…/images/blank.png` 를 서로 다른 두 회사가 쓰고
있었고, `…/images/template/toptype/it1.webp` 는 사람인 공용 템플릿이라 성격상 여러
공고가 나눠 쓴다.

그래서 열쇠는 **주소 목록을 차례까지 지켜 하나로 묶은 것**이다(`key()`). 공고 하나에
열쇠 하나, 답 하나. 덤으로, 여러 장 중 한 장만 캐시에 없어서 전부 다시 받아 읽던 일도
없어진다 — 애초에 낱장으로 맞춰 보지 않는다.

**옛 캐시 파일의 낱장 열쇠는 전부 빗나간다.** 그대로 두어도 해가 없고(안 읽힐 뿐이다),
다음 실행에서 공고 단위로 다시 채워진다. 캐시는 편의지 진실이 아니다.

**빈 결과도 기억한다.** "셋 다 비었다" 는 우리가 실패한 것이 아니라 그림에 쓸 게 없다는
결과다. 안 기억하면 쓰레기 그림을 매 실행 다시 읽는다. 반대로 **우리 쪽 실패는 기억하지
않는다** — 다음 실행에 다시 시도해야 한다.

캐시 때문에 단계가 멎으면 안 된다. 파일이 깨져 있으면 무시하고 새로 읽는다.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

FIELDS = ("기술스택", "자격요건", "우대사항")
# 주소에는 공백이 못 들어간다(RFC 3986 — 공백은 `%20` 으로 적힌다). 그래서 이어 붙여도
# 어디서 끊긴 것인지 헷갈리지 않는다. 해시로 줄일 수도 있지만, 캐시 파일을 열어 보고
# "어느 공고의 답인가" 를 눈으로 알아볼 수 있는 편이 낫다.
SEPARATOR = " "
CACHE_PATH = (Path(__file__).resolve().parent.parent
              / "job_sites" / "_common" / "cache" / "image_reads.json")


def key(urls: list[str]) -> str:
    """공고 하나의 열쇠. **차례도 열쇠의 일부다** — 조각 순서가 바뀌면 다른 입력이다."""
    return SEPARATOR.join(urls)


def load(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(path: Path, book: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")


def get(book: dict, urls: list[str]) -> dict | None:
    entry = book.get(key(urls))
    if not isinstance(entry, dict):
        return None
    return {name: list(entry.get(name) or []) for name in FIELDS}


def put(book: dict, urls: list[str], read: dict, model: str) -> None:
    book[key(urls)] = {
        **{name: list(read.get(name) or []) for name in FIELDS},
        "읽은날": date.today().isoformat(),
        "모델": model,
    }
