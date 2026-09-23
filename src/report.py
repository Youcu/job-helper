#!/usr/bin/env python3
"""최종본을 **사람이 보고 판단하는 화면**으로 그린다.

    python3 src/report.py

    csv/merged_career.csv  →  csv/report.html

## 왜 CSV 말고 HTML 인가

CSV 는 **분석용**이다 (2026-09-18 사용자). 칸이 열넷이고 `지원자격`·`우대사항` 은
한 칸이 수백 자라, 표 계산기로 열면 읽을 수가 없다. 지원할지 말지를 정하는 일은
**공고를 하나씩 읽는 일**이라 다른 화면이 필요하다.

    csv/merged_career.csv   기계가 읽는다 — 숫자를 세고 갈래를 나눈다
    csv/report.html         사람이 읽는다 — 검색하고 접었다 펴고 표시한다

## 왜 단계가 아닌가 (D-25)

D-25 의 기준은 **그물이나 모델을 타거나 · 분 단위로 걸리거나 · 혼자 실패할 수
있을 때** 새 단계로 둔다는 것이다. 그리기는 셋 다 아니다 — 파일 하나를 읽어
파일 하나를 쓰고, 0.1초도 안 걸린다.

그래서 `STAGES` 표에 안 넣는다. 대신 **혼자 돌 수 있는 스크립트**로 둔다 —
화면 모양을 고치고 다시 그리는 일은 자주 생기는데, 그때마다 파이프라인 전체를
돌릴 수는 없다. 오케스트레이터는 마지막에 이것을 부르되 **실패해도 파이프라인을
실패로 만들지 않는다.** 자료는 이미 다 나와 있고, 못 그린 것은 다시 그리면 된다.

## 템플릿은 **온전한 HTML 문서**다

`<!doctype>` 부터 `</html>` 까지 다 들어 있다. 당연한 말 같지만 처음에는 아니었다 —
이 화면을 artifact 로 먼저 만들고 그 본문을 베껴 왔는데, artifact 플랫폼이 `doctype`·
`charset`·`viewport` 를 **알아서 씌워 준다.** 거기서는 멀쩡했고 파일로 떨어뜨리는
순간 깨졌다. `<meta charset>` 이 없으니 브라우저가 인코딩을 추측했고 **한글이 전부
깨졌다** (2026-09-19 사용자).

**웹폰트도 안 쓴다.** 시스템 한글 폰트 스택만 쓴다 — 망에 못 닿으면 그 자리가 통째로
바뀌고, 이 파일은 손에 쥐고 여는 것이라 망을 전제할 수 없다.

## 모양은 `src/templates/report_template.html` 에 있다

파이썬 안에 HTML 을 넣지 않는다. 디자인을 고치려고 파이썬을 열게 되면, 고치는
사람이 자료 읽는 코드까지 지나가야 한다. 템플릿은 자리 표시 다섯 개를 받는다.

    __TITLE__    제목
    __LEDE__     한 줄 설명
    __SOURCE__   어느 파일에서 언제 그렸나
    __FUNNEL__   거르기 눈금 — [이름, 건수] 목록
    __DATA__     공고 목록

## 거르기 눈금은 세어서 넣는다

"883건에서 45건까지" 같은 숫자를 손으로 적으면 **다음 실행에 바로 어긋난다.**
`csv/` 에 있는 단계별 산출물의 행 수를 그때그때 센다. 파일이 없으면 그 칸은
건수 없이 이름만 적는다 — 없는 숫자를 지어내지 않는다.

종료 코드
    0  정상
    1  입력이 없다
    3  이미 돌고 있다
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "job_sites"))

from _common.runlock import guarded            # noqa: E402

SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR / "job_sites"))
sys.path.insert(0, str(SRC_DIR))

from paths import CACHE as CACHE_DIR, CSV, HISTORY as HISTORY_DIR  # noqa: E402
from paths import ROOT, SITES, TEMPLATES                          # noqa: E402
INPUT = CSV / "merged_career.csv"
TEMPLATE = TEMPLATES / "report_template.html"
OUTPUT = CSV / "report.html"
LOCK = CSV / ".report.lock"

TITLE = "백엔드 신입 공고 %d건"
LEDE = "일곱 단계를 지나고 남은 것. 다섯 사이트에서 걷은 %s건이 여기까지 왔다."
LEDE_ALONE = "일곱 단계를 지나고 남은 것."

# 눈금에 세울 칸 — (보일 이름, 세어 올 파일). 파일이 없으면 이름만 남는다.
FUNNEL = (
    ("걷음", "merged.csv"),
    ("그림 판독", "merged_read.csv"),
    ("직군 가리기", "merged_role.csv"),
    ("낱말 거르기", "merged_filtered.csv"),
    ("평점", "merged_rated.csv"),
    ("핵심 기술", "merged_core.csv"),
    ("경력 판정", "merged_career.csv"),
)


def read_rows(path: Path) -> list[dict]:
    """CSV 한 벌을 사전 목록으로. 없으면 빈 목록."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def count_rows(path: Path) -> int | None:
    """행이 몇인가. 파일이 없으면 `None` — **0 이 아니다.**

    0 으로 답하면 "걸러서 하나도 안 남았다" 와 "아직 안 돌렸다" 가 같아 보인다.
    """
    return len(read_rows(path)) if path.exists() else None


