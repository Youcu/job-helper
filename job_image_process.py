#!/usr/bin/env python3
"""합본에서 **본문이 그림인 공고**만 골라 그림을 읽는다.

    python3 job_image_process.py

`csv/merged.csv` 를 읽어 `csv/merged_read.csv` 를 낸다. **원본은 고치지 않는다** — 이
단계는 행을 없애기 때문에, 제자리에서 고치면 없어진 공고의 원본이 어디에도 안 남는다.

혼자서도 돌고, `job_crawling_ochestrator.py` 가 자식 프로세스로 부르기도 한다. 수집이
8~10분인데 이미지 쪽만 다시 돌려 보고 싶을 때가 반드시 온다 — 프롬프트를 고쳤을 때,
모델을 바꿔 볼 때, 캐시를 지우고 다시 읽을 때.

## 버림과 실패를 가른다

모델이 답했는데 셋 다 비면 **버린다.** 우리가 못 받거나 못 읽은 것은 **안 버린다** —
원래 모습대로 남기고 몇 건인지 찍는다. 이 구분이 뚫리면 우리 사고로 데이터가 사라진다.

## 캐시는 공고 하나에 열쇠 하나다

한 공고의 그림들을 합쳐 한 번 읽으므로, 그 답은 **주소 목록 전체**의 답이다. 낱장 주소를
열쇠로 쓰면 같은 그림을 쓰는 다른 공고가 남의 답을 받아 간다(`image_process/cache.py`).
그래서 옛 캐시 파일의 낱장 열쇠는 **전부 빗나가고**, 첫 실행에서 공고 단위로 다시 채워진다.
캐시는 편의지 진실이 아니므로 그래도 된다.
"""
from __future__ import annotations

import shutil
import sys
import threading
import warnings
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
INPUT = ROOT_DIR / "csv" / "merged.csv"
OUTPUT = ROOT_DIR / "csv" / "merged_read.csv"
LOCK = ROOT_DIR / "csv" / ".image_process.lock"
RETRY_PAUSE = 5      # 다시 걸기 전에 쉬는 시간(초)

sys.path.insert(0, str(ROOT_DIR / "job_sites"))
sys.path.insert(0, str(ROOT_DIR))

from tqdm import tqdm                                              # noqa: E402

from _common.env import ConfigError                                # noqa: E402
from _common.runlock import guarded                                # noqa: E402
from _common.store import COLUMNS, read_csv, write_csv             # noqa: E402
from image_process import cache, config, fetch, fill, reader, slicing   # noqa: E402


@dataclass
class Outcome:
    kind: str                 # 채움 · 캐시 · 버림 · 껍데기 · 못읽음
    row: dict | None
    note: str = ""


_현재 = threading.local()


def note_current_image(url: str | None) -> None:
    """이 실이 지금 어느 그림을 다루는지 적어 둔다. 경고가 났을 때 짚어 주려고."""
    _현재.url = url


@contextmanager
def warnings_through_bar():
    """경고를 **진행 막대 위로** 올린다.

    경고는 stderr 로 나가는데 tqdm 막대도 stderr 를 쓴다. 그대로 두면 막대가 덮어써서
    실행 로그에 `warnings.warn(` 마지막 줄만 남는다 — 실제 전체 실행에서 그렇게 한 건을
    잃었고 어느 그림 때문인지 끝내 못 찾았다.

    **이게 그냥 미관 문제가 아니다.** Pillow 는 픽셀이 8,900만을 넘으면 경고만 내고 그림은
    읽는다(오류는 그 두 배부터). 그 구간의 그림은 조용히 지나가므로, 경고가 묻히면 우리가
    무엇을 아슬아슬하게 읽고 있는지 알 방법이 없다.

    `warnings.catch_warnings` 를 쓰지 않는다 — 전역 상태를 건드려서 실 여럿이 함께 돌면
    서로를 덮어쓴다. 여기는 동시 16개까지 돈다.
    """
    original = warnings.showwarning

    def through(message, category, filename, lineno, file=None, line=None):
        where = getattr(_현재, "url", None)
        tqdm.write("  경고: %s: %s%s"
                   % (category.__name__, message, " — %s" % where if where else ""))

    warnings.showwarning = through
    try:
        yield
    finally:
        warnings.showwarning = original


