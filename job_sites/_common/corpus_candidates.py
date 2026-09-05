"""표준 이름으로 못 푼 기술 이름을 **사람이 볼 수 있게** 쌓아 둔다.

## 왜 자동으로 코퍼스에 넣지 않는가

`tech_corpus.json` 은 사이트 공통 표준이고, 거기 있는 이름은 `build_matcher()` 를 통해
**모든 사이트의 산문 매칭 어휘가 된다.** 잘못 읽은 이름 하나가 자동으로 들어가면

1. 다른 사이트 본문에서도 매칭되기 시작하고
2. 매칭돼서 CSV 에 나오니 멀쩡해 보이고 (**자기 강화**)
3. 누적 CSV 에 퍼진 뒤에는 되돌리기 어렵다

그래서 **사람이 승인해야 들어간다.** 이건 이 저장소가 이미 정한 방향과 같다 —
숨김 판정에서 *놓치면 틀린 데이터가 들어오고 과하면 데이터가 없어진다, 없어지는 편이 낫다*
로 정했고, 편집거리 매칭을 버린 것도 같은 이유였다 (`REST`→`Rust`, `MSSQL`→`MySQL`).

## 그러면 놓친 것은 어떻게 아는가

**버려진 이름은 CSV 에 흔적이 안 남는다.** 이 파일이 없으면 아무도 모르게 사라진다.
그래서 이건 편의 기능이 아니라 **누락을 복구 가능하게 만드는 장치**다.

    record(["VxWorks", "ARM"], site="saramin", source_url="https://.../54459386")
    → job_sites/_common/corpus_candidates.json 에 근거와 함께 쌓인다

사람은 그 파일을 훑고 `tech_corpus.json`(새 기술) 이나 `tech_aliases.json`(표기 차이) 로
옮긴다. 옮기고 나면 `canonical()` 이 풀어 주므로 다음 실행부터는 후보로 안 올라온다.

`_similar` 는 **비슷한 표준 이름**을 같이 보여 준다. 자동으로 붙이지 않는다 —
`REST`/`Rust` 처럼 닮았지만 다른 기술을 사람 눈에 걸리게 하려는 것이다.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from difflib import get_close_matches
from pathlib import Path

from . import dictionaries
from .normalize import canonical

CANDIDATES_FILE = Path(__file__).resolve().parent / "corpus_candidates.json"

# 한 후보에 예시 URL 을 몇 개까지 남길지. 판단에는 두엇이면 충분하고,
# 더 쌓으면 사람이 읽어야 할 양만 늘어난다.
MAX_EXAMPLES = 3

# 비슷한 표준 이름을 몇 개까지 보여 줄지, 그리고 얼마나 닮아야 보여 줄지.
MAX_SIMILAR = 3
SIMILARITY_CUTOFF = 0.75


def record(names: list[str], *, site: str, source_url: str = "",
           path: Path | None = None) -> list[str]:
    """표준 이름으로 못 푸는 것만 골라 후보 파일에 쌓는다. 쌓은 이름을 돌려준다.

    이미 코퍼스에 있는 이름은 조용히 버린다 — 후보가 아니다.
    """
    target = path or CANDIDATES_FILE
    unresolved = [name for name in dict.fromkeys(names) if is_unresolved(name)]
    if not unresolved:
        return []

    book = _load(target)
    today = date.today().isoformat()
    for name in unresolved:
        entry = book.setdefault(name, {
            "관측": 0, "사이트": [], "예시": [], "비슷한_표준이름": _similar(name),
            "처음본날": today,
        })
        entry["관측"] += 1
        entry["마지막본날"] = today
        if site and site not in entry["사이트"]:
            entry["사이트"].append(site)
        if source_url and source_url not in entry["예시"]:
            entry["예시"] = (entry["예시"] + [source_url])[:MAX_EXAMPLES]
    _save(target, book)
    return unresolved


def is_unresolved(name: str) -> bool:
    """후보로 올려야 하는 이름인가.

    이미 표준 이름으로 풀리거나, **기술스택이 아니라고 사람이 이미 판단한** 이름은
    후보가 아니다. 기각한 것이 매 실행 다시 올라오면 진짜 후보가 그 속에 묻힌다.
    """
    # `canonical()` 을 거쳐야 한다 — `"   "` 는 참인 문자열이라 `not name` 으로는 안 걸린다.
    if not canonical(name) or is_rejected(name):
        return False
    return not _standard_names(name)


def is_rejected(name: str) -> bool:
    """기술스택이 아니라고 판단해 둔 이름인가 (`tech_rejected.txt`)."""
    return (name or "").strip().lower() in dictionaries.rejected()


def resolved(names: list[str]) -> list[str]:
    """표준 이름으로 풀리는 것만, 순서를 지켜 표준 표기로."""
    kept: dict[str, None] = {}
    for name in names:
        if is_rejected(name):
            continue
        for standard in _standard_names(name):
            kept.setdefault(standard, None)
    return list(kept)


def _standard_names(name: str) -> list[str]:
    """이름 하나가 가리키는 표준 이름들. 못 풀면 빈 목록.

    보통 하나지만, 모델이 `C/C++` `Java-Spring` 처럼 **붙여서** 뱉는 일이 있어 쪼갠다.
    쪼개기 전에 **통째로 먼저 시도한다** — `HTML/CSS` `React-Native` 는 그 자체가 표준
    이름이거나 별칭이다. 그리고 **조각이 전부 풀릴 때만** 쪼갠 것을 받는다.
    `Node-RED` 는 `Node` 만 풀리고 `RED` 가 안 풀리므로 쪼개지지 않는다.
    """
    whole = canonical(name)
    if whole and whole.lower() in dictionaries.corpus():
        return [whole]
    for separator in ("/", "-"):
        if separator not in (name or ""):
            continue
        parts = [canonical(part) for part in name.split(separator)]
        if len(parts) > 1 and all(p and p.lower() in dictionaries.corpus() for p in parts):
            return list(dict.fromkeys(parts))
    return []


def _similar(name: str) -> list[str]:
    """닮은 표준 이름. **제안이 아니라 경고다** — 오인할 만한 것을 눈에 띄게 한다."""
    return get_close_matches(name, dictionaries.corpus_names(),
                             n=MAX_SIMILAR, cutoff=SIMILARITY_CUTOFF)


def _load(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # 후보 파일이 깨졌다고 수집이 멈추면 안 된다. 다시 쌓으면 되는 종류의 자료다.
        return {}
    return data.get("후보", {}) if isinstance(data, dict) else {}


def _save(path: Path, book: dict[str, dict]) -> None:
    payload = {
        "_설명": ("표준 이름으로 못 푼 기술 이름. **사람이 보고 옮긴다.** "
                "새 기술이면 tech_corpus.json 에, 표기 차이면 tech_aliases.json 에. "
                "옮기면 다음 실행부터 여기 안 올라온다."),
        "_주의": "비슷한_표준이름 은 제안이 아니라 경고다. REST/Rust 처럼 닮았지만 다른 기술이 있다.",
        "후보": dict(sorted(book.items(), key=lambda kv: (-kv[1]["관측"], kv[0].lower()))),
    }
    _write_atomically(path, json.dumps(payload, ensure_ascii=False, indent=1))


def _write_atomically(path: Path, text: str) -> None:
    """같은 디렉터리에 임시로 쓰고 이름을 바꾼다 — 중간에 끊겨도 반쪽 파일이 안 남는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
