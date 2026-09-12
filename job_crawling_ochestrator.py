#!/usr/bin/env python3
"""다섯 채용 사이트를 한꺼번에 돌리고 결과를 합친다.

    python3 job_crawling_ochestrator.py

Wanted · 사람인 · 잡코리아 · 잡플래닛 · 점핏 을 **병렬로** 돌리고,
끝나면 각 사이트 CSV 를 그대로 이어 붙여 `csv/merged.csv` 를 만든다.

**사이트별 CSV 는 그대로 둔다.** 합친 파일은 사본이지 대체물이 아니다 — 어느 사이트에서
온 행인지는 `사이트명` 칸에 남아 있고, 한 사이트만 다시 돌리고 싶을 때는 그 사이트
스크래퍼를 따로 부르면 된다.

**전처리는 여기서 하지 않는다.** 중복 제거도, 정규화도, 거르기도 안 한다 — 그건 다음
단계의 일이다. 여기서 손대면 원본이 무엇이었는지 되짚을 수 없게 된다.

## 왜 프로세스를 나누나

각 스크래퍼는 자기 `lib/` 를 `sys.path` 맨 앞에 넣는다. 한 프로세스에서 여럿을 부르면
먼저 불린 사이트의 `lib.config` 가 캐시에 남아 뒤엣것이 그것을 쓴다 — 조용히 남의 조건으로
긁는다. 프로세스를 나누면 그럴 일이 없고, 하나가 죽어도 나머지가 산다.
"""
from __future__ import annotations

import csv
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SITES_DIR = ROOT_DIR / "job_sites"
OUTPUT = ROOT_DIR / "csv" / "merged.csv"
# 파이프라인 전체를 덮는 락. 단계별 락(`csv/.<단계>.lock`)과 이름이 안 겹쳐야 한다.
LOCK = ROOT_DIR / "csv" / ".pipeline.lock"

sys.path.insert(0, str(SITES_DIR))

from tqdm import tqdm                                        # noqa: E402

from _common import staleness                                # noqa: E402
from _common.runlock import guarded                          # noqa: E402
from _common.store import COLUMNS, FIRST_SEEN, KEY_COLUMN   # noqa: E402

# 돌릴 사이트. **순서가 곧 화면에 뜨는 순서**이고, 합칠 때도 이 차례를 지킨다 —
# 실행마다 행 순서가 뒤바뀌면 `merged.csv` 를 눈으로 견주기 어렵다.
SITES = ("wanted", "saramin", "jobkorea", "jobplanet", "jumpit")

# 한 사이트가 이보다 오래 걸리면 끊는다. 사람인이 8분대라 넉넉히 잡았다.
TIMEOUT_SECONDS = 60 * 30

# 실패한 사이트의 마지막 몇 줄을 보여 준다. 설정 오류 메시지가 여러 줄이라 넉넉히 잡았다.
MAX_ERROR_LINES = 8

# 자식이 stderr 로 한 말은 **끝에서 자르지 않고** 이만큼까지 그대로 보여 준다.
#
# 잡플래닛이 막혔을 때 스크래퍼는 `403 으로 막았습니다` 라고 실제로 찍었는데, 그 줄이
# stdout 에 있었고 stdout 끝 8줄은 corpus 안내문이 차지해 **정작 왜 막혔는지가 안 보였다.**
# 403(차단)과 429(속도 제한)는 대응이 정반대라 그 한 줄이 다음 실행을 가른다.
MAX_STDERR_LINES = 25

# 스크래퍼가 약속한 종료 코드. **`4` 는 실패가 아니다** — 잡플래닛이 "조건이 넓어
# 이번엔 건너뛴다" 고 말하는 신호다. 실패로 세면 파이프라인 전체가 멎는다.
EXIT_MEANING = {
    0: ("정상", True),
    1: ("설정 오류", False),
    2: ("온전히 못 걷음 — 차단이거나 상세를 못 받음 (모은 것은 저장됨)", False),
    3: ("이미 돌고 있음", False),
    4: ("조건이 넓어 건너뜀", True),
}
UNKNOWN = ("알 수 없는 종료 코드", False)