def image_urls(row: dict) -> list[str]:
    """이 행이 그림 본문인가. 맞으면 주소들, 아니면 빈 목록.

    수집 단계가 본문이 그림이면 `기술스택` 칸에 주소를 남긴다(D-13).

    **칸 안 어디에 있든 찾는다.** 처음에는 칸이 `http` 로 시작하는지만 봤다. "주소와 진짜
    기술이 섞인 행은 0건" 이라는 실측을 근거로 삼았는데 **그 실측이 틀렸다** — `http` 로
    시작하는 행만 골라 놓고 그 안에서 섞인 것을 찾는 순환 논증이었다.

    사람인은 기술을 먼저 주고 주소를 뒤에 붙인다 — `C++, C, Java, https://…/recruit.png`.
    실제 데이터에서 주소가 든 175행 중 **73행(42%)** 이 이 모양이라 판독 단계를 통째로
    지나갔고, 그 공고들의 내용은 그림 안에 있는데 아무도 안 읽었다.
    """
    parts = [one.strip() for one in (row.get("기술스택") or "").split(",") if one.strip()]
    return [one for one in parts if one.startswith("http")]


def _download_once_more_if_needed(url: str, target: Path) -> None:
    """그림 하나를 받는다. **끊기면 한 번만 다시 받는다.**

    처음에는 비싼 모델 호출에만 재시도를 걸었는데, 실측해 보니 거꾸로였다. 두 번의 전체
    실행에서 최종 실패 3건 중 **2건이 그림 서버가 연결을 끊은 것**이었고, 모델 호출은
    한 번도 안 끊겼다. 그리고 실패한 그림들은 나중에 단독으로 받으면 멀쩡히 받힌다.

    내려받기는 값이 거의 안 드니 한 번 더 두드리는 비용이 없다. 비싼 것은 모델 호출이다.
    """
    last = None
    for attempt in range(2):
        try:
            fetch.download(url, target)
            return
        except fetch.FetchError as error:
            last = error
            if attempt == 0:
                time.sleep(RETRY_PAUSE)
    raise last


def process_one(row: dict, *, cfg, book: dict, work_dir: Path, reader_fn=None) -> Outcome:
    urls = image_urls(row)
    read_fn = reader_fn or (lambda paths, **kw: reader.read(paths, **kw))
    if not urls:
        # 그림 행이 아닌데 불렸다. **행을 건드리지 않고 돌려준다** — 여기서 껍데기로
        # 흘러가면 그림도 아닌 행이 버려지고, 빈 주소 목록이 캐시 열쇠가 된다.
        return Outcome("못읽음", dict(row), "그림 주소가 없다")

    # **공고 하나에 열쇠 하나.** 낱장으로 맞춰 보면 남의 공고 답을 받아 온다.
    cached = cache.get(book, urls)
    if cached is not None:
        if not fill.has_anything(cached):
            return Outcome("버림", None, "캐시: 쓸 게 없음")
        return Outcome("캐시", fill.apply(row, cached))

    work = Path(work_dir) / "그림"
    work.mkdir(parents=True, exist_ok=True)
    pieces: list[Path] = []
    for index, url in enumerate(urls):
        target = work / ("%02d%s" % (index, Path(url.split("?")[0]).suffix or ".img"))
        note_current_image(url)
        try:
            _download_once_more_if_needed(url, target)
            # **못 받은 것과 못 연 것은 같은 종류의 실패다.** 둘 다 "그림에 내용이 없다"
            # 가 아니라 "우리가 못 봤다" 라서, 버리지도 캐시에 넣지도 않는다.
            #
            # **다만 재시도는 내려받기에만 건다.** 받아졌는데 안 열리는 파일은 같은 바이트를
            # 다시 열어 봐야 결과가 같다 — 2억 3천만 픽셀짜리 그림이 실제로 그랬다.
            junk = fetch.is_junk(target)
        except fetch.FetchError as error:
            return Outcome("못읽음", dict(row), str(error))
        if junk:
            continue
        pieces.extend(slicing.slice_image(target, work / ("조각%02d" % index)))
    note_current_image(None)

    if not pieces:
        # 껍데기뿐이다. **모델을 부르지 않고** 버린다 — 부를 이유도 없고 돈만 든다.
        cache.put(book, urls, {name: [] for name in reader.FIELDS}, cfg.model)
        return Outcome("껍데기", None, "글이 담길 수 없는 그림뿐")

    # **한 번만 다시 건다.** 실패는 대개 잠깐의 일이라 쉬었다 걸면 통과한다.
    # 두 번째도 실패하면 실패로 둔다 — 계속 매달리면 뒤엣것이 밀린다.
    last = None
    for attempt in range(2):
        try:
            got = read_fn(pieces, model=cfg.model, timeout=cfg.timeout)
            break
        except reader.ReadError as error:
            last = error
            if attempt == 0:
                time.sleep(RETRY_PAUSE)
    else:
        # **우리가 못 읽은 것이지 그림에 내용이 없는 게 아니다.** 캐시에도 안 넣는다.
        return Outcome("못읽음", dict(row), str(last))

    cache.put(book, urls, got, cfg.model)
    if not fill.has_anything(got):
        return Outcome("버림", None, "읽었는데 쓸 게 없음")
    return Outcome("채움", fill.apply(row, got))


