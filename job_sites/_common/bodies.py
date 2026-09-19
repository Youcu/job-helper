"""공고 **본문**을 CSV 옆에 따로 둔다.

    job_sites/<사이트>/csv/<사이트>_bodies.jsonl     수집기가 쓴다
    csv/bodies.jsonl                                 오케스트레이터가 합친다

## 왜 CSV 칸이 아닌가

본문은 길다 — 실측 최대 18,924자(`rec_idx=50846359`). CSV 칸 상한은 4,000자이고
(`store.MAX_FIELD_LENGTH`), 그건 표 계산기로 열 수 있게 하려고 정한 **약속**이다.
본문을 칸에 넣으면 그 약속이 깨지고, 중간 산출물 여섯 개가 전부 본문을 실어 나른다.

## 왜 필요한가

**절로 잘라 낸 칸은 정보를 잃는다.** 한 공고에 여러 부문이 있으면 `지원자격` 에는
**첫 부문 것만** 들어간다 — 나라스페이스는 PM 부문 요건이 실렸다. 뒤 단계에서
"내 직군 부문만 골라라" 를 물으려면 **자르기 전의 글**이 있어야 한다.

## 다섯 곳이 **다** 쓴다 — 측정값을 규칙으로 굳히지 않는다

실측(2026-09-18, 672행)으로는 여러 직군을 한 공고에 담는 것이 **사람인 36 · 잡코리아
16** 뿐이고 wanted·jumpit·jobplanet 은 **0** 이었다. 그래서 처음에는 HTML 두 곳만
저장하고 나머지는 "칸이 곧 본문" 이라 넘기려 했다.

**그러면 안 된다** (2026-09-18 사용자). 그 0 은 오늘 걷힌 것의 성질일 뿐이다. 내일
wanted 에 통합 공고가 하나 뜨면 본문이 없고, 읽는 쪽은 **이미 잘려 나간 칸**으로
판단한다 — 걸렀다고 믿는데 안 걸린 결과가 나오고, 아무 데도 안 드러난다.

    측정은 "지금 이렇다" 를 말한다. 규칙은 "앞으로도 이래야 한다" 를 말한다.
    측정을 규칙 자리에 놓으면, 세상이 바뀐 날 코드는 조용히 틀린다.

그래서 **본문은 다섯 곳이 다 적는다.** 사이트가 가진 공고 글 **전부**를, 절로
자르기 전의 것으로. API 사이트는 칸과 겹치지만 겹치는 값이 싸다 — 없는 편이 비싸다.

## 없으면 드러나야 한다

그래도 본문이 비는 경우는 생긴다(수집 실패·새 사이트가 빠뜨림). 읽는 쪽은 그때
**조용히 칸으로 대신하지 않는다.** 판정을 못 했다고 말하고 리포트에 남긴다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

KEY = "URL"
BODY = "본문"

# 한 공고에서 이만큼까지만 남긴다. 실측 최대가 18,924자라 넉넉하다. 상한을 두는 이유는
# **모델에게 통째로 줄 글**이기 때문이다 — 페이지가 터무니없이 크면 거기서 막힌다.
MAX_BODY = 50_000


def path_for(site_csv: Path) -> Path:
    """사이트 CSV 옆의 본문 파일. 같이 생기고 같이 지워진다."""
    return site_csv.with_name(site_csv.stem + "_bodies.jsonl")


def tidy(texts: dict[str, str]) -> dict[str, str]:
    """적을 것만 골라 길이를 맞춘다.

    **빈 본문은 안 적는다.** 적으면 "받았는데 비었다" 와 "안 받았다" 가 같아 보이고,
    읽는 쪽이 둘을 못 가른다.
    """
    return {key: text.strip()[:MAX_BODY]
            for key, text in texts.items() if key and (text or "").strip()}


def load(path: Path) -> dict[str, str]:
    """URL → 본문. 파일이 없으면 빈 사전.

    **줄 하나가 깨져도 나머지는 살린다.** 본문은 거들 뿐이라, 한 줄 때문에 수집 전체를
    멈출 이유가 없다.
    """
    if not path.exists():
        return {}
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            one = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = one.get(KEY)
        if key:
            found[key] = one.get(BODY, "")
    return found


def write(path: Path, bodies: dict[str, str]) -> None:
    """원자적으로 쓴다 — 반쯤 쓰인 파일을 다음 단계가 읽는 일이 없게."""
    temp = path.with_suffix(path.suffix + ".tmp")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            for key in sorted(bodies):
                handle.write(json.dumps({KEY: key, BODY: bodies[key]},
                                        ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def write_map(texts: dict[str, str], path: Path) -> int:
    """이번에 걷은 본문을 앞서 둔 것과 합쳐 쓴다. 이번에 쓴 개수를 돌려준다.

    합치는 이유는 CSV 와 같다 — **한 사이트만 따로 여러 번 돌릴 때** 앞 실행 것을
    잃지 않기 위해서다.
    """
    fresh = tidy(texts)
    if not fresh and not path.exists():
        return 0
    kept = load(path)
    kept.update(fresh)
    write(path, kept)
    return len(fresh)


def gather(paths: list[Path], output: Path) -> int:
    """사이트별 본문을 한 파일로 모은다. 오케스트레이터가 CSV 를 합칠 때 같이 부른다.

    같은 URL 이 두 사이트에서 나올 일은 없다(주소에 사이트가 들어 있다). 그래도
    나중 것이 이긴다 — 조용히 둘을 남기는 것보다 낫다.
    """
    merged: dict[str, str] = {}
    for path in paths:
        merged.update(load(path))
    write(output, merged)
    return len(merged)