def posting(row: dict) -> dict:
    """CSV 한 행을 화면이 쓰는 모양으로. **칸 이름은 여기서만 안다.**"""
    return {
        "co": row.get("기업명", "").strip(),
        "title": row.get("공고명", "").strip(),
        "due": row.get("마감일", "").strip(),
        "req": row.get("지원자격", "").strip(),
        "pref": row.get("우대사항", "").strip(),
        "career": row.get("경력", "").strip(),
        "url": row.get("URL", "").strip(),
        "pay": row.get("연봉", "").strip(),
        "tech": [one.strip() for one in row.get("기술스택", "").split(",") if one.strip()],
        "loc": row.get("근무지", "").strip(),
        "site": row.get("사이트명", "").strip(),
        "rate": row.get("평점", "").strip(),
        "first": row.get("최초수집일", "").strip(),
        "last": row.get("최종확인일", "").strip(),
    }


def funnel(csv_dir: Path) -> list[list]:
    """눈금을 센다. 세어 온 숫자만 넣고, 없는 것은 `None` 으로 둔다."""
    return [[label, None if name is None else count_rows(csv_dir / name)]
            for label, name in FUNNEL]


def render(template: str, rows: list[dict], steps: list[list], source: str) -> str:
    """자리 표시 다섯을 채운다.

    **JSON 은 `</` 를 갈라 넣는다.** 공고 글에 `</script>` 가 들어 있으면 브라우저가
    거기서 스크립트를 끊는다 — 우리가 쓰는 글은 남이 쓴 것이라 무엇이 들어올지 모른다.
    """
    data = json.dumps([posting(row) for row in rows], ensure_ascii=False)
    data = data.replace("</", "<\\/")
    counted = steps[0][1]
    return (template
            .replace("__TITLE__", TITLE % len(rows))
            .replace("__LEDE__", LEDE % counted if counted else LEDE_ALONE)
            .replace("__SOURCE__", source)
            .replace("__FUNNEL__", json.dumps(steps, ensure_ascii=False))
            .replace("__DATA__", data))


def write(path: Path, page: str) -> None:
    """원자적으로 쓴다 — 반쯤 쓰인 화면을 여는 일이 없게."""
    temp = path.with_suffix(path.suffix + ".tmp")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            handle.write(page)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def _run(source: Path, template_path: Path, output: Path) -> int:
    if not source.exists():
        print("%s 가 없습니다. 파이프라인을 먼저 돌려 주세요." % source, file=sys.stderr)
        return 1
    if not template_path.exists():
        print("%s 가 없습니다." % template_path, file=sys.stderr)
        return 1

    rows = read_rows(source)
    steps = funnel(source.parent)
    made = datetime.now().strftime("%Y-%m-%d %H:%M")
    page = render(template_path.read_text(encoding="utf-8"), rows, steps,
                  "%s · %s 그림" % (source.name, made))
    write(output, page)
    print("%s — 공고 %d건" % (output, len(rows)))
    return 0


def main() -> int:
    return _run(INPUT, TEMPLATE, OUTPUT)


if __name__ == "__main__":
    raise SystemExit(guarded(LOCK, main))