def main() -> int:
    return guarded(LOCK, _run)


def _run() -> int:
    try:
        cfg = config.load_config()
    except ConfigError as error:
        print("설정 오류: %s" % error, file=sys.stderr)
        return 1
    if not INPUT.exists():
        print("%s 가 없습니다. 먼저 수집을 돌리세요." % INPUT, file=sys.stderr)
        return 1
    if not shutil.which("claude"):
        print("claude 명령을 못 찾았습니다. 이 단계는 그것으로 그림을 읽습니다.",
              file=sys.stderr)
        return 1

    rows = read_csv(INPUT)
    targets = [index for index, row in enumerate(rows) if image_urls(row)]
    print("이미지 본문 %d건을 읽습니다 (동시 %d개 · %s)"
          % (len(targets), cfg.workers, cfg.model))

    book = cache.load(cache.CACHE_PATH)
    stats = {"채움": 0, "캐시": 0, "버림": 0, "껍데기": 0, "못읽음": 0}
    kept: dict[int, dict | None] = {}
    work_root = Path(tempfile.mkdtemp(prefix="image_process_"))
    try:
      # 경고를 막대 위로 올려 둔 채로 돈다 — 안 그러면 막대가 덮어써 사라진다.
      with warnings_through_bar(), ThreadPoolExecutor(max_workers=cfg.workers) as pool:
            futures = {
                pool.submit(process_one, rows[index], cfg=cfg, book=book,
                            work_dir=work_root / str(index)): index
                for index in targets
            }
            # **`as_completed` 여야 실제로 기다린다.** dict 를 그냥 돌면 제출만 하고 지나간다.
            for future in tqdm(as_completed(futures), total=len(futures),
                               desc="그림", unit="건"):
                index = futures[future]
                try:
                    outcome = future.result()
                except Exception as error:
                    # 한 건 때문에 전체를 잃지 않는다. **버림이 아니라 못읽음이다.**
                    outcome = Outcome("못읽음", dict(rows[index]),
                                      "%s: %s" % (type(error).__name__, error))
                stats[outcome.kind] += 1
                kept[index] = outcome.row
                if outcome.kind == "못읽음":
                    tqdm.write("  %s 못 읽음: %s" % (rows[index].get("URL"), outcome.note))
    finally:
        shutil.rmtree(work_root, ignore_errors=True)
        cache.save(cache.CACHE_PATH, book)

    out = []
    for index, row in enumerate(rows):
        if index not in kept:
            out.append(row)              # 그림 행이 아니다. 그대로 통과
        elif kept[index] is not None:
            out.append(kept[index])      # 채웠거나, 못 읽어 원래대로 남긴 것
        # kept[index] 가 None 이면 버린 것이다
    write_csv(OUTPUT, out)
    _report(stats, len(rows), len(out))

    # **`2` 는 "아무것도 못 해냈다" 는 뜻이다.** 캐시 적중도 해낸 것이다 — 안 그러면
    # 정상 상태(거의 전부 캐시)에서 새 공고 하나가 시간 초과만 나도 실행 전체가 실패로
    # 보고되고, 오케스트레이터는 여덟 분짜리 수집을 실패로 적는다.
    usable = stats["채움"] + stats["캐시"] + stats["버림"] + stats["껍데기"]
    if stats["못읽음"] and not usable:
        print("\n%d건을 시도해 하나도 못 읽었습니다 — 온전한 결과가 아닙니다."
              % stats["못읽음"], file=sys.stderr)
        return 2
    return 0


def _report(stats: dict, before: int, after: int) -> None:
    print("  캐시에서 바로       : %d건" % stats["캐시"])
    print("  껍데기라 안 부름     : %d건 → 버림" % stats["껍데기"])
    print("  읽어서 채움         : %d건" % stats["채움"])
    print("  읽었는데 쓸 게 없음  : %d건 → 버림" % stats["버림"])
    print("  못 읽음 (그대로 둠)  : %d건" % stats["못읽음"])
    print("\n%s — %d행 (%s %d행에서 %d건 버림)"
          % (OUTPUT.relative_to(ROOT_DIR), after,
             INPUT.relative_to(ROOT_DIR), before, before - after))


if __name__ == "__main__":
    raise SystemExit(main())
