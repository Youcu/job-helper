"""세로로 긴 그림을 **여백에서** 자른다.

## 왜 자르나

통째로 넣으면 긴 변에 맞춰 축소돼 작은 글씨가 뭉갠다. 실측 — 같은 그림 같은 모델(sonnet)로
통째로 넣으면 자격요건 0개·우대사항 0개가 나오는데, 잘라 넣으면 5개·6개가 정확히 나온다.
그림에는 또렷이 적혀 있다. **버리는 규칙이 있는 설계에서 그런 거짓 실패는 멀쩡한 공고를
없앤다.**

## 왜 등분이 아닌가

등분하면 글줄 한가운데가 잘린다. 대신 가로 한 줄이 통째로 무늬 없는 곳(여백)을 찾아 그
한가운데를 자른다. 실측한 그림(1505×21708)에 20px 이상 여백 띠가 126개, 띠 없는 최장
구간이 1,794px 로 목표 높이(3,612px)보다 한참 짧아 자를 자리를 늘 찾았다.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from image_process import slicing

from .helpers import check, check_equal, temp_dir


def _striped(width: int, height: int, band_every: int, band_height: int):
    """글줄(검은 띠)과 여백(흰 줄)이 번갈아 나오는 그림."""
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    y = 0
    while y < height:
        draw.rectangle([0, y, width, y + band_height], fill=(0, 0, 0))
        y += band_every
    return image


def _solid(width: int, height: int):
    """여백이 하나도 없는 그림 — 빽빽한 표 같은 것.

    **가로 줄이 아니라 세로 줄무늬로 그린다.** 가로 띠로 그리면 띠 안 색이든 띠 사이
    색이든 그 줄 자체는 한 색이라 `flat_rows` 가 여전히 "여백"으로 본다 — 실제로 한 번
    그렇게 짰다가 겹쳐 자르기가 한 번도 발동하지 않는 걸 보고서야 잡았다. 세로 줄무늬는
    모든 가로 줄에 검정과 흰색이 같이 걸쳐 있어서 어느 줄도 무늬 없는 줄이 될 수 없다.
    """
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for x in range(0, width, 10):
        draw.rectangle([x, 0, x + 4, height], fill=(0, 0, 0))
    return image


def test_NORMAL_short_image_is_not_cut():
    image = _striped(800, 1200, 100, 20)      # 세로가 가로의 1.5배
    got, forced = slicing.spans(image)
    check_equal(len(got), 1, "비율 안이면 한 장 그대로")
    check_equal(got[0], (0, 1200), "위에서 아래까지")
    check_equal(forced, 0, "강제로 자른 곳 없음")


def test_NORMAL_tall_image_is_cut_into_several():
    image = _striped(800, 12000, 200, 40)     # 세로가 가로의 15배
    got, forced = slicing.spans(image)
    check(len(got) >= 5, "여러 장이어야 한다: %d장" % len(got))
    check_equal(forced, 0, "여백이 있으니 강제로 자를 일이 없다")


def test_NORMAL_spans_cover_the_whole_image_without_gaps():
    # **빠진 구간이 있으면 그만큼 글을 통째로 잃는다.**
    image = _striped(800, 12000, 200, 40)
    got, _forced = slicing.spans(image)
    check_equal(got[0][0], 0, "맨 위에서 시작")
    check_equal(got[-1][1], 12000, "맨 아래에서 끝")
    for before, after in zip(got, got[1:]):
        check(after[0] <= before[1], "사이가 비면 안 된다: %r → %r" % (before, after))


def test_NORMAL_cuts_land_on_blank_rows():
    """자른 자리에 글자가 없어야 한다. **이 테스트가 이 파일의 이유다.**"""
    image = _striped(800, 12000, 200, 40).convert("L")
    got, _forced = slicing.spans(image)
    pixels = image.load()
    for _top, bottom in got[:-1]:
        row = [pixels[x, bottom] for x in range(0, 800, 4)]
        check(max(row) - min(row) <= slicing.TOLERANCE,
              "%d 번째 줄에 글자가 있다 — 글줄을 잘랐다" % bottom)


def test_EXCEPTION_image_without_any_blank_row_falls_back_to_overlap():
    # 빽빽한 표는 여백이 없다. 그때는 겹쳐 잘라 **잘린 줄이 옆 조각에 한 번 더** 나오게 한다.
    image = _solid(800, 12000)
    got, forced = slicing.spans(image)
    check(forced > 0, "여백을 못 찾았다고 알려야 한다")
    for before, after in zip(got, got[1:]):
        check(after[0] < before[1], "겹쳐야 한다: %r → %r" % (before, after))


def test_BOUNDARY_exactly_at_the_ratio_is_not_cut():
    image = _striped(1000, 2400, 100, 20)     # 딱 1:2.4
    got, _forced = slicing.spans(image)
    check_equal(len(got), 1, "딱 비율이면 안 자른다")


def test_BOUNDARY_wider_than_tall_is_not_cut():
    image = _striped(1720, 760, 100, 20)      # 사람인 템플릿 배너 모양
    got, _forced = slicing.spans(image)
    check_equal(len(got), 1, "가로가 더 긴 그림은 자를 이유가 없다")


def test_BOUNDARY_slice_image_writes_files_in_order():
    path = temp_dir() / "긴그림.png"
    _striped(800, 12000, 200, 40).save(path)
    out = temp_dir() / "조각"
    made = slicing.slice_image(path, out)
    check(len(made) >= 5, "여러 장 나와야 한다")
    for one in made:
        check(one.exists(), "%s 가 없다" % one)
    check_equal(made, sorted(made), "위에서 아래 차례여야 한다 — 섞이면 글 순서가 깨진다")


def test_BOUNDARY_short_image_yields_one_file():
    path = temp_dir() / "짧은그림.png"
    _striped(800, 1200, 100, 20).save(path)
    made = slicing.slice_image(path, temp_dir() / "조각")
    check_equal(len(made), 1, "안 자를 때도 파일 하나는 낸다")


def _sample_step(width: int) -> int:
    """`flat_rows` 가 쓰는 것과 똑같은 계산 — 픽스처가 표본 칸을 정확히 피하게 한다."""
    return max(1, width // slicing.SAMPLES)


def _hidden_between_samples(width, height, fill_low, fill_high,
                             hidden_top, hidden_bottom, real_top=None, real_bottom=None):
    """표본 칸 사이에만 세로줄을 둔 그림 — `flat_rows` 표본으로는 '여백'으로 잡힌다.

    `hidden_top`~`hidden_bottom` 은 실제로는 글자가 있는데 표본에 안 걸리는 구간이다.
    `real_top`~`real_bottom` 을 주면 그 구간은 진짜 흰 여백으로 비워 두고, `fill_low`~
    `fill_high` 의 나머지는 표본 칸에도 걸리는 진짜 검정 점을 찍어 밴드가 되지 못하게 한다
    — 안 그러면 창 전체가 '여백'으로 보여 검사 대상이 흐려진다.
    """
    step = _sample_step(width)
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    for x in range(0, width, step):
        xx = x + step // 2                # 표본이 찍는 칸(step 배수)을 피한 자리
        if xx < width:
            draw.line([(xx, hidden_top), (xx, hidden_bottom)], fill=0)
    for y in range(fill_low, fill_high):
        if hidden_top <= y <= hidden_bottom:
            continue
        if real_top is not None and real_top <= y <= real_bottom:
            continue
        draw.point((0, y), fill=0)          # 표본 칸(x=0)에도 걸리는 진짜 글자
    return image.convert("RGB")


def test_BOUNDARY_hidden_text_between_samples_is_not_cut():
    """표본이 못 보는 곳에 글자를 숨겨도, 자르기 직전 전수 검사가 걸러 낸다."""
    width, height = 800, 4000
    # target=int(800*2.4)=1920, slack=640 → 첫 자르기 창은 [1280, 2560].
    # 그 창 안에서 (1400,1650) 은 표본에 안 걸리는 '가짜 여백' 이라 더 두껍고,
    # (2000,2100) 은 진짜 여백이라 더 얇다 — 검사 없이 두꺼운 쪽만 골랐다면 글자를 잘랐을 것.
    image = _hidden_between_samples(width, height, 1280, 2560,
                                     hidden_top=1400, hidden_bottom=1650,
                                     real_top=2000, real_bottom=2100)
    got, _forced = slicing.spans(image)
    cut = got[0][1]
    check(not (1400 <= cut <= 1650), "숨은 글자 구간(%d~%d) 안에서 잘랐다: %d" % (1400, 1650, cut))
    grey = image.convert("L")
    pixels = grey.load()
    row = [pixels[x, cut] for x in range(width)]
    check(max(row) - min(row) <= slicing.TOLERANCE,
          "%d 번째 줄을 전수로 보니 글자가 있다" % cut)


def test_BOUNDARY_all_candidates_failing_verification_falls_back_to_forced():
    """창 안의 후보가 모두 숨은 글자뿐이면, 죽지 않고 강제/겹침 경로로 넘어간다."""
    width, height = 800, 4000
    image = _hidden_between_samples(width, height, 1280, 2560,
                                     hidden_top=1400, hidden_bottom=1650)
    got, forced = slicing.spans(image)     # 예외 없이 끝나야 한다
    check(forced > 0, "여백 후보가 전부 걸러졌으니 강제로 잘랐다고 알려야 한다")
    check_equal(got[0][0], 0, "맨 위에서 시작")
    check_equal(got[-1][1], height, "맨 아래에서 끝")
    for before, after in zip(got, got[1:]):
        check(after[0] <= before[1], "사이가 비면 안 된다: %r → %r" % (before, after))
