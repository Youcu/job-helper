#!/usr/bin/env python3
"""**낱말이 걸렸다고 다 결격은 아니다.** 뉘앙스를 모델이 판정한다.

    python3 src/nuance.py

    csv/merged_filtered.csv  ──▶  csv/merged_nuance.csv    남은 공고
                             +    csv/nuance_report.csv    판정 전량

## 왜 필요한가 — 같은 낱말이 정반대를 뜻한다

거르기(`src/filter.py`)는 낱말이 있으면 뺐다. 그런데 실측(2026-09-22)으로 같은 낱말이
정반대 뜻으로 쓰인다.

    단순 **SI**가 아닌 자사 플랫폼 중심으로 …          ← SI 를 **부정**한다
    2,000개 이상의 **고객사**를 유치했으며 …           ← 자사 플랫폼의 고객 수 자랑
    **고객사** 상위 시스템(MES·ERP) 연동 API 구현      ← 자사 제품의 연동 대상
    ※ 산업기능요원 **보충역** … 지원 가능합니다        ← 요구가 아니라 혜택 안내

    시스템통합(**SI/SM**) 담당업무 · SI/SM 관련 업무    ← 진짜 SI 업체
    **SI** 프로젝트 웹/업무시스템 개발 및 유지보수      ← 진짜
    GIS, Digital Twin, XR 기반의 **SI** 및 통합 솔루션  ← 회사소개에서 자기가 SI 라 한다
    근무형태: **고객사** 상주                          ← 진짜 상주다
    **[병역특례]** Android Developer (산업기능요원)     ← 병역특례 전용 공고

**낱말만 보고는 이것을 가를 수 없다.** 규칙을 아무리 더해도 다음 형태에서 또 뚫린다.
그래서 **좁히는 일은 코드가, 판정은 모델이** 한다 — `src/career.py` 와 같은 모양이다.

## 본문까지 본다

거르기는 `공고명`·`지원자격`·`우대사항` 셋만 본다. 회사소개는 안 본다 — 회사 이름과
지역명이 낱말을 품어 근거 없이 자르게 되기 때문이다. 그래서 **회사소개에서 자기가
SI 기업이라고 말해도 안 걸렸다** (실측: 최종 46행 중 11행이 본문에 금칙어를 가졌다).

여기서는 `csv/bodies.jsonl` 의 본문까지 넣어 본다. 오탐이 늘지만 **자르는 것은
모델이므로** 오탐이 곧 삭제가 아니다. 낱말은 후보를 좁히는 데까지만 쓴다.

## 애매하면 **남긴다**

지우는 판단에 "모르겠으면 지운다" 는 없다 (2026-09-13 사용자). 놓친 공고는 사람이
목록에서 보고 넘기면 그만이지만, **지워진 공고는 있었다는 사실조차 안 남는다.**

종료 코드
    0  정상
    1  입력이 없거나 `claude` 명령을 못 찾음
    3  이미 돌고 있다
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR / "job_sites"))
sys.path.insert(0, str(SRC_DIR))

from paths import CACHE as CACHE_DIR, CSV, HISTORY as HISTORY_DIR  # noqa: E402
from paths import ROOT, SITES                                      # noqa: E402
SITES_DIR = SITES
INPUT = CSV / "merged_filtered.csv"
BODIES = CSV / "bodies.jsonl"
OUTPUT = CSV / "merged_nuance.csv"
REPORT = CSV / "nuance_report.csv"
CACHE = CACHE_DIR / "nuance_judge.json"
LOCK = CSV / ".nuance.lock"


from _common import bodies as bodies_module                        # noqa: E402
from _common.outcome import gate_line                              # noqa: E402
from _common.runlock import guarded                                # noqa: E402
from _common.staleness import confirm, yes_given                   # noqa: E402
from _common.store import read_csv, write_csv, write_rows          # noqa: E402

import filter_words                                                # noqa: E402


def company_of(row: dict) -> str:
    """판정을 나눠 쓸 단위. **법인 표기를 지운 회사 이름**이다.

    `filter_words.company_key` 를 그대로 쓴다 — 중복 묶기가 같은 회사인지 가릴 때
    쓰는 자와 같아야 한다. 두 자가 갈리면 "중복은 아닌데 같은 회사" 같은 어중간한
    상태가 생긴다.
    """
    return filter_words.company_key(row.get("기업명"))

REPORT_COLUMNS = ("기업명", "공고명", "사이트명", "URL", "판정", "빠진이유",
                  "걸린낱말", "어디서", "근거")

MODEL = "sonnet"
TIMEOUT = 120

# **판정 규칙이 바뀌면 옛 판정을 버린다.** 프롬프트를 고쳐도 이미 판정된 공고가
# 캐시에서 그대로 나오면 고침이 영영 안 먹는다 — `src/career.py` 에서 실제로 겪었다.
RULES_VERSION = 3

# 본문을 이만큼까지만 프롬프트에 싣는다. 회사소개·복지·전형절차가 다 들어 있어
# 길다 — 실측 평균 2,100자 · 최대 11,358자.
MAX_BODY = 4000

# 걸린 낱말 앞뒤로 이만큼을 보고에 적는다.
CONTEXT = 40


class JudgeError(RuntimeError):
    """우리가 못 물어봤다. **뺌 판정에 쓰면 안 된다.**"""


def hits_of(row: dict, body: str = "") -> list[tuple[str, str, str]]:
    """이 공고에서 걸린 (낱말, 어디서, 근처 글). 없으면 빈 목록.

    **두 군데를 따로 센다.** 칸에서 걸린 것과 본문에서만 걸린 것은 무게가 다르다 —
    자격요건에 적힌 `SI` 는 그 자리의 조건이고, 회사소개의 `SI` 는 회사의 업이다.
    모델에게 그 구분을 넘겨 주려면 어디서 걸렸는지가 답에 실려야 한다.
    """
    found: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    columns = filter_words.text_of(row)
    for name, pattern in filter_words.BANNED:
        match = pattern.search(columns)
        if match:
            found.append((name, "공고 칸", _around(columns, match)))
            seen.add(name)
    for name, pattern in filter_words.BANNED:
        if name in seen or not body:
            continue
        match = pattern.search(body)
        if match:
            found.append((name, "본문", _around(body, match)))
    return found


def _around(text: str, match) -> str:
    start = max(0, match.start() - CONTEXT)
    end = min(len(text), match.end() + CONTEXT)
    return " ".join(text[start:end].split())


def build_prompt(row: dict, hits: list[tuple[str, str, str]], body: str) -> str:
    """모델에게 물을 말.

    **판정 기준을 못 박는다.** 안 적으면 낱말이 있다는 이유만으로 결격이라 답한다.
    """
    listed = "\n".join("- `%s` (%s) … %s …" % (name, where, near)
                       for name, where, near in hits)
    return (
        "채용공고 하나를 본다. 나는 **신입 백엔드·웹 개발자**로 지원할 자리를 찾고 있고,\n"
        "아래 종류의 자리는 **피하고 싶다.**\n"
        "- SI/SM 을 업으로 하는 회사, 또는 그런 일을 하게 되는 자리\n"
        "- 고객사에 상주하거나 파견되는 자리\n"
        "- 병역특례(산업기능요원·전문연구요원·보충역) **전용** 공고\n\n"
        "이 공고에서 그 낱말들이 이렇게 걸렸다:\n%s\n\n"
        "[공고명]\n%s\n\n[지원자격]\n%s\n\n[우대사항]\n%s\n\n[본문]\n%s\n\n"
        "**세 가지를 따로 답하라.**\n"
        "  `회사가SI` — 이 **회사**가 SI/SM 을 업으로 하는가. 회사소개·사업영역·\n"
        "               담당업무가 고객 시스템의 구축·운영 대행이면 true 다.\n"
        "  `자리가상주` — 이 **자리**가 고객사·제휴사에 상주하거나 파견되는가.\n"
        "               근무지·근무형태에 그렇게 적혀 있으면 true 다.\n"
        "  `병역특례전용` — 이 **자리**가 병역특례 대상자만 뽑는가. 제목이나 지원자격에\n"
        "               `[병역특례]`·`[전문연구요원]` 을 달았거나 `…자격 보유자만 지원\n"
        "               가능` 처럼 못 박았으면 true 다.\n"
        "셋 중 하나라도 true 면 피할 자리다.\n\n"
        "**왜 갈라 묻는가** — 회사 판단은 그 회사의 모든 공고에 같아야 하고, 자리\n"
        "판단은 공고마다 다르다. 한 답에 섞으면 같은 회사의 두 공고가 다르게 갈린다 —\n"
        "실측으로 클릭비·풀링포레스트·마드라스체크가 그렇게 갈렸다.\n\n"
        "판정 기준\n"
        "- 회사가 **회사소개에서 스스로 SI/SM 기업이라고 말하면** 피할 자리다.\n"
        "  `GIS 기반의 SI 및 통합 솔루션 서비스를 제공하는 IT기업` 이 그렇다.\n"
        "- 담당업무가 **SI 프로젝트 구축·유지보수**이거나 **고객사 상주**면 피할 자리다.\n"
        "- **낱말이 있다는 것만으로는 아니다.** 다음은 피할 자리가 **아니다**:\n"
        "  · `단순 SI가 **아닌** 자사 플랫폼 중심` 처럼 **부정하는** 문장\n"
        "  · `2,000개 이상의 **고객사**를 유치` 처럼 자사 제품·플랫폼의 **고객 수**\n"
        "  · `**고객사** 상위 시스템과 연동` 처럼 자사 제품이 **연동하는 대상**\n"
        "  · 헤드헌팅 회사가 아니라 **일반 기업의 평범한 고객 언급**\n"
        "- 병역특례는 **전용 공고만** 피한다. `※ 산업기능요원 보충역 지원 가능합니다`\n"
        "  처럼 **일반 지원자도 그대로 지원할 수 있으면 피할 자리가 아니다** —\n"
        "  그것은 요구가 아니라 **혜택 안내**다 (2026-09-22 사용자).\n"
        "  반대로 `전문연구요원 자격 보유자만 지원 가능` · `해당하지 않는 경우 서류\n"
        "  전형에서 불합격` · 제목의 `[병역특례 현역/보충역]` 은 **전용 공고**다.\n"
        "- **자사 제품을 만들어 파는 회사는 SI 업체가 아니다.** 그 제품을 고객 환경에\n"
        "  설치·운영하는 자리라도 회사는 제품회사다 — 여러 고객의 **서로 다른** 시스템을\n"
        "  만들어 주는 것이 SI 이고, **하나의 자사 제품**을 배포하는 것은 아니다\n"
        "  (2026-09-22 사용자, 마드라스체크 `플로우`).\n"
        "- **애매하면 false 를 내라.** 놓치는 것보다 멀쩡한 공고를 지우는 쪽이 나쁘다.\n"
        "  다만 **고객 시스템의 구축·유지보수·기술지원이 그 회사의 업이면 애매하지\n"
        "  않다** — `고객사 시스템 구축`·`고객사 장애 지원`·`고객 대상 인프라 구축·운영`\n"
        "  은 말만 다른 SI/SM 이다 (2026-09-22 사용자).\n\n"
        "아래 JSON 만 출력하고 다른 말은 하지 마라. 따옴표 안에 큰따옴표를 쓰지 마라.\n"
        '{"회사가SI": true/false, "자리가상주": true/false, '
        '"병역특례전용": true/false, "근거": "한 문장"}'
        % (listed, row.get("공고명", ""), (row.get("지원자격") or "")[:800],
           (row.get("우대사항") or "")[:500], (body or "")[:MAX_BODY])
    )


def _call(command: list[str], timeout: int) -> str:
    done = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                          stdin=subprocess.DEVNULL)
    if done.returncode != 0:
        raise JudgeError("claude 가 %d 로 끝났습니다: %s"
                         % (done.returncode, (done.stderr or "")[-300:]))
    return done.stdout or ""


def _first_object(text: str) -> dict:
    start = text.find("{")
    if start < 0:
        raise JudgeError("JSON 을 못 찾았습니다: %r" % text[:200])
    try:
        obj, _end = json.JSONDecoder().raw_decode(text, start)
    except ValueError as error:
        raise JudgeError("JSON 을 못 읽었습니다: %s" % error) from error
    return obj


def parse_output(text: str) -> tuple[bool, bool, bool, str]:
    """`claude -p …` 의 출력 → (회사가 SI, 자리가 상주, 병역특례 전용, 근거)."""
    answer = _first_object(text).get("result")
    if not isinstance(answer, str):
        raise JudgeError("답이 비었습니다: %r" % text[:200])
    body = _first_object(answer)
    return (bool(body.get("회사가SI")), bool(body.get("자리가상주")),
            bool(body.get("병역특례전용")), str(body.get("근거") or "")[:200])


def judge(row: dict, hits: list, body: str, *, model: str = MODEL,
          timeout: int = TIMEOUT, runner=None) -> tuple[bool, bool, bool, str]:
    """**한 번만 다시 묻는다.**

    실측(2026-09-22)으로 154건 중 1건이 JSON 이 깨져 판정을 못 받았다 —
    `(주)넥스비원` 의 `ERP SAP B1 운영/유지보수 담당자`. 근거 문장 안에 큰따옴표가
    섞여 들어간 것이라 **같은 물음을 다시 던지면 대개 통과한다.**

    못 물어본 것은 남기므로(`_run`) 실패해도 공고가 사라지지는 않는다. 다만 그러면
    **SI 업체가 목록에 남는다** — 여기 넥스비원이 딱 그 모양이다(ERP 운영·유지보수).
    그래서 한 번 더 두드린다.

    두 번째도 실패하면 실패로 둔다. 계속 매달리면 뒤엣것이 밀린다.
    """
    command = [shutil.which("claude") or "claude",
               "-p", build_prompt(row, hits, body),
               "--model", model, "--output-format", "json"]
    last = None
    for _attempt in range(2):
        try:
            return parse_output((runner or _call)(command, timeout))
        except JudgeError as error:
            last = error
        except Exception as error:
            last = JudgeError("%s: %s" % (type(error).__name__, error))
    raise last


def load_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def save_cache(path: Path, book: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".%s.tmp%d" % (path.name, os.getpid()))
    try:
        tmp.write_text(json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    assume_yes = yes_given(argv)
    return guarded(LOCK, lambda: _run(assume_yes=assume_yes))


def _run(source: Path | None = None, bodies_path: Path | None = None,
         output: Path | None = None, report: Path | None = None,
         cache_path: Path | None = None, *, ask=None,
         have_claude: bool | None = None, assume_yes: bool = False) -> int:
    """바깥과 닿는 것을 전부 인자로 받는다 — 안 넘기면 진짜를 쓴다."""
    source = source if source is not None else INPUT
    bodies_path = bodies_path if bodies_path is not None else BODIES
    output = output if output is not None else OUTPUT
    report = report if report is not None else REPORT
    cache_path = cache_path if cache_path is not None else CACHE

    if not source.exists():
        print("%s 가 없습니다. 먼저 거르기까지 돌리세요." % source, file=sys.stderr)
        print("  python3 job_crawling_ochestrator.py", file=sys.stderr)
        return 1
    if not confirm(source, assume_yes=assume_yes):
        print("멈췄습니다 — 아무것도 안 바꿨습니다.", file=sys.stderr)
        return 1
    if not (shutil.which("claude") if have_claude is None else have_claude):
        print("claude 명령을 못 찾았습니다. 이 단계는 그것으로 판정합니다.", file=sys.stderr)
        print("  거르지 않고 통과시키면 **걸렀다고 믿는데 안 걸린 파일**을 받습니다.",
              file=sys.stderr)
        return 1

    rows = read_csv(source)
    texts = bodies_module.load(bodies_path)
    print(gate_line(len(rows),
                    sum(1 for row in rows
                        if hits_of(row, texts.get(row.get("URL") or "", ""))),
                    "낱말이 걸린 공고"))
    book = load_cache(cache_path)
    asked = failed = 0

    # ── 1번 지나기: 묻는다 ────────────────────────────────────────────
    verdicts: dict[str, dict] = {}
    for row in rows:
        url = row.get("URL") or ""
        body = texts.get(url, "")
        hits = hits_of(row, body)
        if not hits:
            continue                              # 후보가 아니다

        remembered = book.get(url)
        if remembered is not None and remembered.get("규칙판") == RULES_VERSION:
            got = (bool(remembered.get("회사가SI")), bool(remembered.get("자리가상주")),
                   bool(remembered.get("병역특례전용")), remembered.get("근거", ""))
        else:
            try:
                got = (ask or judge)(row, hits, body)
            except JudgeError as error:
                # **못 물어본 것을 결격으로 읽으면 안 된다.**
                failed += 1
                print("  %s 판정 실패: %s" % (url, error), file=sys.stderr)
                verdicts[url] = {"hits": hits, "실패": str(error)[:200]}
                continue
            asked += 1
            book[url] = {"회사가SI": got[0], "자리가상주": got[1],
                         "병역특례전용": got[2], "근거": got[3],
                         "규칙판": RULES_VERSION, "판정일": date.today().isoformat()}
            save_cache(cache_path, book)
        verdicts[url] = {"hits": hits, "회사": got[0], "자리": got[1],
                         "병역": got[2], "근거": got[3]}

    # ── 2번 지나기: **회사 판단을 그 회사의 모든 공고에 퍼뜨린다** ────────
    #
    # 회사가 SI 업체인가는 **공고마다 달라질 수 없다.** 그런데 사이트마다 본문에
    # 실린 글이 달라서 한쪽은 회사소개를 갖고 한쪽은 안 갖는다. 그러면 같은 회사가
    # 갈린다 — 실측(2026-09-22)으로 클릭비·풀링포레스트·마드라스체크가 그랬다.
    #
    #     (주)클릭비 프론트엔드 개발자 채용 (자사/SI)  → 결격 아님
    #     (주)클릭비 프론트엔드 개발자 채용            → 피할 자리   ← 거꾸로다
    #
    # **한 곳이라도 SI 업체라고 판정되면 그 회사 전체에 적용한다.** 자리 판단
    # (상주·파견)은 공고마다 다르므로 안 퍼뜨린다.
    si_firms = {company_of(row) for row in rows
                if verdicts.get(row.get("URL") or "", {}).get("회사")}

    kept, lines = [], []
    spread = 0
    for row in rows:
        url = row.get("URL") or ""
        seen = verdicts.get(url)
        if seen is None:
            kept.append(row)                      # 후보가 아니었다
            continue
        if "실패" in seen:
            lines.append(_line(row, seen["hits"], "남김 · 판정 실패", "", seen["실패"]))
            kept.append(row)
            continue

        firm = company_of(row) in si_firms
        if firm and not seen["회사"]:
            spread += 1                           # 형제 공고의 판단을 물려받았다
        if firm or seen["자리"] or seen["병역"]:
            # **병역특례 전용은 회사 단위가 아니다.** 같은 회사가 전용 공고와 일반
            # 공고를 함께 내는 일이 흔하다 — 실측으로 파이오링크·메디인테크가 그랬다.
            reason = " · ".join(part for part, on in (
                ("SI/SM 업체", firm), ("상주·파견", seen["자리"]),
                ("병역특례 전용", seen["병역"])) if on)
            if firm and not seen["회사"]:
                reason += " (같은 회사의 다른 공고에서 판정)"
            lines.append(_line(row, seen["hits"], "제외 · 피할 자리",
                               reason, seen["근거"]))
        else:
            kept.append(row)
            # **남긴 것도 전량 적는다.** 낱말이 걸렸는데 남겼다는 것은 사람이
            # 되짚어야 할 판단이다 — 안 적으면 왜 남았는지 알 수 없다.
            lines.append(_line(row, seen["hits"], "남김 · 결격 아님", "", seen["근거"]))

    write_csv(output, kept)
    write_rows(report, REPORT_COLUMNS, lines)
    _print(len(rows), asked, failed, kept, lines, source, output, report, spread)
    return 0


def _line(row: dict, hits: list, verdict: str, reason: str, why: str) -> dict:
    """`빠진이유` 는 **걸린 낱말과 다를 수 있다.**

    낱말은 후보를 좁히는 자일 뿐이고, 판정은 글 전체를 본다. 실측으로 버즈빌이
    `전문연구요원` 으로 걸렸는데 빠진 이유는 `제휴사 오피스로 출근` 이었다.
    두 칸을 갈라 적어야 사람이 그 차이를 본다.
    """
    return {"기업명": row.get("기업명", ""), "공고명": row.get("공고명", ""),
            "사이트명": row.get("사이트명", ""), "URL": row.get("URL", ""),
            "판정": verdict, "빠진이유": reason,
            "걸린낱말": ", ".join(sorted({name for name, _, _ in hits})),
            "어디서": " / ".join(sorted({where for _, where, _ in hits})),
            "근거": why or " / ".join("%s «%s»" % (n, near) for n, _, near in hits)[:300]}


def _print(before: int, asked: int, failed: int, kept: list, lines: list,
           source: Path, output: Path, report: Path, spread: int = 0) -> None:
    cut = [one for one in lines if one["판정"].startswith("제외")]
    held = [one for one in lines if one["판정"].startswith("남김 · 결격 아님")]
    print("\n물어본 공고 %d건 (캐시에서 바로 나온 것은 안 셉니다)" % asked)
    if failed:
        print("  판정 실패 %d건 — **남겼습니다.** 못 물어본 것을 결격으로 읽으면 안 됩니다."
              % failed)
    print("  낱말이 걸린 공고 %d건 중" % len(lines))
    print("    피할 자리로 판정 : %d건" % len(cut))
    print("    결격 아님        : %d건  ← 낱말만 봤으면 잘렸을 공고다" % len(held))
    if spread:
        print("  같은 회사의 다른 공고 판단을 물려받아 뺌 : %d건" % spread)
    print("\n%s — %d행 (%s %d행에서 %d행 뺌)"
          % (_shown(output), len(kept), _shown(source), before, len(cut)))
    print("%s — %d행 (판정 전량)" % (_shown(report), len(lines)))


def _shown(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