IMAGE_STAGE = ROOT_DIR / "job_image_process.py"

# 이미지 판독 단계가 내는 코드. **스크래퍼의 표를 빌려 쓰면 거짓말이 된다** — 이 단계는
# 사이트를 긁지 않는데 `2` 에 "차단이거나 상세를 못 받음" 이라고 찍혔다. 코드 숫자는
# 같은 계약이지만 뜻하는 사건이 다르므로 표를 따로 둔다. `4` 는 이 단계에 없다 —
# 건너뛸 조건이 없다.
IMAGE_EXIT_MEANING = {
    0: ("정상", True),
    1: ("단계를 못 돌림 — merged.csv 가 없거나 claude 명령을 못 찾음", False),
    2: ("시도한 그림을 하나도 못 읽음 (merged.csv 는 그대로)", False),
    3: ("이미 돌고 있음", False),
}


FILTER_STAGE = ROOT_DIR / "filter.py"

# 거르기 단계는 그물도 모델도 안 탄다 — 파일 하나를 읽고 정규식을 돌릴 뿐이다.
# 실측 710행에 0.02초. 5분이면 데이터가 백 배로 늘어도 남는다.
FILTER_TIMEOUT = 60 * 5

# 거르기가 내는 코드. **`2` 는 이 단계에 없다** — 부분 실패라는 것이 없다.
FILTER_EXIT_MEANING = {
    0: ("정상", True),
    1: ("단계를 못 돌림 — merged_read.csv 가 없음", False),
    3: ("이미 돌고 있음", False),
}


RATING_STAGE = ROOT_DIR / "jobplanet_rating.py"

# 평점 걷기는 **그물을 탄다.** 잡플래닛이 요청 간격을 보고 403 을 던지므로 5초씩 쉰다.
# 실측(2026-09-11) 457곳에 요청 660건·70분. 변형 사다리로 회사당 1.5회쯤 묻고,
# 403 이 11% 나서 건당 30초를 더 쓴다. 웹검색 되찾기까지 하면 더 는다.
# 넉넉히 세 시간을 준다 — 모자라서 끊기면 걷은 것을 살리려고 다시 처음부터 봐야 한다.
RATING_TIMEOUT = 60 * 180

# 평점 걷기가 내는 코드. **`2` 가 여기서는 실패가 아닌 "덜 걷었다"** 는 뜻이다 —
# 걷은 것은 저장됐고 다시 돌리면 이어받는다. 그래도 **성공으로 세지는 않는다.**
# 덜 걷힌 평점으로 거른 결과를 온전한 것으로 읽으면 안 된다.
RATING_EXIT_MEANING = {
    0: ("정상", True),
    1: ("단계를 못 돌림 — merged_filtered.csv 가 없음", False),
    2: ("차단이 실측과 다르게 굴어 덜 걷음 — **출력은 안 바꿨다.** 다시 돌리면 이어감", False),
    3: ("이미 돌고 있음", False),
}


CORE_STACK_STAGE = ROOT_DIR / "core_stack.py"

# 파일 하나를 읽고 정규식을 돌릴 뿐이다. 거르기와 같은 값이면 충분하다.
CORE_STACK_TIMEOUT = 60 * 5

# 핵심 기술 거르기가 내는 코드. `1` 에 **`.env` 얘기가 들어간다** — 이 단계만 `.env` 의
# `CORE_TECH_STACKS` 를 읽으므로, 다른 단계의 표를 빌려 쓰면 어디를 고쳐야 할지 못 짚는다.
CORE_STACK_EXIT_MEANING = {
    0: ("정상", True),
    1: ("단계를 못 돌림 — merged_rated.csv 가 없거나 .env 의 CORE_TECH_STACKS 가 빔", False),
    3: ("이미 돌고 있음", False),
}


HISTORY_STAGE = ROOT_DIR / "history.py"

