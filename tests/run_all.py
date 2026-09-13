#!/usr/bin/env python3
"""저장소의 **모든** 테스트를 한 명령으로 돌린다.

    python3 tests/run_all.py

러너가 여섯이다 — 루트 하나와 사이트 다섯. 지금까지는 사람이 여섯 번 쳐야 했고,
`cd` 도 사이트마다 해야 했다. **그래서 한 번 잊으면 그 묶음이 조용히 안 돌았다.**

각 러너에는 "`MODULES` 에 안 적힌 테스트 파일" 을 잡는 장치가 있다. 그런데 그것은
**러너 안의 누락**만 막고 **러너 자체를 안 돌린 것**은 못 막는다. 이 파일이 그 구멍을 막는다.

## 왜 import 하지 않고 자식 프로세스로 부르나

러너 여섯이 저마다 `sys.path` 를 자기 사이트 쪽으로 밀어 넣는다
(`job_sites/<사이트>/tests/run.py` 의 맨 위). 한 프로세스에서 여섯을 이어 import 하면
**나중 것이 앞 것의 `lib` 를 집어** 엉뚱한 사이트 코드를 시험한다. 사이트마다 `lib/` 라는
같은 이름을 쓰기 때문이다.

프로세스를 나누면 그 문제가 아예 없다. 느려지지만(실측 여섯 묶음에 몇 초) 대신
**어느 묶음이 깨졌는지가 섞이지 않는다.**

## 무엇을 안 하나

테스트를 **고르거나 거르지 않는다.** 이름으로 필터링하는 기능을 두면 CI 가 "일부만 돌고
초록" 인 상태를 만들 수 있다. 여기서는 전부 돌거나 전부 안 돌거나 둘 중 하나다.

종료 코드
    0  전부 통과
    1  한 묶음이라도 실패
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# **여기 적힌 차례대로 돈다.** 루트를 먼저 두는 이유는 파이프라인 단계가 거기 있어서다 —
# 무엇이 깨졌는지 화면 위쪽에서 먼저 보이는 편이 낫다.
RUNNERS = [
    ("오케스트레이터·단계", ROOT / "tests" / "run.py"),
    ("wanted", ROOT / "job_sites" / "wanted" / "tests" / "run.py"),
    ("saramin", ROOT / "job_sites" / "saramin" / "tests" / "run.py"),
    ("jobkorea", ROOT / "job_sites" / "jobkorea" / "tests" / "run.py"),
    ("jobplanet", ROOT / "job_sites" / "jobplanet" / "tests" / "run.py"),
    ("jumpit", ROOT / "job_sites" / "jumpit" / "tests" / "run.py"),
]

# 러너가 마지막에 찍는 줄에서 건수를 읽는다 — `N건 전부 통과` 또는 `N건 중 M건 실패`.
# **못 읽어도 실패로 치지 않는다.** 건수는 보고용이고, 성패는 종료 코드가 정한다.
import re
_COUNT = re.compile(r"(\d+)건")


def _missing() -> list[Path]:
    """목록에 적혔는데 디스크에 없는 러너.

    사이트를 지우고 여기를 안 고치면 그 묶음이 조용히 안 돈다 — 러너들이 자기
    `MODULES` 에서 막는 것과 같은 종류의 사고다.
    """
    return [path for _name, path in RUNNERS if not path.exists()]


def _run(name: str, runner: Path) -> tuple[int, int, float]:
    """(종료 코드, 건수, 초). 자식의 출력은 그대로 흘려보낸다."""
    print("\n%s\n── %s  (%s)\n%s" % ("=" * 62, name,
                                     runner.relative_to(ROOT), "=" * 62), flush=True)
    started = time.monotonic()
    done = subprocess.run([sys.executable, runner.name], cwd=runner.parent,
                          capture_output=True, text=True)
    seconds = time.monotonic() - started
    sys.stdout.write(done.stdout or "")
    sys.stderr.write(done.stderr or "")
    tail = [line for line in (done.stdout or "").strip().split("\n") if "건" in line]
    found = _COUNT.search(tail[-1]) if tail else None
    return done.returncode, int(found.group(1)) if found else 0, seconds


def main() -> int:
    gone = _missing()
    if gone:
        print("러너를 못 찾았습니다: %s" % ", ".join(str(p.relative_to(ROOT)) for p in gone),
              file=sys.stderr)
        print("  tests/run_all.py 의 RUNNERS 와 디스크가 어긋났습니다.", file=sys.stderr)
        return 1

    results = []
    for name, runner in RUNNERS:
        results.append((name,) + _run(name, runner))

    total = sum(count for _n, _c, count, _s in results)
    failed = [name for name, code, _c, _s in results if code != 0]

    print("\n%s\n전체" % ("=" * 62))
    for name, code, count, seconds in results:
        print("  %-20s %5d건  %5.1f초  %s"
              % (name, count, seconds, "통과" if code == 0 else "**실패**"))
    print("%s" % ("-" * 62))
    if failed:
        print("%d건 중 %d묶음 실패: %s" % (total, len(failed), ", ".join(failed)))
        return 1
    print("%d건 전부 통과 (%d묶음)" % (total, len(results)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
