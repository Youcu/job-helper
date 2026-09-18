#!/usr/bin/env python3
"""**한 공고에 여러 직군이 섞여 있으면, 내 직군 부문만 남기고 나머지는 지운다.**

    python3 role.py

    csv/merged_read.csv  →  csv/merged_role.csv    남은 공고 (내 직군 내용으로 덮어씀)
    csv/bodies.jsonl     ↗   csv/role_report.csv   **뺀 공고 전량 + 뺀 이유**

## 무엇이 문제였나

회사가 여러 자리를 한 공고에 담는다. 그러면 **우리는 그것을 한 덩어리로 다룬다.**

    [NARA SPACE] 각 부문별 직원모집   (rec_idx=50846359, 실측 2026-09-18)

    기술스택    전 부문의 합집합 53개
                프론트 6(React·Redux·CSS) · 임베디드 11(Verilog·FPGA·I2C·CAN)
                · 백엔드 5 · 인프라 7 · 그 밖 24
    지원자격    **PM 부문 것만** — "기술 개발 프로젝트 전 주기 관리 경험",
                "MS Office Excel 활용", "영어 회화(B1,B2)"

절로 자를 때 **첫 부문 것만** 남기 때문이다. 그래서 뒤 단계가 다 어긋난다 —
핵심 기술 게이트는 다른 부문의 `FastAPI` 를 보고 통과시키고, 경력 판정은 PM
부문의 요건을 읽고 판정하고, 낱말 거르기는 다른 부문의 `PHP` 를 보고 뺀다
(실측 8건이 그렇게 억울하게 빠졌다).

## 두 겹으로 가른다

    ① 기계  제목·본문의 낱말로 **후보**를 고른다   `role_words.py` · 8%
    ② 모델  후보만 `claude` 에게 내 직군 부문을 뽑게 한다

회사가 공고를 어떻게 쓸지 모르므로 ②는 기계로 못 한다 (사용자 판단). 그렇다고
전부 모델에 태우면 느리고 비싸다. ①이 92%를 걸러 준다.

## 무엇으로 덮어쓰나

`.env` 의 `JOB_ROLES` 다. **`백엔드` 라고 코드에 박지 않는다** — 박으면 `.env` 를
바꿔도 코드가 안 따라온다 (사용자 지적). 이름·별칭·설명은 `_common/roles.py` 가
갖고 있고, 그 설명을 프롬프트에 그대로 넣어 모델이 무엇을 고를지 알게 한다.

덮어쓰는 칸은 넷이다 — `기술스택` · `지원자격` · `우대사항` · `경력`.
나머지(기업명·URL·근무지·마감일…)는 공고 전체의 것이라 그대로 둔다.

## 내 직군이 없으면 뺀다

`JOB_ROLES` 에 해당하는 부문이 하나도 없으면 그 공고는 나와 상관없다. 리포트에
이유와 함께 남긴다.

## 본문이 없으면 **조용히 넘기지 않는다**

후보인데 본문이 없으면 판정할 재료가 없다. 그때 칸으로 대신하면 **이미 잘려 나간
첫 부문 것**으로 판정하게 되고, 걸렀다고 믿는데 안 걸린 결과가 나온다. 그래서
남기되 **리포트에 "본문 없음" 으로 적는다** — 드러나야 고칠 수 있다.

## 자리 — 거르기 **앞**이다

낱말 거르기(`filter.py`)의 `EXCLUDE_TECH_STACKS` 가 기술스택을 본다. 직군을
먼저 안 가리면 다른 부문의 `PHP`·`jQuery` 를 보고 멀쩡한 공고를 뺀다.

종료 코드
    0  정상
    1  입력이 없거나 `claude` 명령을 못 찾았거나 `JOB_ROLES` 가 비었다
    3  이미 돌고 있다
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SITES_DIR = ROOT_DIR / "job_sites"
INPUT = ROOT_DIR / "csv" / "merged_read.csv"
BODIES = ROOT_DIR / "csv" / "bodies.jsonl"
OUTPUT = ROOT_DIR / "csv" / "merged_role.csv"
REPORT = ROOT_DIR / "csv" / "role_report.csv"
CACHE = ROOT_DIR / "cache" / "role_judge.json"
LOCK = ROOT_DIR / "csv" / ".role.lock"

sys.path.insert(0, str(SITES_DIR))
sys.path.insert(0, str(ROOT_DIR))

from _common import bodies as bodies_module                        # noqa: E402
from _common import roles                                          # noqa: E402
from _common.env import ConfigError, read_env                      # noqa: E402
from _common.normalize import canonical                            # noqa: E402
from _common.skills import blocked                                 # noqa: E402
from _common.runlock import guarded                                # noqa: E402
from _common.staleness import confirm, yes_given                   # noqa: E402
from _common.store import read_csv, trim, write_csv, write_rows    # noqa: E402

import role_words                                                  # noqa: E402

REPORT_COLUMNS = ("기업명", "공고명", "사이트명", "URL", "판정", "걸린신호",
                  "찾은부문", "부문원문", "근거")

MODEL = "sonnet"
TIMEOUT = 180

# 모델에게 넘길 본문 길이. 실측 최대가 18,924자라 넉넉하다.
MAX_PROMPT_BODY = 20_000

# **판정 규칙이 바뀌면 옛 판정을 버린다.** 프롬프트를 고쳐도 이미 판정된 공고가
# 캐시에서 그대로 나오면 고침이 영영 안 먹는다 — `career.py` 에서 실제로 겪었다.
# 규칙(프롬프트)이나 `JOB_ROLES`, 그리고 **`roles.json` 의 설명**을 손대면 이 숫자를
# 올려라. 설명은 프롬프트에 그대로 실리므로 그것이 바뀌면 판정 기준이 바뀐 것이다 —
# 실제로 `웹` 의 뜻을 넓혔더니(백엔드·프론트엔드·풀스택) 옛 판정이 어긋났다.
RULES_VERSION = 4

# 덮어쓰는 칸. 나머지는 공고 전체의 것이라 그대로 둔다.
OVERWRITE = ("기술스택", "지원자격", "우대사항", "경력")
TECH_COLUMN = "기술스택"


class JudgeError(RuntimeError):
    """우리가 못 물어봤다. **뺌 판정에 쓰면 안 된다.**"""


def build_prompt(row: dict, body: str, wanted: list[str]) -> str:
    """모델에게 물을 말.

    **내 직군이 무엇인지 설명까지 넣는다.** 이름만 주면 `웹` 을 프론트로도 읽는다 —
    `_common/roles.json` 이 갖고 있는 설명이 그 자리를 메운다.
    """
    described = "\n".join("- **%s** : %s" % (name, roles.describe(name) or "")
                          for name in wanted)
    return (
        "채용공고 하나를 본다. 이 공고는 **여러 직군을 한 장에 담았을** 가능성이 있다.\n"
        "회사가 부문을 나눈 방식은 공고마다 다르다 — 표·목록·문단 무엇이든 될 수 있다.\n\n"
        "내가 찾는 직군은 이것뿐이다:\n%s\n\n"
        "[공고명]\n%s\n\n"
        "[공고 본문]\n%s\n\n"
        "할 일\n"
        "1. 이 공고에 **여러 부문(모집 직무)** 이 있는지 본다.\n"
        "2. 내가 찾는 직군에 **해당하는 부문만** 고른다. 여럿이면 다 고른다.\n"
        "3. 고른 부문의 것만 모아 낸다.\n\n"
        "**가장 중요한 규칙 — 네 칸은 모두 \"같은 부문 블록\" 에서 나와야 한다.**\n"
        "공고는 부문마다 제 자격요건·우대사항·기술·경력을 따로 적는다. 한 칸이라도\n"
        "다른 부문 블록에서 가져오면, 읽는 사람은 그것을 내 직군의 조건으로 믿는다.\n"
        "- 프론트엔드 부문의 React 나 임베디드 부문의 Verilog 가 들어가면 안 된다.\n"
        "- **고른 부문 블록에 그 칸이 없으면 빈 문자열로 둬라.** 옆 부문에서\n"
        "  가져오지 마라. 비는 것이 틀린 것보다 낫다.\n"
        "- `경력` 은 **그 부문이 명시한 것만** 적어라 (`신입`·`경력 3년 이상`).\n"
        "  안 적혀 있으면 빈 문자열이다. `경력무관` 같은 값을 **지어내지 마라.**\n"
        "- 고른 부문의 머리말을 `부문원문` 에 **공고에 적힌 그대로** 옮겨라.\n"
        "  사람이 네 답을 확인할 자리다.\n"
        "- **머리말만 있고 그 부문의 내용이 본문에 없을 수 있다.** 채용 사이트가\n"
        "  포지션 목록만 싣고 상세는 링크 너머에 두기 때문이다. 그때 옆 부문의\n"
        "  글을 끌어다 쓰면 안 된다 — `내용확실=false` 로 하고 네 칸을 비워라.\n"
        "  고른 부문의 일이라고 **읽어서 납득이 되면** `내용확실=true` 다.\n\n"
        "판정 기준\n"
        "- 부문이 **하나뿐**이고 그것이 내 직군이면 `해당=true` 로 하고, 칸은\n"
        "  공고에 적힌 그대로 낸다.\n"
        "- 부문이 하나뿐인데 내 직군이 **아니면** `해당=false` 다.\n"
        "- 내 직군 부문이 **하나도 없으면** `해당=false` 다.\n"
        "- **애매하면 `해당=true` 로 두고 내용을 그대로 내라.** 놓치는 것보다\n"
        "  멀쩡한 공고를 지우는 쪽이 나쁘다.\n\n"
        "아래 JSON 만 출력하고 다른 말은 하지 마라. 모르는 칸은 빈 문자열로 둬라.\n"
        '{"해당": true 또는 false, "내용확실": true 또는 false, '
        '"부문": "고른 부문 이름들", "부문원문": "공고에 적힌 머리말 그대로", '
        '"기술스택": "쉼표로 나열", "지원자격": "", "우대사항": "", '
        '"경력": "", "근거": "한 문장"}'
        % (described, row.get("공고명", ""), body[:MAX_PROMPT_BODY])
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


def parse_output(text: str) -> dict:
    """`claude -p --output-format json` 의 출력 → 우리가 시킨 JSON.

    답은 두 겹이다 — 바깥이 `claude` 의 봉투, 안이 우리가 시킨 JSON.
    """
    answer = _first_object(text).get("result")
    if not isinstance(answer, str):
        raise JudgeError("답이 비었습니다: %r" % text[:200])
    return _first_object(answer)


def judge(row: dict, body: str, wanted: list[str], *, model: str = MODEL,
          timeout: int = TIMEOUT, runner=None) -> dict:
    """한 공고에서 내 직군 부문을 뽑는다. 못 물어보면 `JudgeError`."""
    command = [shutil.which("claude") or "claude",
               "-p", build_prompt(row, body, wanted),
               "--model", model, "--output-format", "json"]
    try:
        return parse_output((runner or _call)(command, timeout))
    except JudgeError:
        raise
    except Exception as error:
        raise JudgeError("%s: %s" % (type(error).__name__, error)) from error


# 기술 이름 하나로 받아들일 최대 길이. 모델이 `KAFKA / [공용서비스 개발 및 운영] Java`
# 처럼 절 머리말을 끼워 넣은 것을 걸러 낸다 (2026-09-18 실측). 가장 긴 진짜 이름은
# `Naver Cloud Platform`(20자) 쯤이라 넉넉하다.
MAX_TECH_NAME = 30


def clean_techs(value: str) -> str:
    """모델이 낸 기술 이름 줄을 **수집기와 같은 규칙으로** 다듬는다.

    **이 단계는 기술 이름이 들어오는 다섯 번째 길이다.** 앞의 넷(수집·태그 /
    수집·산문 / 그림 판독 / 후보 해석)은 차단을 지나는데 여기만 안 지났다 —
    모델이 낸 글을 그대로 칸에 썼다. 그래서 `풀스택`·`DevOps`·`컨테이너`·`ORM`
    이 최종본에 되돌아왔다 (2026-09-18 실측: 48행에 26가지·47번).

    셋을 한다.
    - 쉼표로 가르고 표준 표기로 모은다 (`canonical`)
    - 차단 목록을 지난다 (`blocked` — 애초에 기술스택이 아닌 이름)
    - **말이 섞여 든 조각을 버린다.** 모델이 절 머리말을 끼워 넣는 일이 있다.
    """
    kept: list[str] = []
    seen: set[str] = set()
    for piece in str(value or "").split(","):
        name = canonical(piece.strip())
        if not name or len(name) > MAX_TECH_NAME:
            continue
        if "[" in name or "]" in name or "/" in name and " " in name:
            continue                      # 절 머리말이 섞였다
        if blocked(name):
            continue
        low = name.lower()
        if low not in seen:
            seen.add(low)
            kept.append(name)
    return ", ".join(kept)


def apply(row: dict, answer: dict) -> dict:
    """모델이 뽑아 준 것으로 네 칸을 덮어쓴다. **빈 칸은 안 덮는다.**

    모델이 한 칸을 못 채웠다고 원래 있던 내용을 지우면, 통합 공고가 아니었을 때
    멀쩡한 칸이 빈다. 못 채운 것은 **모르는 것**이지 *없는 것*이 아니다.

    `기술스택` 은 `clean_techs` 를 지난다 — 여기가 기술 이름이 들어오는 다섯 번째
    길이라 차단을 지나야 한다.
    """
    out = dict(row)
    for column in OVERWRITE:
        value = str(answer.get(column) or "").strip()
        if column == TECH_COLUMN:
            value = clean_techs(value)
        if value:
            out[column] = trim(value)
    return out


# ── 캐시 ────────────────────────────────────────────────────────────────
#
# **같은 공고를 두 번 물으면 답이 달라질 수 있다.** 재현성이 걸려 있으므로 URL 로
# 캐시한다. 그림 판독·평점·경력이 이미 같은 방식이다.

def load_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}            # 깨져 있으면 버리고 새로 묻는다


def save_cache(path: Path, book: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".%s.tmp%d" % (path.name, os.getpid()))
    try:
        tmp.write_text(json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def wanted_roles(env_path: Path | None = None) -> list[str]:
    """`.env` 의 `JOB_ROLES`. 수집기가 쓰는 것과 **같은 값**이다."""
    env = read_env(env_path) if env_path is not None else read_env()
    raw = [piece.strip() for piece in str(env.get("JOB_ROLES") or "").split(",")
           if piece.strip()]
    if not raw:
        raise ConfigError(
            "JOB_ROLES 가 비어 있습니다. 이 단계는 그것으로 부문을 고릅니다.\n"
            "  예: JOB_ROLES=백엔드,웹")
    return roles.normalize(raw)


def main(argv: list[str] | None = None) -> int:
    assume_yes = yes_given(argv)
    return guarded(LOCK, lambda: _run(assume_yes=assume_yes))


def _run(source: Path | None = None, bodies_path: Path | None = None,
         output: Path | None = None, report: Path | None = None,
         cache_path: Path | None = None, env_path: Path | None = None, *,
         ask=None, have_claude: bool | None = None, assume_yes: bool = False) -> int:
    """바깥과 닿는 것을 전부 인자로 받는다 — 안 넘기면 진짜를 쓴다."""
    source = source if source is not None else INPUT
    bodies_path = bodies_path if bodies_path is not None else BODIES
    output = output if output is not None else OUTPUT
    report = report if report is not None else REPORT
    cache_path = cache_path if cache_path is not None else CACHE

    if not source.exists():
        print("%s 가 없습니다. 먼저 그림 판독까지 돌리세요." % source, file=sys.stderr)
        print("  python3 job_crawling_ochestrator.py", file=sys.stderr)
        return 1
    if not confirm(source, assume_yes=assume_yes):
        print("멈췄습니다 — 아무것도 안 바꿨습니다.", file=sys.stderr)
        return 1
    try:
        wanted = wanted_roles(env_path)
    except ConfigError as error:
        print(str(error), file=sys.stderr)
        return 1
    if not (shutil.which("claude") if have_claude is None else have_claude):
        print("claude 명령을 못 찾았습니다. 이 단계는 그것으로 부문을 고릅니다.",
              file=sys.stderr)
        print("  거르지 않고 통과시키면 **걸렀다고 믿는데 안 걸린 파일**을 받습니다.",
              file=sys.stderr)
        return 1

    rows = read_csv(source)
    texts = bodies_module.load(bodies_path)
    book = load_cache(cache_path)
    asked = failed = bodyless = unsure = 0
    kept, cut = [], []

    print("찾는 직군: %s" % " · ".join(wanted))

    for row in rows:
        url = row.get("URL") or ""
        body = texts.get(url, "")
        signals = role_words.looks_mixed(row, body)
        if not signals:
            kept.append(row)                      # 후보가 아니다
            continue
        if not body:
            # **조용히 칸으로 대신하지 않는다.** 칸은 첫 부문 것이라 판정에 못 쓴다.
            bodyless += 1
            cut.append((row, "남김 · 본문 없음", signals, "", "",
                        "후보인데 본문이 없어 못 물어봤습니다. 남깁니다."))
            kept.append(row)
            continue

        remembered = book.get(url)
        if remembered is not None and remembered.get("규칙판") == RULES_VERSION:
            answer = remembered.get("답") or {}
        else:
            try:
                answer = (ask or judge)(row, body, wanted)
            except JudgeError as error:
                # **못 물어본 것을 "내 직군 아님" 으로 읽으면 안 된다.** 남긴다.
                failed += 1
                print("  %s 판정 실패: %s" % (url, error), file=sys.stderr)
                cut.append((row, "남김 · 판정 실패", signals, "", "", str(error)[:200]))
                kept.append(row)
                continue
            asked += 1
            book[url] = {"답": answer, "신호": signals, "규칙판": RULES_VERSION,
                         "판정일": date.today().isoformat()}
            save_cache(cache_path, book)          # 하나 끝날 때마다 — 중간에 죽어도 이어받는다

        found = str(answer.get("부문") or "").strip()
        quoted = str(answer.get("부문원문") or "").strip()[:200]
        why = str(answer.get("근거") or "")[:200]
        if not answer.get("해당"):
            cut.append((row, "제외 · 내 직군 없음", signals, found, quoted, why))
        elif answer.get("내용확실") is False:
            # **머리말만 있고 내용이 없다.** 사이트가 포지션 목록만 싣고 상세는
            # 링크 너머에 둔 것이다 (실측 rec_idx=55013189 — `NestJS` 가 본문 전체에서
            # 머리말 한 곳에만 나온다). 옆 부문 글로 덮어쓰면 **품질보증 요건이
            # 백엔드 요건으로 둔갑한다.** 덮지 말고 드러낸다.
            unsure += 1
            kept.append(row)
            cut.append((row, "남김 · 부문 내용 없음", signals, found, quoted, why))
        else:
            kept.append(apply(row, answer))
            # **고른 것도 전량 남긴다.** 덮어쓰는 단계라 오판이 조용하다 — 무엇을
            # 어느 부문 것으로 갈아 끼웠는지 못 되짚으면 고칠 수가 없다.
            cut.append((row, "남김 · 부문 골라 덮어씀", signals, found, quoted, why))

    write_csv(output, kept)
    _write_report(report, cut)
    _print(len(rows), asked, failed, bodyless, unsure, kept, cut, wanted,
           source, output, report)
    return 0


def _write_report(path: Path, cut: list) -> None:
    """**뺀 것과 남겼지만 못 판정한 것을 전량 남긴다.**

    모델이 판정하는 단계라 오판이 반드시 있다. 무엇을 잃었는지 되짚을 수 있어야 한다.
    """
    write_rows(path, REPORT_COLUMNS, [
        {"기업명": row.get("기업명", ""), "공고명": row.get("공고명", ""),
         "사이트명": row.get("사이트명", ""), "URL": row.get("URL", ""),
         "판정": verdict, "걸린신호": " / ".join(signals),
         "찾은부문": found, "부문원문": quoted, "근거": why}
        for row, verdict, signals, found, quoted, why in cut])


def _print(total: int, asked: int, failed: int, bodyless: int, unsure: int,
           kept: list, cut: list, wanted: list, source: Path, output: Path,
           report: Path) -> None:
    dropped = [one for one in cut if one[1].startswith("제외")]
    print("\n물어본 공고 %d건 (캐시에서 바로 나온 것은 안 셉니다)" % asked)
    if failed:
        print("  판정 실패로 남긴 공고: %d건" % failed)
    if bodyless:
        print("  본문이 없어 못 물어본 공고: %d건 — 남겼습니다. %s 를 보세요"
              % (bodyless, report.name))
    if unsure:
        print("  부문은 찾았는데 본문에 그 내용이 없는 공고: %d건 — 안 덮고 남겼습니다"
              % unsure)
    print("%s — %d행 (%s %d행에서 %d행 뺌)"
          % (output, len(kept), source, total, len(dropped)))
    print("%s — %d행 (뺀 이유와 못 판정한 것 전량)" % (report, len(cut)))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