# 파일 몇 개를 병합해 쓰고 사이트 CSV 를 지운다. 그물도 모델도 안 탄다.
HISTORY_TIMEOUT = 60 * 5

# 이력 단계가 내는 코드. `1` 은 **파이프라인이 안 끝났다**는 뜻이다 — 이 단계만
# 최종본까지 다 나온 것을 전제로 하므로 다른 단계의 표를 빌리면 뜻이 어긋난다.
HISTORY_EXIT_MEANING = {
    0: ("정상", True),
    1: ("단계를 못 돌림 — merged_read.csv 나 merged_core.csv 가 없음", False),
    3: ("이미 돌고 있음", False),
}


@dataclass
class Result:
    site: str
    code: int | None = None
    seconds: float = 0.0
    rows: int = 0
    output: Path | None = None
    log: str = ""
    # 자식이 **stderr 로 한 말**. `log` 와 따로 든다 — stdout 은 진행 기록이고
    # stderr 는 "왜 멈췄나" 다. 섞어 두면 끝 몇 줄을 볼 때 진행 기록에 밀려 사라진다.
    err: str = ""
    error: str = ""
    # 어느 종료 코드 표로 읽을 것인가. 기본은 스크래퍼의 표다.
    meanings: dict = field(default_factory=lambda: EXIT_MEANING)

    @property
    def meaning(self) -> str:
        return self.meanings.get(self.code, UNKNOWN)[0] if self.code is not None else self.error

    @property
    def ok(self) -> bool:
        """**실패가 아닌가.** 건너뛴 것(4)은 실패가 아니다."""
        return self.code is not None and self.meanings.get(self.code, UNKNOWN)[1]

    @property
    def stale(self) -> bool:
        """이번엔 못 걷었는데 CSV 는 남아 있는가.

        **그 행들은 지난 실행이 남긴 것**이다. 합치기는 하되(30일 누적이라 현재 상태의
        일부다) 이번에 걷은 것처럼 보이면 안 된다.
        """
        return not self.ok and self.rows > 0


def main() -> int:
    """**실행 락을 쥐고 돈다.**

    사이트와 단계에는 저마다 락이 있는데 **합치기 구간만 무방비였다.** 오케스트레이터를
    둘 돌리면 각 사이트는 `3` 을 내고 물러나지만, 그 뒤 두 실행이 같은 `merged.csv` 를
    함께 쓴다. 한쪽이 반쯤 쓴 것을 다른 쪽이 읽을 수 있다.

    락은 **파이프라인 전체**를 덮는다 — 수집부터 마지막 단계까지. 단계들이 자기 락을
    또 쥐지만 그것은 "이 단계만 따로 돌리는 사람" 을 막는 것이라 역할이 다르다.
    """
    return guarded(LOCK, _main)


