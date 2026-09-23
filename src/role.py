#!/usr/bin/env python3
"""**한 공고에 여러 직군이 섞여 있으면, 내 직군 부문만 남기고 나머지는 지운다.**

    python3 src/role.py

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

    ① 기계  제목·본문의 낱말로 **후보**를 고른다   `src/role_words.py` · 8%
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

낱말 거르기(`src/filter.py`)의 `EXCLUDE_TECH_STACKS` 가 기술스택을 본다. 직군을
먼저 안 가리면 다른 부문의 `PHP`·`jQuery` 를 보고 멀쩡한 공고를 뺀다.

종료 코드
    0  정상
    1  입력이 없거나 `claude` 명령을 못 찾았거나 `JOB_ROLES` 가 비었다
    3  이미 돌고 있다
"""
from __future__ import annotations

import csv
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
INPUT = CSV / "merged_read.csv"
BODIES = CSV / "bodies.jsonl"
OUTPUT = CSV / "merged_role.csv"
REPORT = CSV / "role_report.csv"
CACHE = CACHE_DIR / "role_judge.json"
LOCK = CSV / ".role.lock"


from _common import bodies as bodies_module                        # noqa: E402
from _common import roles                                          # noqa: E402
from _common.env import ConfigError, read_env                      # noqa: E402
from _common import corpus_candidates                              # noqa: E402
from _common.skills import keep_known, split_names, unknown_names  # noqa: E402
from _common.outcome import gate_line                              # noqa: E402
from _common.runlock import guarded                                # noqa: E402
from _common.sections import VALUES_HEADING                        # noqa: E402
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
# 캐시에서 그대로 나오면 고침이 영영 안 먹는다 — `src/career.py` 에서 실제로 겪었다.
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
        "- 앞 단계가 `지원자격` 에 `%s` 머리말과 그 아래 줄들을 넣어 두었을 수 있다.\n"
        "  그것은 회사가 바라는 **사람됨**이라 부문을 안 가린다. 고른 부문의\n"
        "  자격요건 뒤에 **머리말째 그대로 옮겨라.** 부문별로 고르지도, 지우지도 마라.\n"
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
        % (described, row.get("공고명", ""), body[:MAX_PROMPT_BODY],
           VALUES_HEADING)
    )


# ── 두 번째 물음: 절을 못 갈랐을 때 ─────────────────────────────────────
#
# **첫 물음과 섞지 않는다.** 위 `build_prompt` 는 "어느 부문이 내 직군인가" 를 묻고,
# 그 답이 `해당=false` 면 행을 **뺀다.** 절을 못 가른 행에까지 그 물음을 던지면,
# 자격요건을 채우러 갔다가 **행이 사라지는** 일이 생긴다. 후보를 넓히는 대가가
# "한 번 더 묻는 것" 이어야지 "멀쩡한 공고가 지워지는 것" 이면 안 된다.
#
# 그래서 이 물음은 **뽑기만 한다.** 판정하지 않고, 이 답으로는 아무도 안 뺀다.
def build_fill_prompt(row: dict, body: str) -> str:
    """이 글에서 네 칸을 뽑아 달라. **고르지 말고 뽑기만.**"""
    return (
        "채용공고 본문이다. 우리 절 가르기가 `자격요건` 같은 머리말을 못 찾아\n"
        "지원자격 칸이 비었다. **글을 직접 읽고 채워라.**\n\n"
        "[공고명]\n%s\n\n[본문]\n%s\n\n"
        "할 일\n"
        "- **머리말 글자에 매이지 마라.** `자격요건` 이라 적혀 있지 않아도, 지원하려면\n"
        "  갖춰야 할 것이면 `지원자격` 에 담아라. `필요사항` · `이런 분을 찾습니다` ·\n"
        "  `필수 역량` 처럼 말이 다를 수 있고, 번호 목록이나 문단에 섞여 있을 수도 있다.\n"
        "- 표 형식이면 열 이름(`담당업무` `자격요건` `우대사항`)을 보고 값을 갈라라.\n"
        "- `우대사항` 은 없어도 지원할 수 있는 것이다.\n"
        "- `경력` 은 **공고가 명시한 것만** 적어라. 안 적혀 있으면 빈 문자열이다.\n"
        "  `경력무관` 같은 값을 **지어내지 마라.**\n"
        "- `기술스택` 에는 기술 **이름만** 쉼표로 나열하라.\n"
        "- **담지 마라**: 복지·급여·근무조건·전형절차·접수기간·문의처·회사소개.\n"
        "- **글에 없는 것을 지어내지 마라.** 못 찾은 칸은 빈 문자열로 둬라.\n\n"
        "아래 JSON 만 출력하고 다른 말은 하지 마라.\n"
        '{"지원자격": "", "우대사항": "", "기술스택": "쉼표로 나열", '
        '"경력": "", "근거": "한 문장"}'
        % (row.get("공고명", ""), body[:MAX_PROMPT_BODY])
    )


