"""`claude -p` 를 부르고 출력에서 JSON 을 꺼낸다.

실측으로 알아낸 것 둘 —
- **`< /dev/null` 이 없으면 `claude` 가 stdin 을 3초 기다린다.** 대상마다 3초씩 버린다.
- `--output-format json` 의 출력 **앞에 경고 줄이 붙을 수 있다.** 첫 `{` 부터 읽어야 한다.
"""
from __future__ import annotations

import json
from pathlib import Path

from image_process import reader

from .helpers import check, check_equal

ANSWER = {"기술스택": ["Java", "Spring"], "자격요건": ["3년 이상"], "우대사항": []}


def _envelope(result_text: str) -> str:
    return json.dumps({"type": "result", "result": result_text,
                       "duration_ms": 1000, "total_cost_usd": 0.1}, ensure_ascii=False)


def test_NORMAL_parses_a_plain_answer():
    got = reader.parse_output(_envelope(json.dumps(ANSWER, ensure_ascii=False)))
    check_equal(got, ANSWER, "그대로 읽혀야 한다")


def test_NORMAL_command_carries_model_and_read_tool():
    command = reader.build_command([Path("/tmp/a_000.png")], "opus")
    check("claude" in command[0], "claude 를 부른다: %r" % command)
    check("--model" in command and "opus" in command, "모델을 넘긴다: %r" % command)
    check("--output-format" in command and "json" in command, "json 으로 받는다")
    check("Read" in " ".join(command), "Read 도구를 허용해야 그림을 연다")


def test_NORMAL_max_turns_scales_with_slice_count_and_has_headroom():
    # 실측: 조각 7장을 --max-turns 14 로 돌렸더니 num_turns 이 딱 14 로 끝났다.
    # 여유가 없으면 살짝만 수다스러워도 답이 안 나온다. 조각당 2턴 + 여유 8.
    paths = [Path("/tmp/a_%03d.png" % i) for i in range(7)]
    command = reader.build_command(paths, "opus")
    index = command.index("--max-turns")
    check_equal(int(command[index + 1]), 2 * len(paths) + 8, "여유를 둔 턴 예산")


def test_NORMAL_prompt_names_every_slice():
    paths = [Path("/tmp/a_000.png"), Path("/tmp/a_001.png"), Path("/tmp/a_002.png")]
    prompt = reader.build_prompt(paths)
    for one in paths:
        check(str(one) in prompt, "%s 가 프롬프트에 없다" % one)
    check("전부" in prompt or "모두" in prompt, "다 읽으라고 시켜야 한다")


def test_EXCEPTION_warning_line_before_json_is_skipped():
    # 실제로 이렇게 나온다. 첫 `{` 부터 읽지 않으면 통째로 실패한다.
    raw = "Warning: no stdin data received in 3s, proceeding without it.\n" \
          + _envelope(json.dumps(ANSWER, ensure_ascii=False))
    check_equal(reader.parse_output(raw), ANSWER, "경고 줄을 넘겨야 한다")


def test_EXCEPTION_chatter_around_the_answer_is_tolerated():
    raw = _envelope("네, 읽었습니다.\n" + json.dumps(ANSWER, ensure_ascii=False) + "\n이상입니다.")
    check_equal(reader.parse_output(raw), ANSWER, "앞뒤에 말이 붙어도 꺼내야 한다")


def test_EXCEPTION_stray_brace_in_trailing_chatter_is_tolerated():
    # `rfind("}")` 로 끝을 짐작하면 이 뒤에 붙은 `}` 까지 통째로 잘라내 JSON 이
    # 깨진다. `raw_decode` 로 실제 값의 끝에서 멈춰야 한다.
    raw = _envelope(json.dumps(ANSWER, ensure_ascii=False) + "\n참고로 이건 여담입니다 {참고}")
    check_equal(reader.parse_output(raw), ANSWER, "뒤에 붙은 낱개 중괄호에 속으면 안 된다")


def test_EXCEPTION_unparseable_output_raises_not_returns_empty():
    # **여기가 제일 중요하다.** 빈 결과로 돌려주면 "그림에 내용이 없다" 로 읽혀
    # 멀쩡한 공고가 버려진다. 우리가 못 읽은 것은 예외로 알려야 한다.
    for raw in ("", "그냥 말만 했다", _envelope("JSON 이 아닙니다")):
        error = None
        try:
            reader.parse_output(raw)
        except reader.ReadError as caught:
            error = caught
        check(error is not None, "못 읽으면 예외여야 한다: %r" % raw)


def test_BOUNDARY_missing_fields_are_filled_with_empty_lists():
    got = reader.parse_output(_envelope('{"기술스택":["Java"]}'))
    check_equal(got["기술스택"], ["Java"], "있는 것")
    check_equal(got["자격요건"], [], "없는 칸은 빈 목록")
    check_equal(got["우대사항"], [], "없는 칸은 빈 목록")


def test_BOUNDARY_all_empty_is_a_valid_answer_not_an_error():
    # "셋 다 비었다" 는 **결과다.** 예외로 만들면 버림 판정을 못 한다.
    got = reader.parse_output(_envelope('{"기술스택":[],"자격요건":[],"우대사항":[]}'))
    check_equal(got, {"기술스택": [], "자격요건": [], "우대사항": []}, "빈 결과도 답이다")


def test_BOUNDARY_non_string_items_are_dropped():
    got = reader.parse_output(_envelope('{"기술스택":["Java",null,3,"Go"]}'))
    check_equal(got["기술스택"], ["Java", "Go"], "글이 아닌 것은 버린다")


def test_BOUNDARY_read_uses_the_injected_runner():
    seen = {}
    paths = [Path("/tmp/a_000.png")]

    def fake(command, timeout):
        seen["command"] = command
        seen["timeout"] = timeout
        return _envelope(json.dumps(ANSWER, ensure_ascii=False))

    got = reader.read(paths, model="sonnet", timeout=42, runner=fake)
    check_equal(got, ANSWER, "결과")
    check_equal(seen["timeout"], 42, "시간제한을 넘겨야 한다")
    check_equal(seen["command"], reader.build_command(paths, "sonnet"), "명령도 검증해야 한다")
