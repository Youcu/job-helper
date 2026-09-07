#!/usr/bin/env python3
"""테스트를 전부 모아 돌린다.

    python3 tests/run.py

세 갈래로 나눠 센다 — 이름 앞자리가 갈래다.

    test_NORMAL_…     제대로 된 입력이 제대로 나오는가
    test_EXCEPTION_…  망가진 입력에 어떻게 반응하는가
    test_BOUNDARY_…   0, 1, 최대, 딱 떨어지는 지점, 뒤집힌 범위

**통과시키려고 쓴 테스트가 아니다.** 코드를 적대적으로 읽고 "여기가 틀렸을 것 같다" 는 곳을
먼저 찔러 본 뒤, 실제로 틀린 것만 굳혔다. 잡코리아에서는 그림 주소 뽑기에서 2건이 실제 결함이었다.
그 테스트에는 `# 결함:` 주석이 붙어 있다.

네트워크를 타지 않는다 — 떠 놓은 실제 공고 `fixtures/pages.json` 을 쓴다.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

MODULES = [
    "tests.test_config",
    "tests.test_client",
    "tests.test_filters",
    "tests.test_collect",
    "tests.test_body",
    "tests.test_skills",
    "tests.test_record",
    "tests.test_jobkorea",
]

KIND_LABEL = {"NORMAL": "일반", "EXCEPTION": "예외", "BOUNDARY": "경계"}


def collect_tests() -> list[tuple[str, str, str, callable]]:
    """(갈래, 모듈, 이름, 함수) 목록."""
    found = []
    for module_name in MODULES:
        module = importlib.import_module(module_name)
        for name in sorted(dir(module)):
            if not name.startswith("test_"):
                continue
            fn = getattr(module, name)
            if callable(fn):
                found.append((name.split("_")[1], module_name.split(".")[-1], name, fn))
    return found


def _check_module_list_is_complete() -> None:
    """`MODULES` 가 `tests/` 의 파일을 다 담고 있는가.

    **손으로 적는 목록이라 새 파일을 빠뜨리면 그 테스트가 조용히 안 돈다.**
    실제로 그랬다 — 새로 쓴 `test_outcome.py` 열 건이 통과도 실패도 하지 않고
    없는 것처럼 지나갔고, 개수만 보고는 알 수 없었다.
    """
    here = Path(__file__).resolve().parent
    on_disk = {"tests.%s" % p.stem for p in here.glob("test_*.py")}
    missing = sorted(on_disk - set(MODULES))
    if missing:
        raise SystemExit(
            "tests/run.py 의 MODULES 에 안 적힌 테스트 파일이 있습니다: %s\n"
            "  적지 않으면 그 테스트는 돌지 않습니다. MODULES 에 넣어 주세요."
            % ", ".join(missing))

def main() -> int:
    _check_module_list_is_complete()
    tests = collect_tests()
    failed: list[tuple[str, Exception]] = []

    for kind in ("NORMAL", "EXCEPTION", "BOUNDARY"):
        group = [t for t in tests if t[0] == kind]
        print(f"\n[{KIND_LABEL[kind]}] {len(group)}건")
        current_module = None
        for _, module, name, fn in group:
            if module != current_module:
                current_module = module
                print(f"  · {module}")
            try:
                fn()
                print(f"      PASS  {name}")
            except AssertionError as exc:
                failed.append((name, exc))
                print(f"      FAIL  {name}\n              {exc}")
            except Exception as exc:      # 테스트가 터지는 것도 실패다
                failed.append((name, exc))
                print(f"      ERROR {name}\n              {type(exc).__name__}: {exc}")

    print(f"\n{'=' * 60}")
    if failed:
        print(f"{len(tests)}건 중 {len(failed)}건 실패")
        for name, exc in failed:
            print(f"  - {name}: {exc}")
        return 1
    print(f"{len(tests)}건 전부 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