def fill_judge(row: dict, body: str, *, model: str = MODEL, timeout: int = TIMEOUT,
               runner=None) -> dict:
    """절을 못 가른 공고 하나에서 네 칸을 뽑는다."""
    command = [shutil.which("claude") or "claude",
               "-p", build_fill_prompt(row, body),
               "--model", model, "--output-format", "json"]
    try:
        return parse_output((runner or _call)(command, timeout))
    except JudgeError:
        raise
    except Exception as error:
        raise JudgeError("%s: %s" % (type(error).__name__, error)) from error


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


# 한 번에 띄울 `claude -p` 개수. **그림 판독과 같은 근거다** — 한 건마다 프로세스가
# 통째로 뜨므로 수십 개를 동시에 띄우면 이 기계가 먼저 힘들어진다.
#
# **왜 병렬이 필요해졌나** — 후보 고르기를 화이트리스트로 바꾸면서(2026-09-23
# 사용자) 물어볼 것이 203행 → 457행이 됐다. 직렬로 두면 첫 실행이 한 시간 가까이
# 걸린다. 둘째 실행부터는 캐시라 값이 0이지만, **첫 실행이 한 시간이면 아무도 안 돌린다.**
WORKERS = 8


def _prefetch(rows: list[dict], texts: dict, book: dict, cache_path: Path,
              wanted: list[str], *, ask=None, fill_ask=None) -> None:
    """**판정만 미리 병렬로 받아 캐시에 채운다.** 뒤의 본 루프는 캐시에서 읽는다.

    루프를 통째로 병렬로 만들지 않는 이유는, 그 루프가 `kept`·`cut` 에 **차례대로**
    쌓아 결과 CSV 의 행 순서를 정하기 때문이다. 순서가 흔들리면 같은 입력이 매번
    다른 파일을 낸다 — 되짚기가 어려워진다.

    **못 물어본 것은 조용히 지나간다.** 본 루프가 캐시에 없는 것을 다시 물어보고
    거기서 실패를 제대로 처리한다(`JudgeError` → 남김 + 보고). 여기서 삼키면 그
    처리가 두 군데로 갈린다.
    """
    lock = threading.Lock()
    jobs = []
    for row in rows:
        url = row.get("URL") or ""
        body = texts.get(url, "")
        if not body:
            continue
        remembered = book.get(url)
        fresh = remembered is not None and remembered.get("규칙판") == RULES_VERSION
        unclear = role_words.title_unclear(row)
        if (role_words.looks_mixed(row, body) or unclear) and not fresh:
            jobs.append(("부문", url, row, body))
        key = "절:" + url
        held = book.get(key)
        if (role_words.needs_sections(row, body, VALUES_HEADING)
                and not (held is not None and held.get("규칙판") == RULES_VERSION)):
            jobs.append(("절", key, row, body))
    if not jobs:
        return

    print("  미리 물어봅니다: %d건 (동시 %d개)" % (len(jobs), WORKERS))

    def one(job):
        kind, key, row, body = job
        if kind == "부문":
            answer = (ask or judge)(row, body, wanted)
            return key, {"답": answer, "신호": [], "규칙판": RULES_VERSION,
                         "판정일": date.today().isoformat()}
        answer = (fill_ask or fill_judge)(row, body)
        return key, {"답": answer, "규칙판": RULES_VERSION,
                     "판정일": date.today().isoformat()}

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(one, job) for job in jobs]
        done = 0
        for future in as_completed(futures):
            try:
                key, value = future.result()
            except Exception:
                continue                  # 본 루프가 다시 물어보고 제대로 처리한다
            with lock:
                book[key] = value
                save_cache(cache_path, book)
                done += 1
                if done % 50 == 0:
                    print("    %d/%d" % (done, len(jobs)))


