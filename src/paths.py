"""저장소 안의 자리를 **한 곳에서** 정한다.

    from paths import CSV, CACHE, SITES
    INPUT = CSV / "merged_role.csv"

## 왜 모으나

전에는 단계마다 `ROOT_DIR = Path(__file__).resolve().parent` 를 적고 거기서
`ROOT_DIR / "csv" / …` 로 뻗어 나갔다. 파일이 열두 개라 **"저장소 뿌리가 어디인가"
를 아는 곳이 열두 군데**였고, 파일을 한 칸 옮기면 열두 군데를 같이 고쳐야 했다.

실제로 `_common/sections.py` 의 머리말 글자가 세 군데에 흩어져 있다가 같은 문제를
냈다 — 한 곳만 고치는 일이 반드시 생긴다. 자리도 같은 성질이다.

## 배치

    저장소 뿌리/
      job_crawling_ochestrator.py   오케스트레이터. **루트에는 이것과 README 뿐이다**
      README.md  requirements.txt
      src/          ← 단계 코드와 패키지
        paths.py      이 파일
        filter.py  role.py  career.py  nuance.py  …
        job_sites/    수집기와 공용 모듈
        image_process/ 그림 판독
        templates/    리포트 HTML 틀
      docs/         README 가 아닌 문서 (`docs/stages/` 에 단계별 설명)
      scripts/      손으로 돌리는 셸
      tests/        시험
      csv/ cache/ history/ context/   자료

## 자료 폴더는 **뿌리에 둔다**

`csv/`·`cache/`·`history/` 는 코드가 아니라 **실행이 만든 것**이다. `src/` 안에
두면 코드와 산출물이 섞여, 무엇이 손으로 쓴 것이고 무엇이 만들어진 것인지
`git status` 로 안 갈린다.
"""
from __future__ import annotations

from pathlib import Path

# 이 파일은 `src/` 안에 있다. 그러므로 한 칸 위가 저장소 뿌리다.
ROOT = Path(__file__).resolve().parent.parent

SRC = ROOT / "src"
SITES = SRC / "job_sites"
TEMPLATES = SRC / "templates"

CSV = ROOT / "csv"
CACHE = ROOT / "cache"
HISTORY = ROOT / "history"
DOCS = ROOT / "docs"

# 오케스트레이터가 자식으로 부르는 단계들. **이름을 여기 모은다** — 오케스트레이터가
# `ROOT / "filter.py"` 처럼 직접 적으면, 파일을 옮길 때 그쪽도 같이 고쳐야 한다.
def stage(name: str) -> Path:
    """단계 스크립트 하나의 자리. `stage("filter")` → `src/filter.py`."""
    return SRC / ("%s.py" % name)
