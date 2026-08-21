"""The stream-json parser. No claude process is spawned: the fixture IS the
capture, and the first real log replaces it verbatim."""
import json
from pathlib import Path

from pipeline.core.config import harness
from pipeline.stream import MAX_BUF, MAX_TEXT, StreamReader, parse

FIXTURE = Path(__file__).parent / "fixtures" / "stream-planning.ndjson"


def events():
    r = StreamReader()
    return r.feed(FIXTURE.read_bytes())


def test_stream_fixture_parses_and_never_raises():
    evs = events()
    assert [e["kind"] for e in evs] == [
        "other",          # the `$ cmd` header every log starts with
        "init",
        "assistant",      # thinking + text
        "assistant",      # tool_use
        "hook_started",
        "hook_response",  # the guard biting, exit 2
        "tool_result",
        "rate_limit",
        "other",          # a type this parser has never heard of
        "assistant",
        "other",          # truncated JSON mid-line
        "result",
    ], [e["kind"] for e in evs]

    init = evs[1]
    assert init["session"].startswith("6f1c0a2e") and init["model"] == "claude-sonnet-4-6"
    assert init["permission_mode"] == "plan" and "Bash" in init["tools"]
    assert init["messaging_socket_path"].endswith(".sock")
    assert init["capabilities"] == {"messaging": True}

    say = evs[2]
    assert say["text"] == "Reading the file the reproduction points at."
    assert "read it before planning" in say["thinking"]
    assert say["tools"] == [] and say["usage"]["output_tokens"] == 88

    use = evs[3]["tools"]
    assert use == [{"name": "Bash", "id": "toolu_01",
                    "input": {"command": "cat .project/pipeline.toml",
                              "description": "read project config"}}]

    # the one thing in this ticket worth demoing: the guard, watchable live
    hook = evs[5]
    assert hook["exit_code"] == 2 and "guard" in hook["stderr"]
    assert hook["hook"] == "PreToolUse" and hook["outcome"] == "block"
    assert evs[4]["hook"] == "PreToolUse" and evs[4]["tool"] == "Bash"

    tr = evs[6]
    assert tr["tool_use_id"] == "toolu_01" and tr["is_error"] is True
    assert "read-only stage" in tr["text"]

    assert evs[7]["status"] == "warning" and evs[7]["remaining_fraction"] == 0.12
    assert evs[8]["raw_type"] == "stream_event_from_a_newer_harness"

    res = evs[11]
    assert isinstance(res["total_cost_usd"], float) and res["total_cost_usd"] == 0.3412
    assert res["num_turns"] == 7 and res["duration_ms"] == 184203
    assert res["subtype"] == "success" and res["is_error"] is False
    assert res["stop_reason"] == "end_turn" and res["permission_denials"]
    assert res["usage"]["input_tokens"] == 22110 and res["modelUsage"]


def test_malformed_never_raises():
    """A harness upgrade must not kill the supervisor and strand every lease."""
    hostile = [
        "", "   ", "not json at all", '{"type":"result"', "[]", "null", '"a string"',
        "42", '{"type":"assistant"}', '{"type":"assistant","message":"not a dict"}',
        '{"type":"assistant","message":{"content":"not a list"}}',
        '{"type":"assistant","message":{"content":[null,7,{"type":"text"}]}}',
        '{"type":"user","message":{"content":[{"type":"tool_result"}]}}',
        '{"type":"user"}', '{"type":"system","subtype":"init"}',
        '{"type":"system","subtype":"hook_response"}',
        '{"type":"result","total_cost_usd":"free"}',
        '{"type":"rate_limit_event","kind":"spoofed"}',
        '{"no":"type"}', "\x00\xff binary",
    ]
    for line in hostile:
        ev = parse(line)
        assert isinstance(ev, dict) and isinstance(ev.get("kind"), str), line
    # a payload key named `kind` must not hijack the normalised kind
    assert parse('{"type":"rate_limit_event","kind":"spoofed"}')["kind"] == "rate_limit"
    # a cost that is not a number degrades the field, not the event
    assert parse('{"type":"result","total_cost_usd":"free"}')["total_cost_usd"] == 0.0


def test_tool_result_truncates():
    big = json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t", "content": "x" * (1 << 20)}]}})
    assert len(parse(big)["text"]) <= MAX_TEXT


def test_reader_splits_partial_lines():
    r = StreamReader()
    assert r.feed(b'{"type":"system","subtype":"ini') == []
    evs = r.feed(b't","session_id":"s"}\n{"type":"result"}\n')
    assert [e["kind"] for e in evs] == ["init", "result"]


def test_reader_caps_the_buffer():
    """Unbounded memory from untrusted subprocess output is a real boundary."""
    r = StreamReader()
    evs = r.feed(b"x" * (MAX_BUF + 1))          # one line, no newline, ever
    assert [e["kind"] for e in evs] == ["other"] and "exceeded" in evs[0]["error"]
    assert r.feed(b'{"type":"result"}\n') == []  # stopped parsing this child
    assert r.buf == b""                          # and dropped what it held


def test_harness_asks_for_stream_json():
    cmd = harness("claude-code")["cmd"]
    assert "--output-format stream-json" in cmd and "--verbose" in cmd
    # deliberately omitted -- see the comment in the TOML before re-adding
    assert "--input-format" not in cmd and "--include-partial-messages" not in cmd


def test_render_is_total_and_shows_the_guard_biting():
    from pipeline.cli.main import render
    lines = [render(e) for e in events()]
    assert all(isinstance(x, str) for x in lines)
    assert "exit=2" in lines[5] and "guard:" in lines[5], lines[5]
    assert lines[11].startswith("== success $0.3412 7 turns 184.2s")


def test_an_unnamed_event_is_named_and_a_shell_line_is_not_marked_unparseable():
    """`??` means "I could not parse this", and three different things wore it.

    A dispatcher stage (`verifying`, `merging`) logs plain shell output, so a
    whole merge read as `?? Merge made by the 'ort' strategy.` -- unparseable
    marked on something there was nothing to parse in. `system/thinking_tokens`
    is a per-turn token counter: 45 of one implementing stage's 189 events.
    And an event with a name and a payload printed as a bare `?? system`.
    """
    from pipeline.cli.main import render
    from pipeline.stream.events import parse

    assert render(parse("Merge made by the 'ort' strategy.")) == \
        "Merge made by the 'ort' strategy."
    assert render(parse(json.dumps(
        {"type": "system", "subtype": "thinking_tokens",
         "estimated_tokens": 812}))) == "", "a token counter is not an event"

    line = render(parse(json.dumps(
        {"type": "system", "subtype": "task_started",
         "description": "uv run pytest -q"})))
    assert line.startswith("?? system/task_started"), line
    assert "uv run pytest -q" in line, "the payload was dropped again"

    line = render(parse(json.dumps(
        {"type": "user", "isSynthetic": True,
         "message": {"content": [{"type": "text", "text": "interrupted by user"}]}})))
    assert line.startswith("?? user") and "interrupted by user" in line, line