def _fill_sections(row: dict, body: str, url: str, book: dict, cache_path: Path,
                   *, ask=None) -> tuple[dict, tuple[str, str]]:
    """절을 못 가른 행을 모델에게 읽혀 채운다. (채운 행, (판정, 근거)).

    **못 물어봐도 행은 그대로 돌려준다.** 채우려다 실패한 것이 행을 없앨 이유는 없다.

    캐시는 `looks_mixed` 쪽과 **열쇠를 나눈다** — 같은 URL 에 물음이 둘이라
    한 자루에 담으면 나중 답이 앞 답을 덮는다.
    """
    key = "절:" + url
    remembered = book.get(key)
    if remembered is not None and remembered.get("규칙판") == RULES_VERSION:
        answer = remembered.get("답") or {}
    else:
        try:
            answer = (ask or fill_judge)(row, body)
        except JudgeError as error:
            return row, ("남김 · 절 복구 실패", str(error)[:200])
        book[key] = {"답": answer, "규칙판": RULES_VERSION,
                     "판정일": date.today().isoformat()}
        save_cache(cache_path, book)

    got = {c: str(answer.get(c) or "").strip() for c in OVERWRITE}
    if not got.get("지원자격"):
        # **빈 답을 채움으로 세지 않는다.** 모델도 못 찾았다는 뜻이고, 그건
        # 글에 조건이 없다는 말일 수 있다. 지어내는 것보다 비는 편이 낫다.
        return row, ("남김 · 절 복구 · 못 찾음", str(answer.get("근거") or "")[:200])
    return apply(row, answer), ("남김 · 절 복구", str(answer.get("근거") or "")[:200])


def clean_techs(value: str, *, url: str = "") -> str:
    """모델이 낸 기술 이름 줄을 **corpus 로 거른다.**

    **이 단계는 기술 이름이 들어오는 다섯 번째 길이다.** 앞의 넷(수집·태그 /
    수집·산문 / 그림 판독 / 후보 해석)은 걸러지는데 여기만 안 걸러졌다 —
    모델이 낸 글을 그대로 칸에 썼다.

    처음에는 차단 목록(`blocked`)만 지나게 했다. **그걸로는 안 된다** —
    모델은 본문에 있는 말을 잘라 오는데, 본문에는 기술 이름이 아닌 말이
    얼마든지 있다. 실측으로 `AI 기반 개발도구` · `OpenAI API 등 LLM API` ·
    `데이터베이스 쿼리` · `OGC 표준` 이 그렇게 들어왔고, 그런 말은 **무한하다.**
    하나 볼 때마다 목록에 한 줄 더하는 것은 끝이 없다 (2026-09-18 사용자).

    그래서 **아는 이름만 통과시킨다** (`skills.keep_known`). 산문 경로가 진작부터
    그러고 있다. 모르는 이름은 버리되 `corpus_candidates` 에 쌓아 사람이 보게 한다.
    """
    pieces = split_names(value)
    unknown = unknown_names(pieces)
    if unknown:
        corpus_candidates.record(unknown, site="role", source_url=url)
    return ", ".join(keep_known(pieces))


def apply(row: dict, answer: dict) -> dict:
    """모델이 뽑아 준 것으로 네 칸을 덮어쓴다. **빈 칸은 안 덮는다.**

    모델이 한 칸을 못 채웠다고 원래 있던 내용을 지우면, 통합 공고가 아니었을 때
    멀쩡한 칸이 빈다. 못 채운 것은 **모르는 것**이지 *없는 것*이 아니다.

    `기술스택` 은 `clean_techs` 를 지난다 — 여기가 기술 이름이 들어오는 다섯 번째
    길이라 차단을 지나야 한다.

    **인재상은 코드가 되붙인다.** 프롬프트에도 지키라고 적었지만 실측으로 안 지켜졌다
    (2026-09-22, 274행 중 10행에서 표기가 사라졌다). 그중 둘은 내용까지 잃었고
    나머지는 머리말만 없이 요건에 섞였다 — 그러면 무엇이 요구인지 다시 흐려진다.
    """
    out = dict(row)
    for column in OVERWRITE:
        value = str(answer.get(column) or "").strip()
        if column == TECH_COLUMN:
            value = clean_techs(value, url=row.get("URL", ""))
        if value:
            out[column] = trim(value)
    out["지원자격"] = _keep_values(row.get("지원자격"), out.get("지원자격"))
    return out