def _main() -> int:
    scrapers = _find_scrapers()
    missing = [site for site in SITES if site not in scrapers]
    if missing:
        print("스크래퍼를 못 찾았습니다: %s" % ", ".join(missing), file=sys.stderr)
        print("  job_sites/<사이트>/<사이트>.py 가 있어야 합니다.", file=sys.stderr)
        return 1

    print("%d개 사이트를 병렬로 돌립니다 — %s\n" % (len(SITES), " · ".join(SITES)))
    started = time.monotonic()
    results = _run_all(scrapers)
    elapsed = time.monotonic() - started

    merged = merge_csvs([r.output for r in results if r.output], OUTPUT)
    _print_report(results, merged, elapsed)

    image = _run_stage(IMAGE_STAGE, "이미지판독", IMAGE_EXIT_MEANING)
    print("\n%s" % "\n".join(_last_lines(image.log, 12)))
    if not image.ok:
        print("이미지 판독 단계가 실패했습니다 (%s). csv/merged.csv 는 그대로 있습니다."
              % image.meaning, file=sys.stderr)

    # **앞이 죽으면 뒤를 안 부른다.** 거르기의 입력은 앞 단계가 낸 파일인데, 앞이 죽었으면
    # 거기 있는 것은 **지난 실행이 남긴 것**이다. 그것을 걸러 내면 어제 결과가 오늘 것처럼
    # 나온다 — 터지지 않고 조용히 틀리므로 알아채기가 가장 어렵다.
    filtered = _run_stage(FILTER_STAGE, "거르기", FILTER_EXIT_MEANING,
                          FILTER_TIMEOUT) if image.ok else None
    if filtered is not None:
        print("\n%s" % "\n".join(_last_lines(filtered.log, 12)))
        if not filtered.ok:
            print("거르기 단계가 실패했습니다 (%s). csv/merged_read.csv 는 그대로 있습니다."
                  % filtered.meaning, file=sys.stderr)

    rated = _run_stage(RATING_STAGE, "평점 거르기", RATING_EXIT_MEANING,
                       RATING_TIMEOUT) if (filtered is not None and filtered.ok) else None
    if rated is not None:
        print("\n%s" % "\n".join(_last_lines(rated.log, 14)))
        if not rated.ok:
            print("평점 단계가 실패했습니다 (%s). csv/merged_filtered.csv 는 그대로 있습니다."
                  % rated.meaning, file=sys.stderr)

    cored = _run_stage(CORE_STACK_STAGE, "핵심 기술 거르기", CORE_STACK_EXIT_MEANING,
                       CORE_STACK_TIMEOUT) if (rated is not None and rated.ok) else None
    if cored is not None:
        print("\n%s" % "\n".join(_last_lines(cored.log, 12)))
        if not cored.ok:
            print("핵심 기술 단계가 실패했습니다 (%s). csv/merged_rated.csv 는 그대로 있습니다."
                  % cored.meaning, file=sys.stderr)

    # **최종본까지 다 나왔을 때만 이력을 쌓는다.** 중간에 멈춘 실행의 반쪽 결과를
    # 이력에 섞으면, 나중에 "그때 이 공고가 없었다" 를 거짓으로 읽는다.
    history = _run_stage(HISTORY_STAGE, "이력 쌓기", HISTORY_EXIT_MEANING,
                         HISTORY_TIMEOUT) if (cored is not None and cored.ok) else None
    if history is not None:
        print("\n%s" % "\n".join(_last_lines(history.log, 12)))
        if not history.ok:
            print("이력 단계가 실패했습니다 (%s). csv/ 와 사이트 CSV 는 그대로 있습니다."
                  % history.meaning, file=sys.stderr)

    failed = [r for r in results if not r.ok]
    if failed:
        _print_failures(failed)
    stages = [image, filtered, rated, cored, history]
    return 1 if (failed or any(st is not None and not st.ok for st in stages)) else 0


def _print_failures(failed: list[Result]) -> None:
    """왜 실패했는지 **스크래퍼가 한 말을 그대로** 보여준다.

    "설정 오류" 라고만 하면 사람이 폴더를 하나씩 뒤져야 한다. 스크래퍼는 어느 `.env` 항목을
    채워야 하는지까지 말해 주므로, 그 말을 여기로 끌어올린다.

    **stderr 를 먼저 통째로 보여 준다.** 스크래퍼가 "왜 멈췄나" 를 말하는 자리가 거기다.
    stdout 은 진행 기록이라 양이 많고, 끝 몇 줄만 보면 정작 이유가 밀려 사라진다 —
    실제로 잡플래닛의 `403 으로 막았습니다` 를 그렇게 잃었다.
    """
    print("\n%s" % ("=" * 62), file=sys.stderr)
    print("실패한 사이트 %d곳" % len(failed), file=sys.stderr)
    for result in failed:
        print("\n── %s (%s)" % (result.site, result.meaning), file=sys.stderr)
        said = _first_lines(result.err, MAX_STDERR_LINES)
        if said:
            print("   [스크래퍼가 말한 것]", file=sys.stderr)
            for line in said:
                print("   %s" % line, file=sys.stderr)
            print("   [진행 기록 끝부분]", file=sys.stderr)
        for line in _last_lines(result.log, MAX_ERROR_LINES):
            print("   %s" % line, file=sys.stderr)


