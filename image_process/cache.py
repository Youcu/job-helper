"""읽은 결과를 **그림 주소별로** 기억한다.

사이트별 CSV 는 30일 누적이라 같은 공고가 30일 동안 계속 대상에 잡힌다. 캐시가 없으면
같은 그림을 한 달에 서른 번 읽고 그만큼 돈을 낸다. 두 번째 실행부터 이 단계는 수 초에
끝나고 돈이 안 든다.

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
CACHE_PATH = (Path(__file__).resolve().parent.parent
              / "job_sites" / "_common" / "cache" / "image_reads.json")


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


def get(book: dict, url: str) -> dict | None:
    entry = book.get(url)
    if not isinstance(entry, dict):
        return None
    return {name: list(entry.get(name) or []) for name in FIELDS}


def put(book: dict, url: str, read: dict, model: str) -> None:
    book[url] = {
        **{name: list(read.get(name) or []) for name in FIELDS},
        "읽은날": date.today().isoformat(),
        "모델": model,
    }