def _keep_values(before: str | None, after: str | None) -> str:
    """덮어쓰기 전에 있던 인재상 대목을 **그대로 되돌려 놓는다.**

    **부문을 안 가리므로 코드로 옮겨도 맞다.** 인재상은 회사가 바라는 사람됨이라
    부문마다 다르지 않다 — 그래서 애초에 별도 표기로 떼어 둔 것이고, 그래서 모델의
    부문 고르기를 거칠 이유가 없다.

    모델이 머리말 없이 요건에 섞어 놓았을 수 있다. 그때도 **머리말째 다시 붙인다** —
    같은 줄이 두 번 보이는 것이 무엇이 요구인지 모르는 것보다 낫다.
    """
    before, after = before or "", after or ""
    if VALUES_HEADING not in before or VALUES_HEADING in after:
        return after
    block = VALUES_HEADING + before.split(VALUES_HEADING, 1)[1].rstrip()
    return (after.rstrip() + "\n" + block) if after.strip() else block


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
         ask=None, fill_ask=None, have_claude: bool | None = None,
         assume_yes: bool = False) -> int:
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
    filled = filled_failed = 0
    kept, cut = [], []

    print("찾는 직군: %s" % " · ".join(wanted))
    print(gate_line(len(rows),
                    sum(1 for row in rows
                        if role_words.looks_mixed(row, texts.get(row.get("URL") or "", ""))
                        or role_words.title_unclear(row)),
                    "직군을 물어볼 공고"))
    _prefetch(rows, texts, book, cache_path, wanted, ask=ask, fill_ask=fill_ask)

    for row in rows:
        url = row.get("URL") or ""
        body = texts.get(url, "")
        # **두 갈래가 같은 물음으로 온다.**
        #   looks_mixed    여러 직군을 한 장에 담았나  → 내 직군 부문을 고른다
        #   looks_foreign  제목이 다른 직군을 말하나    → 내 직군이 맞는지 본다
        #
        # 물음이 같아서(`build_prompt`) 프롬프트를 나눌 이유가 없다 — 그 프롬프트는
        # "부문이 하나뿐인데 내 직군이 아니면 `해당=false`" 를 이미 말한다.
        #
        # **이 갈래는 뺄 수 있다.** 절 복구(`needs_sections`)와 다른 점이다 —
        # 저기는 자격요건을 채우러 가는 길이라 빼면 안 되고, 여기는 애초에 "내 자리가
        # 맞나" 를 묻는 길이라 아니면 빼는 것이 맞다.
        unclear = role_words.title_unclear(row)
        signals = role_words.looks_mixed(row, body) + ([unclear] if unclear else [])
        if not signals:
            # **두 번째 게이트.** 통합 공고는 아닌데 절을 못 가른 행이 있다 —
            # 회사가 `자격요건` 이라는 말을 안 쓴 것이다. 규칙이 못 가르면 이상한
            # 경우로 보고 모델이 직접 읽는다 (2026-09-22 사용자).
            why = role_words.needs_sections(row, body, VALUES_HEADING)
            if why:
                row, note = _fill_sections(
                    row, body, url, book, cache_path, ask=fill_ask)
                cut.append((row, note[0], [why], "", "", note[1]))
                if note[0].startswith("남김 · 절 복구 실패"):
                    filled_failed += 1
                elif note[0].startswith("남김 · 절 복구"):
                    filled += 1
            kept.append(row)                      # **이 물음으로는 아무도 안 뺀다**
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
           source, output, report, filled, filled_failed)
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
           report: Path, filled: int = 0, filled_failed: int = 0) -> None:
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
    # **채운 것을 찍는다.** 안 찍으면 이 게이트가 도는지 사람이 알 수 없고,
    # 빈 칸이 조용히 채워지는 것과 조용히 안 채워지는 것이 같아 보인다.
    if filled:
        print("  절을 못 갈라 모델이 직접 읽은 공고: %d건 — 지원자격을 채웠습니다" % filled)
    if filled_failed:
        print("  그중 못 물어본 공고: %d건 — 빈 채로 남겼습니다" % filled_failed)
    print("%s — %d행 (%s %d행에서 %d행 뺌)"
          % (output, len(kept), source, total, len(dropped)))
    print("%s — %d행 (뺀 이유와 못 판정한 것 전량)" % (report, len(cut)))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