def _first_lines(text: str, count: int) -> list[str]:
    """진행 막대와 빈 줄을 빼고 **앞에서** 몇 줄.

    stderr 는 앞쪽이 중요하다 — 처음 막힌 곳이 이유이고, 뒤따르는 것은 그 여파다.
    """
    return _clean_lines(text)[:count]


def _last_lines(text: str, count: int) -> list[str]:
    """진행 막대와 빈 줄을 빼고 **끝에서** 몇 줄. 오류는 대개 끝에 있다."""
    return _clean_lines(text)[-count:]


def _clean_lines(text: str) -> list[str]:
    """진행 막대와 빈 줄을 뺀 줄들."""
    lines = []
    for raw in (text or "").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        if line.strip() and "|" not in line[:20]:      # tqdm 막대는 건너뛴다
            lines.append(line)
    return lines


def _find_scrapers() -> dict[str, Path]:
    return {site: SITES_DIR / site / ("%s.py" % site)
            for site in SITES if (SITES_DIR / site / ("%s.py" % site)).exists()}


def _run_all(scrapers: dict[str, Path]) -> list[Result]:
    """전부를 동시에 돌린다. **각자 다른 프로세스**라 서로를 못 건드린다.

    자식의 출력은 붙잡아 둔다 — 여럿이 동시에 tqdm 을 그리면 화면이 엉킨다. 대신 여기서
    막대 하나로 진행을 보이고, 끝난 사이트부터 한 줄씩 알린다.
    """
    results: dict[str, Result] = {}
    with ThreadPoolExecutor(max_workers=len(scrapers)) as pool:
        pending = {pool.submit(_run_one, site, path): site
                   for site, path in scrapers.items()}
        with tqdm(total=len(pending), desc="사이트", unit="곳") as bar:
            for future in as_completed(pending):
                result = future.result()
                results[result.site] = result
                bar.update(1)
                tqdm.write("  %s %-10s %6.1f초 · %s"
                           % ("✓" if result.ok else "✗", result.site,
                              result.seconds, _tail(result)))
    return [results[site] for site in SITES if site in results]


