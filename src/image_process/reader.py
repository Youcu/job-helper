"""`claude -p` 로 그림을 읽는다.

## 실측으로 알아낸 것

- **`< /dev/null` 이 없으면 `claude` 가 stdin 을 3초 기다린다.** 대상마다 3초씩 버린다.
  `subprocess` 에서는 `stdin=subprocess.DEVNULL` 이 그 노릇을 한다.
- `--output-format json` 의 출력 **앞에 경고 줄이 붙을 수 있다.** 첫 `{` 부터 읽는다.
- 답은 두 겹이다. 바깥이 `claude` 의 봉투(`result` 칸에 모델이 한 말), 안이 우리가
  시킨 JSON 이다.

## 못 읽으면 **예외를 던진다**

빈 결과로 돌려주면 "그림에 내용이 없다" 로 읽혀 **멀쩡한 공고가 버려진다.** 우리가 못
읽은 것과 그림에 쓸 게 없는 것은 다른 일이고, 그 구분이 이 단계의 안전장치다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

FIELDS = ("기술스택", "자격요건", "우대사항")

# **인재상은 셋과 따로 받는다.** `FIELDS` 는 "쓸 게 있었나"(`fill.has_anything`)를
# 재는 자라서, 여기에 인재상을 더하면 인재상만 있는 그림이 내용 있는 공고로 둔갑한다.
# 인재상은 `자격요건` 칸에 별도 표기로 붙는다 (`fill.VALUES_HEADING`).
VALUES = "인재상"

# **읽은 글 자체.** 위 셋은 이미 추려 낸 결과라 부문 구조가 없다 — 여러 직군을 한
# 장에 담은 그림 공고에서 어느 부문이 무엇을 요구하는지가 거기서 사라진다
# (실측 2026-09-18: 통합 공고 후보 59건 중 12건이 그림 본문이었고, 기술 57개짜리
# `[안랩] 2026 연구소 집중 채용` 이 거기 있었다).
#
# 그래서 **자르기 전의 글**을 따로 받는다. 이것은 `csv/bodies.jsonl` 로 가고,
# 직군을 가리는 단계가 그것을 읽는다.
BODY = "본문"
# 실측: 조각 7장을 --max-turns 14 로 돌렸더니 num_turns 이 정확히 14 로 끝났다 —
# 자연 종료(stop_reason: end_turn)이긴 했지만 여유가 0 이었다. 조각마다 Read 한 번
# + 응답 한 번으로 대략 2턴을 쓴다고 보고, 마무리 답변까지 더해 여유 8 을 둔다.
TURNS_PER_SLICE = 2
EXTRA_TURNS = 8


class ReadError(RuntimeError):
    """우리가 못 읽었다. **버림 판정에 쓰면 안 된다.**"""


# 추리는 규칙. **그림을 읽을 때와 글만 다시 추릴 때가 같아야 한다** — 두 경로가
# 다른 말을 들으면 같은 공고가 어느 길로 왔느냐에 따라 다른 결과를 낸다.
#
# ## 왜 이만큼 길게 적나 — 짧게 적었더니 머리말 글자만 봤다
#
# 처음에는 한 줄이었다: "요구 조건은 자격요건에, 있으면 좋은 것은 우대사항에".
# 그랬더니 모델이 **`자격요건` 이라고 글자로 적힌 머리말 아래만** 옮겼다.
#
# 실측(2026-09-22, 위캔소프트 `GI_Read/49811179`): 본문에는
# `이런 사람을 원합니다!` 아래 네 줄이 멀쩡히 읽혀 있는데 `자격요건` 배열에는
# `전문대졸이상`·`경력 3년이상` 둘뿐이었다. 본문 있는 캐시 146건 중 **18건**에서
# 이런 식으로 245줄이 샜다.
#
# ## 그런데 넓히기만 하면 인재상과 복지가 딸려 온다
#
# 같은 실측에서 샌 245줄에는 `필수 역량`·`NICE TO HAVE` 같은 진짜 요건과 함께
# `도전(CHALLENGE): 배우고 성장하며 용감하게 도전하는 인재`, `포도의 복지는?` 도
# 있었다. 그래서 **인재상은 따로 받고 복지·회사소개는 안 받는다.**
#
# 인재상을 버리지 않는 이유는 사용자가 그것도 분석에 쓰기 때문이다 (2026-09-22).
# 다만 요건과 섞으면 무엇이 요구인지 흐려지므로 `fill` 이 별도 표기로 붙인다.
EXTRACT_RULES = (
    "- 나머지 네 칸에는 그 글에서 추린 것을 담아라.\n"
    "- **머리말 글자에 매이지 마라.** `자격요건` 이라고 적힌 대목만 보지 말고,\n"
    "  `이런 사람을 원합니다` · `이런 분을 찾습니다` · `필수 역량` · `우리가 원하는` ·\n"
    "  `NICE TO HAVE` · `기본 자격` 처럼 **말만 다르고 뜻이 같은 대목**도 담아라.\n"
    "  머리말이 아예 없이 글 안에 섞여 있어도 요구 조건이면 담아라.\n"
    "- `자격요건` — 지원하려면 **갖춰야 하는 것**. 필수 역량·학력·경력·자격증.\n"
    "- `우대사항` — 없어도 지원할 수 있는 것. `우대` · `있으면 좋은` · `NICE TO HAVE`.\n"
    "- `인재상` — 회사가 바라는 **사람됨·태도**. `도전적인 분` · `협업을 즐기는 분` ·\n"
    "  `책임감 있는 인재` 처럼 기술이나 연수가 아니라 성향을 말하는 것.\n"
    "  자격요건과 겹쳐 적지 마라 — 한 줄은 한 칸에만 넣어라.\n"
    "- **담지 마라**: 복지·급여·근무조건·전형절차·접수기간·문의처·회사소개·연혁·\n"
    "  사옥 주소·수상 실적. 지원자가 갖출 것이 아니라 회사가 주는 것이다.\n"
    "- `기술스택` 에는 기술 **이름만** 넣어라. `AI 기반 개발도구` 같은 설명은 빼라.\n"
)

EMPTY_RULE = (
    "- 아무것도 못 읽으면 본문은 빈 문자열, 네 칸은 모두 빈 배열로 두어라."
)

SHAPE = '{"본문":"","기술스택":[],"자격요건":[],"우대사항":[],"인재상":[]}'


def build_prompt(paths: list[Path]) -> str:
    listed = "\n".join(str(one) for one in paths)
    return (
        "%s\n"
        "위 그림들은 채용공고 하나를 위에서 아래로 자른 조각이다. **전부 읽어라.**\n"
        "그런 다음 아래 JSON 만 출력하고 다른 말은 하지 마라.\n"
        "%s\n"
        "- 그림에서 실제로 읽히는 것만 담아라. 추측하지 마라.\n"
        "- `본문` 에는 **읽은 글을 위에서 아래 차례 그대로** 옮겨라. 요약하지 말고,\n"
        "  모집부문·직무 이름 같은 머리말을 빠뜨리지 마라. 한 공고에 여러 자리가\n"
        "  실려 있으면 **어느 글이 어느 자리 것인지 차례로 드러나야** 한다.\n"
        "%s%s" % (listed, SHAPE, EXTRACT_RULES, EMPTY_RULE)
    )


def build_text_prompt(body: str) -> str:
    """**이미 읽어 둔 글에서 네 칸만 다시 추린다.** 그림을 안 본다.

    본문은 그림에서 읽어 낸 것이라 비싸다 — 내려받고, 조각내고, 조각마다 `Read` 를
    돌린다. 추린 칸은 그 글만 있으면 다시 만들 수 있다. 그래서 추리는 규칙을 고쳤을 때
    **본문은 지키고 이 경로로만 다시 만든다** (`cache.RULES_VERSION`).

    실측(2026-09-22): 이번 실행의 그림 공고 154건 중 **133건이 본문을 갖고 있어**
    이 경로로 처리된다. 그림을 다시 읽어야 하는 것은 21건뿐이다.
    """
    return (
        "아래는 채용공고 하나의 본문을 위에서 아래로 그대로 옮긴 글이다.\n"
        "이 글에서 추려 아래 JSON 만 출력하고 다른 말은 하지 마라.\n"
        "%s\n"
        "- `본문` 에는 **아래 글을 그대로** 옮겨 담아라. 고치거나 줄이지 마라.\n"
        "- 글에 실제로 있는 것만 담아라. 추측하지 마라.\n"
        "%s%s\n\n"
        "[본문]\n%s" % (SHAPE, EXTRACT_RULES, EMPTY_RULE, body)
    )


def build_command(paths: list[Path], model: str) -> list[str]:
    return [
        shutil.which("claude") or "claude",
        "-p", build_prompt(paths),
        "--model", model,
        "--allowedTools", "Read",
        "--output-format", "json",
        "--max-turns", str(TURNS_PER_SLICE * len(paths) + EXTRA_TURNS),
    ]


def _run(command: list[str], timeout: int) -> str:
    done = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                          stdin=subprocess.DEVNULL)
    if done.returncode != 0:
        raise ReadError("claude 가 %d 로 끝났습니다: %s"
                        % (done.returncode, (done.stderr or "")[-300:]))
    return done.stdout or ""


def _first_object(text: str) -> dict:
    # `rfind("}")` 로 끝을 짐작하면 안 된다 — 답 뒤에 딸린 말("{참고}" 같은)에 낱개
    # 중괄호가 하나만 섞여도 진짜 끝을 넘어가 통째로 깨진다. `raw_decode` 는 첫 `{`
    # 부터 값 하나만 실제로 파싱하고 그 값이 끝나는 자리에서 정확히 멈춘다.
    start = text.find("{")
    if start < 0:
        raise ReadError("JSON 을 못 찾았습니다: %r" % text[:200])
    try:
        obj, _end = json.JSONDecoder().raw_decode(text, start)
    except ValueError as error:
        raise ReadError("JSON 을 못 읽었습니다: %s" % error) from error
    return obj


def parse_output(text: str) -> dict:
    """`claude -p --output-format json` 의 출력 → 우리 네 칸 + 본문."""
    envelope = _first_object(text)
    answer = envelope.get("result")
    if not isinstance(answer, str):
        raise ReadError("답이 비었습니다: %r" % str(envelope)[:200])
    body = _first_object(answer)
    got = {name: [item for item in (body.get(name) or []) if isinstance(item, str)]
           for name in FIELDS + (VALUES,)}
    got[BODY] = str(body.get(BODY) or "")
    return got


def read(paths: list[Path], *, model: str, timeout: int, runner=None) -> dict:
    return _ask(build_command(paths, model), timeout, runner)


def text_command(body: str, model: str) -> list[str]:
    """**`--allowedTools` 를 안 준다.** 글만 보면 되므로 `Read` 가 필요 없다."""
    return [shutil.which("claude") or "claude",
            "-p", build_text_prompt(body), "--model", model,
            "--output-format", "json"]


def reread(body: str, *, model: str, timeout: int, runner=None) -> dict:
    """이미 읽어 둔 글에서 네 칸만 다시 추린다. **본문은 그대로 돌려준다.**

    모델이 본문을 줄여 오는 일이 있어서 우리가 갖고 있던 것으로 덮는다 — 본문이
    짧아지면 직군을 가리는 단계가 판단할 재료를 잃는다.
    """
    got = _ask(text_command(body, model), timeout, runner)
    got[BODY] = body
    return got


def _ask(command: list[str], timeout: int, runner=None) -> dict:
    runner = runner or _run
    try:
        raw = runner(command, timeout)
    except ReadError:
        raise
    except Exception as error:
        raise ReadError("%s: %s" % (type(error).__name__, error)) from error
    return parse_output(raw)
