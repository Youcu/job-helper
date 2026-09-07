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
# 실측: 조각 7장을 --max-turns 14 로 돌렸더니 num_turns 이 정확히 14 로 끝났다 —
# 자연 종료(stop_reason: end_turn)이긴 했지만 여유가 0 이었다. 조각마다 Read 한 번
# + 응답 한 번으로 대략 2턴을 쓴다고 보고, 마무리 답변까지 더해 여유 8 을 둔다.
TURNS_PER_SLICE = 2
EXTRA_TURNS = 8


class ReadError(RuntimeError):
    """우리가 못 읽었다. **버림 판정에 쓰면 안 된다.**"""


def build_prompt(paths: list[Path]) -> str:
    listed = "\n".join(str(one) for one in paths)
    return (
        "%s\n"
        "위 그림들은 채용공고 하나를 위에서 아래로 자른 조각이다. **전부 읽어라.**\n"
        "그런 다음 아래 JSON 만 출력하고 다른 말은 하지 마라.\n"
        '{"기술스택":[],"자격요건":[],"우대사항":[]}\n'
        "- 그림에서 실제로 읽히는 것만 담아라. 추측하지 마라.\n"
        "- 기술 이름은 기술스택에, 요구 조건은 자격요건에, 있으면 좋은 것은 우대사항에 담아라.\n"
        "- 아무것도 못 읽으면 세 칸을 모두 빈 배열로 두어라." % listed
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
    """`claude -p --output-format json` 의 출력 → 우리 세 칸."""
    envelope = _first_object(text)
    answer = envelope.get("result")
    if not isinstance(answer, str):
        raise ReadError("답이 비었습니다: %r" % str(envelope)[:200])
    body = _first_object(answer)
    return {name: [item for item in (body.get(name) or []) if isinstance(item, str)]
            for name in FIELDS}


def read(paths: list[Path], *, model: str, timeout: int, runner=None) -> dict:
    runner = runner or _run
    try:
        raw = runner(build_command(paths, model), timeout)
    except ReadError:
        raise
    except Exception as error:
        raise ReadError("%s: %s" % (type(error).__name__, error)) from error
    return parse_output(raw)