def _run_one(site: str, script: Path) -> Result:
    """스크래퍼 하나를 별도 프로세스로 돌린다."""
    result = Result(site=site)
    started = time.monotonic()
    try:
        done = subprocess.run(
            [sys.executable, script.name],
            cwd=script.parent, capture_output=True, text=True,
            timeout=TIMEOUT_SECONDS,
        )
        result.code = done.returncode
        result.log = (done.stdout or "") + (done.stderr or "")
        result.err = done.stderr or ""
    except subprocess.TimeoutExpired:
        result.error = "%d분을 넘겨 끊었습니다" % (TIMEOUT_SECONDS // 60)
    except Exception as error:                     # 여기서 죽으면 나머지 사이트도 잃는다
        result.error = "%s: %s" % (type(error).__name__, error)
    result.seconds = time.monotonic() - started

    # **이번에 걷은 수가 아니라 지금 CSV 에 있는 수**다. 사이트 CSV 는 30일 누적이라,
    # 이번 실행이 실패해도 앞서 걷어 둔 것이 남아 있다 — 그것도 "현재 상태" 의 일부라
    # 합치기는 하되, 이번에 걷은 것처럼 보이지 않게 화면에서 갈라 적는다.
    output = script.parent / "csv" / ("%s_post.csv" % site)
    if output.exists():
        result.output = output
        result.rows = count_rows(output)
    return result


def count_rows(path: Path) -> int:
    """CSV 의 **데이터 행** 수. 본문에 줄바꿈이 들어 있어 줄 수로 세면 안 된다."""
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return max(0, sum(1 for _ in csv.reader(handle)) - 1)
    except OSError:
        return 0


def _run_stage(script: Path, name: str, meanings: dict,
               timeout: int = TIMEOUT_SECONDS) -> Result:
    """수집 뒤 단계 하나를 **자식 프로세스로** 돌린다.

    불러들이지(import) 않는다 — 위의 "왜 프로세스를 나누나" 와 같은 이유다. 그리고
    이 단계들은 혼자서도 도는 엔트리포인트라, 여기서만 쓰는 다른 길을 만들 이유가 없다.

    **종료 코드 표를 인자로 받는다.** 숫자는 같은 계약이지만 뜻하는 사건이 단계마다
    다르다 — 이미지 판독의 `2` 를 거르기에 갖다 붙이면 있지도 않은 사건이 화면에 찍힌다.
    """
    result = Result(site=name, meanings=meanings)
    started = time.monotonic()
    try:
        # **사슬 안이라고 알린다.** 방금 앞 단계가 만든 파일이므로 "입력이 낡았다" 를
        # 물을 이유가 없다. 물으면 자식이 tty 를 못 잡아 멈춰 버린다.
        done = subprocess.run(
            [sys.executable, script.name],
            cwd=ROOT_DIR, capture_output=True, text=True, timeout=timeout,
            env={**os.environ, staleness.CHAIN_ENV: "1"},
        )
        result.code = done.returncode
        result.log = (done.stdout or "") + (done.stderr or "")
        result.err = done.stderr or ""
    except subprocess.TimeoutExpired:
        result.error = "%d분을 넘겨 끊었습니다" % (timeout // 60)
    except Exception as error:
        result.error = "%s: %s" % (type(error).__name__, error)
    result.seconds = time.monotonic() - started
    # **`output`/`rows` 는 채우지 않는다.** 이 단계가 파일을 쓰기 전에 끝났으면 거기 있는
    # 산출물은 **지난 실행이 남긴 것**이다. 그것을 이번 결과로 적어 두면,
    # 나중에 누가 이 값을 화면에 끌어다 쓰는 순간 지난 데이터가 이번 것으로 보고된다.
    # 사이트 CSV 와 달리 여기서는 그 수를 밝힐 곳도 없다(`stale` 은 합치기 얘기다).
    return result


# 이력이 쌓이는 자리. 합칠 때 여기서 `최초수집일` 을 되살려 넣는다.
HISTORY_READ = ROOT_DIR / "history" / "history_read.csv"


def _seed_first_seen(rows: list[dict], history: Path) -> int:
    """이력에서 **진짜 `최초수집일`** 을 되살려 넣는다. 몇 행을 되살렸는지 돌려준다.

    사이트별 CSV 가 예전에는 누적 저장소였다 — `store.save()` 가 기존 파일과 병합해
    처음 본 날을 지켰다. 이제 그 파일을 매 실행 지우므로(`history.py`), 그냥 두면
    **`최초수집일` 이 항상 오늘**이 되어 칸의 뜻이 없어진다.

    그래서 누적의 자리를 `history/history_read.csv` 로 옮기고, 합칠 때 URL 로 찾아
    되살린다. 이력에 없는 공고는 **오늘 처음 본 것**이 맞으므로 손대지 않는다.
    """
    if not history.exists():
        return 0
    known = {row.get(KEY_COLUMN): row.get(FIRST_SEEN)
             for row in _read_rows(history) if row.get(KEY_COLUMN)}
    revived = 0
    for row in rows:
        seen = known.get(row.get(KEY_COLUMN))
        if seen and seen != row.get(FIRST_SEEN):
            row[FIRST_SEEN] = seen
            revived += 1
    return revived


def merge_csvs(paths: list[Path], output: Path, history: Path = HISTORY_READ) -> int:
    """사이트별 CSV 를 **그대로** 이어 붙인다. 몇 행을 썼는지 돌려준다.

    **손대지 않는다** — 중복 제거도, 정규화도, 거르기도 안 한다. 그건 다음 단계의 일이고,
    여기서 손대면 원본이 무엇이었는지 되짚을 수 없게 된다.

    칸은 `_common/store.py` 의 `COLUMNS` 로 맞춘다. 사이트가 다 같은 스키마를 쓰지만,
    한 곳이 칸을 더하거나 빼도 합친 파일이 어긋나지 않게 여기서 한 번 더 맞춘다.
    """
    # **원자적으로 쓴다.** 같은 디렉터리 임시 파일에 다 쓰고 `os.replace` 로 바꿔치기한다.
    #
    # 여기만 이 규칙에서 빠져 있었다 — `_common/store.write_csv` 도, 단계들의 보고 CSV 도
    # 전부 원자적인데 정작 **파이프라인의 첫 파일**이 아니었다. 도중에 죽으면 반쯤 쓰인
    # `merged.csv` 가 남고, 그림 판독이 그것을 완성품으로 읽는다.
    # `image_process/README.md` 가 금지한 바로 그 상황이다.
    rows = [row for path in paths for row in _read_rows(path)]
    revived = _seed_first_seen(rows, history)

    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(".%s.tmp%d" % (output.name, os.getpid()))
    try:
        with tmp.open("w", encoding="utf-8-sig", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=list(COLUMNS))
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row.get(column, "") for column in COLUMNS})
            target.flush()
            os.fsync(target.fileno())
        os.replace(tmp, output)
    finally:
        tmp.unlink(missing_ok=True)
    if revived:
        print("  이력에서 최초수집일을 되살린 공고: %d행" % revived)
    return len(rows)


