"""stream-json -> plain dicts, plus the buffer that turns a byte stream into
lines.

Plain dicts, not dataclasses: the only two consumers are a renderer and (later)
a SQLite writer, and both want dicts. Seven dataclasses would be boilerplate
enforcing nothing.

Nothing in here raises. A harness upgrade that adds an event type must not kill
the supervisor and strand every lease -- this is CLAUDE.md invariant 2 one layer
down: the state machine escalates on an unknown `(stage, result)` rather than
guessing, and the parser degrades to `kind: "other"` rather than crashing.
"""
import json

MAX_TEXT = 4000    # the bound `run_cmd` already uses; a `git diff` result is a MB
MAX_BUF = 8 << 20  # untrusted subprocess output is a memory boundary
# `type` is what we dispatch on; `kind` is our normalised answer to it; the rest
# are `Store.emit()`'s own columns. No parsed record may carry any of them out
# of a passthrough branch -- see the `rate_limit_event` case below.
RESERVED = ("type", "kind", "project", "ticket", "stage", "session")


def _blocks(ev: dict) -> list:
    msg = ev.get("message")
    c = msg.get("content") if isinstance(msg, dict) else None
    return [b for b in c if isinstance(b, dict)] if isinstance(c, list) else []


def _join(blocks: list, kind: str, key: str) -> str:
    return "\n".join(str(b.get(key) or "") for b in blocks if b.get("type") == kind)


def _flat(content) -> str:
    """A tool_result's `content` is a string on some harness versions and a list
    of blocks on others."""
    if isinstance(content, list):
        return "\n".join(str(b.get("text") or "") if isinstance(b, dict) else str(b)
                         for b in content)
    return "" if content is None else str(content)


def _first(ev: dict, *keys):
    return next((ev[k] for k in keys if ev.get(k) is not None), None)


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _norm(ev: dict) -> dict:
    typ, sub = ev.get("type"), ev.get("subtype")

    # Codex `exec --json` lifecycle. Keep these beside the Claude branches,
    # because the dispatcher consumes one harness-neutral event vocabulary.
    if typ == "thread.started":
        return {"kind": "init", "session": ev.get("thread_id"),
                "model": ev.get("model"), "tools": ev.get("tools") or [],
                "permission_mode": ev.get("permission_mode"),
                "messaging_socket_path": None, "capabilities": {}}

    if typ in {"item.started", "item.completed"}:
        item = ev.get("item") if isinstance(ev.get("item"), dict) else {}
        item_type = item.get("type")
        if item_type == "agent_message":
            return {"kind": "assistant", "text": str(item.get("text") or ""),
                    "thinking": "", "tools": [], "model": ev.get("model"),
                    "usage": {}}
        if item_type == "reasoning":
            return {"kind": "assistant", "text": "",
                    "thinking": str(item.get("text") or ""), "tools": [],
                    "model": ev.get("model"), "usage": {}}
        if item_type == "command_execution":
            if typ == "item.started":
                return {"kind": "assistant", "text": "", "thinking": "",
                        "tools": [{"name": "Bash", "id": item.get("id"),
                                   "input": {"command": item.get("command") or ""}}],
                        "model": ev.get("model"), "usage": {}}
            code = item.get("exit_code")
            return {"kind": "tool_result", "tool_use_id": item.get("id"),
                    "is_error": code not in (None, 0) or item.get("status") in {
                        "failed", "errored", "interrupted"},
                    "text": str(item.get("aggregated_output") or "")[:MAX_TEXT]}
        if item_type == "mcp_tool_call":
            name = item.get("tool") or item.get("name") or "mcp"
            if typ == "item.started":
                return {"kind": "assistant", "text": "", "thinking": "",
                        "tools": [{"name": name, "id": item.get("id"),
                                   "input": item.get("arguments") or {}}],
                        "model": ev.get("model"), "usage": {}}
            return {"kind": "tool_result", "tool_use_id": item.get("id"),
                    "is_error": item.get("status") in {"failed", "errored"},
                    "text": _flat(item.get("result"))[:MAX_TEXT]}
        if item_type == "file_change":
            changes = item.get("changes") if isinstance(item.get("changes"), list) else []
            if typ == "item.started":
                return {"kind": "assistant", "text": "", "thinking": "",
                        "tools": [{"name": "apply_patch", "id": item.get("id"),
                                   "input": {"changes": changes}}],
                        "model": ev.get("model"), "usage": {}}
            return {"kind": "tool_result", "tool_use_id": item.get("id"),
                    "is_error": item.get("status") in {"failed", "errored"},
                    "text": json.dumps(changes, default=str)[:MAX_TEXT]}
        if item_type == "error":
            return {"kind": "other", "raw_type": typ, "subtype": "error",
                    "text": str(item.get("message") or "")[:MAX_TEXT]}

    if typ == "turn.completed":
        raw_usage = ev.get("usage") if isinstance(ev.get("usage"), dict) else {}
        usage = dict(raw_usage)
        if "cached_input_tokens" in raw_usage:
            usage.setdefault("cache_read_input_tokens", raw_usage["cached_input_tokens"])
        if "cache_write_input_tokens" in raw_usage:
            usage.setdefault("cache_creation_input_tokens",
                             raw_usage["cache_write_input_tokens"])
        micro = ev.get("cost_microusd")
        cost = (float(micro) / 1_000_000
                if isinstance(micro, (int, float)) else None)
        return {"kind": "result", "total_cost_usd": cost,
                "num_turns": 1, "duration_ms": ev.get("duration_ms"),
                "usage": usage, "modelUsage": {}, "permission_denials": [],
                "stop_reason": None, "is_error": False,
                "terminal_reason": None, "subtype": "success"}

    if typ == "system" and sub == "init":
        return {"kind": "init", "session": ev.get("session_id"),
                "model": ev.get("model"), "tools": ev.get("tools") or [],
                "permission_mode": _first(ev, "permissionMode", "permission_mode"),
                "messaging_socket_path": ev.get("messaging_socket_path"),
                "capabilities": ev.get("capabilities") or {}}

    if typ == "system" and sub == "hook_started":
        return {"kind": "hook_started",
                "hook": _first(ev, "hook_name", "hook", "hook_event_name"),
                "tool": _first(ev, "tool_name", "tool")}

    if typ == "system" and sub == "hook_response":
        # a guard block arrives here: non-zero exit_code plus the guard's stderr
        return {"kind": "hook_response",
                "hook": _first(ev, "hook_name", "hook", "hook_event_name"),
                "exit_code": ev.get("exit_code"), "outcome": ev.get("outcome"),
                "stderr": str(ev.get("stderr") or "")[:MAX_TEXT]}

    if typ == "assistant":
        blocks = _blocks(ev)
        msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
        return {"kind": "assistant", "text": _join(blocks, "text", "text"),
                "thinking": _join(blocks, "thinking", "thinking"),
                "tools": [{"name": b.get("name"), "id": b.get("id"),
                           "input": b.get("input") or {}}
                          for b in blocks if b.get("type") == "tool_use"],
                "model": msg.get("model"), "usage": msg.get("usage") or {}}

    if typ == "user":
        for b in _blocks(ev):
            if b.get("type") == "tool_result":
                return {"kind": "tool_result", "tool_use_id": b.get("tool_use_id"),
                        "is_error": bool(b.get("is_error")),
                        "text": _flat(b.get("content"))[:MAX_TEXT]}

    if typ == "result":
        return {"kind": "result", "total_cost_usd": _num(ev.get("total_cost_usd")),
                "num_turns": ev.get("num_turns"), "duration_ms": ev.get("duration_ms"),
                "usage": ev.get("usage") or {}, "modelUsage": ev.get("modelUsage") or {},
                "permission_denials": ev.get("permission_denials") or [],
                "stop_reason": ev.get("stop_reason"), "is_error": ev.get("is_error"),
                "terminal_reason": ev.get("terminal_reason"),
                "subtype": sub}

    if typ == "rate_limit_event":
        # Passthrough, because the useful fields here are the harness's to
        # name (`remaining_fraction` today, whatever it adds tomorrow) -- but
        # not of `RESERVED`: `kind` is ours, and the rest are the event log's
        # own columns, which a payload key must not be able to fill. The
        # store's writer excludes them too; both, not either.
        return {**{k: v for k, v in ev.items() if k not in RESERVED},
                "kind": "rate_limit"}

    # An unnamed event still carries something a human can read: a synthetic
    # `user` message's text, a task's `description`, a notification's
    # `summary`. Keep it -- `?? system` with the content dropped is why these
    # lines looked like noise rather than events.
    return {"kind": "other", "raw_type": typ, "subtype": sub,
            "text": (_join(_blocks(ev), "text", "text")
                     or str(ev.get("summary") or ev.get("description") or ""))[:MAX_TEXT]}


