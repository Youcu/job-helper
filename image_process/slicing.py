"""세로로 긴 그림을 **여백에서** 자른다.

## 왜 자르나

모델에 넣으면 긴 변에 맞춰 축소된다. 세로가 21,708px 이면 작은 글씨가 통째로 뭉갠다.
실측 — 같은 그림·같은 모델로 통째로 넣으면 자격요건 0개·우대사항 0개, 잘라 넣으면
5개·6개가 정확히 나왔다. 그림에는 또렷이 있다.

**버리는 규칙이 있는 설계라 이건 그냥 품질 문제가 아니다.** 못 읽으면 그 공고를 버리므로,
읽을 수 있는데 못 읽는 것은 멀쩡한 데이터를 없애는 일이다.

## 왜 등분이 아닌가

등분하면 글줄 한가운데가 잘린다. 가로 한 줄이 통째로 무늬 없는 곳을 찾아 그 한가운데를
자른다. 실측한 그림에 20px 이상 여백 띠가 126개, 띠 없는 최장 구간이 1,794px 로 목표
높이보다 한참 짧아 자를 자리를 늘 찾았다(강제로 자른 곳 0).

여백을 못 찾으면(빽빽한 표) 겹쳐서 자른다 — 잘린 줄이 옆 조각에 온전히 한 번 더 나오게.
중복은 `fill.py` 의 대조가 걸러 준다.

## 왜 자르기 직전에 한 번 더 본다

`flat_rows` 는 한 줄에서 `SAMPLES` 칸만 찍어 본다 — 21,708줄을 전수로 보면 느리다.
그런데 표본 칸 사이에만 글자가 걸리면 그 줄은 실제로는 무늬가 있는데도 "무늬 없음"으로
잡힌다. 실측한 두 그림에서 이렇게 잘못 "여백"으로 잡힌 줄이 최대 192px 연속으로
나왔다 — `MIN_BAND`(12) 를 가볍게 넘는 두께라 자를 자리로 뽑힐 수 있다. 그래서 자르기
**직전에** 그 한 줄만 전수로 다시 본다. 후보를 놓치면 다음으로 두꺼운 후보를, 그것도
없으면 강제/겹침 경로로 넘어간다. 전수 검사는 자르는 횟수만큼만 도니 표본을 쓰는
이유(속도)는 그대로 남는다.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

RATIO = 2.4          # 세로가 가로의 이 배를 넘으면 자른다
TOLERANCE = 8        # 한 줄의 밝기 폭이 이 안이면 무늬 없는 줄
MIN_BAND = 12        # 이 두께 이상인 여백이라야 자를 자리로 본다
OVERLAP = 60         # 여백을 못 찾았을 때 겹치는 픽셀
SAMPLES = 200        # 한 줄에서 이만큼만 찍어 본다 (전수는 느리고 이걸로 충분하다)


def flat_rows(image) -> list[bool]:
    """가로 한 줄이 통째로 '거의 한 색' 인가. 인덱스가 y 다."""
    grey = image.convert("L")
    width, height = grey.size
    pixels = grey.load()
    step = max(1, width // SAMPLES)
    out = []
    for y in range(height):
        values = [pixels[x, y] for x in range(0, width, step)]
        out.append(max(values) - min(values) <= TOLERANCE)
    return out


def _bands(flat: list[bool], low: int, high: int) -> list[tuple[int, int]]:
    """`low`~`high` 안의 연속된 여백 구간들."""
    out, start = [], None
    for y in range(max(low, 0), min(high, len(flat))):
        if flat[y]:
            if start is None:
                start = y
        elif start is not None:
            out.append((start, y - 1))
            start = None
    if start is not None:
        out.append((start, min(high, len(flat)) - 1))
    return out


def _row_is_really_flat(pixels, width: int, y: int) -> bool:
    """`y` 줄을 이번엔 전수로 본다. `flat_rows` 의 표본이 놓친 글자를 잡아낸다.

    실제로 자를 후보로 뽑힌 줄에서만 부르므로 — 자르는 횟수만큼만 도니 값싸다."""
    values = [pixels[x, y] for x in range(width)]
    return max(values) - min(values) <= TOLERANCE


def spans(image, *, ratio: float = RATIO) -> tuple[list[tuple[int, int]], int]:
    """자를 구간들과, 여백을 못 찾아 강제로 자른 횟수.

    구간은 **빈틈 없이 그림 전체를 덮는다** — 빠진 구간이 있으면 그만큼 글을 통째로 잃는다.
    """
    width, height = image.size
    target = int(width * ratio)
    if height <= target:
        return [(0, height)], 0

    grey = image.convert("L")
    pixels = grey.load()
    flat = flat_rows(image)
    slack = max(target // 3, 1)
    out: list[tuple[int, int]] = []
    top, forced = 0, 0
    while height - top > target + slack:
        want = top + target
        found = [b for b in _bands(flat, max(top + 1, want - slack), want + slack)
                 if b[1] - b[0] >= MIN_BAND]
        found.sort(key=lambda b: b[1] - b[0], reverse=True)   # 두꺼운 후보부터 시도
        cut = None
        for start, end in found:
            candidate = (start + end) // 2
            if _row_is_really_flat(pixels, width, candidate):
                cut = candidate
                break
            # 표본은 여백이라 했지만 전수로 보니 글자가 있다 — 다음 후보로.
        if cut is not None:
            out.append((top, cut))
            top = cut
        else:
            forced += 1
            out.append((top, want))
            top = max(want - OVERLAP, top + 1)     # 잘린 줄을 다음 조각이 다시 담는다
    out.append((top, height))
    return out, forced


def slice_image(path: Path, out_dir: Path, *, ratio: float = RATIO) -> list[Path]:
    """조각 파일들을 만들고 **위에서 아래 차례로** 돌려준다."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    with Image.open(path) as image:
        image = image.convert("RGB")
        pieces, _forced = spans(image, ratio=ratio)
        width = image.size[0]
        for index, (top, bottom) in enumerate(pieces):
            target = out_dir / ("%s_%03d.png" % (Path(path).stem, index))
            image.crop((0, top, width, bottom)).save(target)
            made.append(target)
    return made