def _read_rows(path: Path) -> list[dict]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError:
        return []


def _tail(result: Result) -> str:
    """한 줄 요약. 실패면 왜인지, 정상이면 몇 행인지.

    **이번에 못 걷었는데 CSV 가 남아 있으면 그렇게 밝힌다** — 안 그러면 실패한 사이트가
    행을 걷어 온 것처럼 보인다.
    """
    if result.code is None:
        return result.error or "알 수 없는 실패"
    if result.ok:
        return "%s · %d행" % (result.meaning, result.rows)
    if result.stale:
        return "%s (이번엔 못 걷음 · 지난 CSV %d행은 그대로 있음)" % (result.meaning, result.rows)
    return result.meaning


def _print_report(results: list[Result], merged: int, elapsed: float) -> None:
    print("\n%s" % ("=" * 62))
    print("%-10s %6s %8s %7s  %s" % ("사이트", "종료", "소요", "CSV행", "뜻"))
    for result in results:
        print("%-10s %6s %7.1f초 %6d  %s"
              % (result.site,
                 "-" if result.code is None else result.code,
                 result.seconds, result.rows, _tail(result)))
    print("%s" % ("-" * 62))
    print("%-10s %6s %7.1f초 %6d  %s"
          % ("합계", "", elapsed, sum(r.rows for r in results),
             "가장 오래 걸린 곳: %s (병렬이라 합이 아니다)"
             % max(results, key=lambda r: r.seconds).site))

    print("\n%s — %d행" % (OUTPUT.relative_to(ROOT_DIR), merged))
    print("  사이트별 CSV 는 그대로 두었습니다. 어느 사이트에서 왔는지는 `사이트명` 칸에 있습니다.")
    print("  **손대지 않고 그대로 이어 붙였습니다** — 중복 제거·정규화는 다음 단계의 일입니다.")

    stale = [r for r in results if r.stale]
    if stale:
        print("\n  이번에 못 걷은 사이트의 지난 CSV 도 합쳤습니다: %s"
              % ", ".join("%s %d행" % (r.site, r.rows) for r in stale))
        print("  사이트 CSV 는 30일 누적이라 그 행들도 현재 상태의 일부입니다.")
        print("  언제 걷힌 것인지는 `최종확인일` 칸을 보세요.")

    skipped = [r for r in results if r.code == 4]
    if skipped:
        print("\n  건너뛴 사이트: %s" % ", ".join(r.site for r in skipped))
        print("  실패가 아닙니다 — 조건이 넓어 절반만 걷힐 상황이라 아예 안 걷은 것입니다.")
        print("  조건을 좁히면 걷힙니다. 그 사이트의 README.md 를 보세요.")


if __name__ == "__main__":
    raise SystemExit(main())