def parse(line: str) -> dict:
    """One stream-json line -> one normalised dict. Never raises."""
    try:
        ev = json.loads(line)
    except Exception:
        marker = "Command blocked by PreToolUse hook:"
        if marker in line:
            return {"kind": "hook_response", "hook": "PreToolUse",
                    "exit_code": 2, "outcome": "block",
                    "stderr": line.split(marker, 1)[1].strip()[:MAX_TEXT]}
        return {"kind": "other", "raw_type": None, "raw": line[:MAX_TEXT]}
    if not isinstance(ev, dict):
        return {"kind": "other", "raw_type": None, "raw": line[:MAX_TEXT]}
    try:
        return _norm(ev)
    except Exception as e:            # a shape no fixture covered; degrade, do not die
        return {"kind": "other", "raw_type": ev.get("type"),
                "error": f"{e.__class__.__name__}: {e}"}


class StreamReader:
    """The partial-line buffer for one child's stdout. No I/O of its own -- the
    caller hands it bytes and gets parsed events back.

    This is the seam TICKET-011 takes over: its selectors loop registers the
    child's stdout fd and calls `feed(os.read(fd, 65536))` from the callback.
    Today `pipeline logs -f` feeds it from the log file the child writes.
    """

    def __init__(self) -> None:
        self.buf = b""
        self.stopped = False

    def feed(self, chunk: bytes) -> list[dict]:
        if self.stopped:
            return []
        self.buf += chunk
        *lines, self.buf = self.buf.split(b"\n")
        out = [parse(ln.decode("utf-8", "replace")) for ln in lines if ln.strip()]
        if len(self.buf) > MAX_BUF:
            self.buf, self.stopped = b"", True
            out.append({"kind": "other", "raw_type": None,
                        "error": f"partial line exceeded {MAX_BUF} bytes; "
                                 f"stopped parsing this child"})
        return out
