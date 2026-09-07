#!/usr/bin/env python3
"""오케스트레이터 테스트를 모아 돌린다.

    python3 tests/run.py

세 갈래로 나눠 센다 — 이름 앞자리가 갈래다 (일반 / 예외 / 경계).
자식 프로세스도 네트워크도 타지 않는다.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "job_sites"))

MODULES = ["tests.test_merge", "tests.test_orchestrator"]
KIND_LABEL = {"NORMAL": "일반", "EXCEPTION": "예외", "BOUNDARY": "경계"}


def _check_module_list_is_complete() -> None:
    """`MODULES` 가 `tests/` 의 파일을 다 담고 있는가.

    **손으로 적는 목록이라 새 파일을 빠뜨리면 그 테스트가 조용히 안 돈다.**
    실제로 그랬다 — 새로 쓴 테스트 열 건이 통과도 실패도 하지 않고 없는 것처럼
    지나갔고, 개수만 보고는 알 수 없었다.
    """
    here = Path(__file__).resolve().parent
    on_disk = {"tests.%s" % f.stem for f in here.glob("test_*.py")}
    missing = sorted(on_disk - set(MODULES))
    if missing:
        raise SystemExit(
            "tests/run.py 의 MODULES 에 안 적힌 테스트 파일이 있습니다: %s\n"
            "  적지 않으면 그 테스트는 돌지 않습니다. MODULES 에 넣어 주세요."
            % ", ".join(missing))


def main() -> int:
    _check_module_list_is_complete()
    tests = []
    for name in MODULES:
        module = importlib.import_module(name)
        for attr in sorted(dir(module)):
            if attr.startswith("test_") and callable(getattr(module, attr)):
                tests.append((attr.split("_")[1], name.split(".")[-1], attr,
                              getattr(module, attr)))
    failed = []
    for kind in ("NORMAL", "EXCEPTION", "BOUNDARY"):
        group = [t for t in tests if t[0] == kind]
        print("\n[%s] %d건" % (KIND_LABEL[kind], len(group)))
        current = None
        for _, module, name, fn in group:
            if module != current:
                current = module
                print("  · %s" % module)
            try:
                fn()
                print("      PASS  %s" % name)
            except Exception as exc:
                failed.append((name, exc))
                print("      FAIL  %s\n              %s" % (name, exc))
    print("\n%s" % ("=" * 60))
    if failed:
        print("%d건 중 %d건 실패" % (len(tests), len(failed)))
        return 1
    print("%d건 전부 통과" % len(tests))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
