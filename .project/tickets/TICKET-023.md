---
id: TICKET-023
stage: done
class: feature
branch: ticket/023
test_file: tests/test_ticket.py::test_the_stage_view_is_bounded_by_thread_length
files_declared:
- CLAUDE.md
- pipeline/core/config.py
- pipeline/core/ticket.py
- pipeline/daemon/supervisor.py
- pipeline/harnesses/claude-code.toml
- pipeline/stages/_common.md
- tests/test_harness.py
- tests/test_stages.py
- tests/test_ticket.py
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
  no_result: 0
lease:
  holder: null
  expires: null
last_session:
  stage: holistic-review
  id: b4793688-82ec-4a2e-bfaf-c651674c275f
  log: .project/logs/TICKET-023-holistic-review-b4793688.log
approved_by: chezzijr
approved_at: '2026-08-21T08:45:24.523999+00:00'
---

## Summary

Holistic review passed: the accumulated change is coherent. The delta is
commits `85f59c4` and `a97e7b7`, 9 files, `193 insertions(+), 12
deletions(-)`, exactly the 9 files in `files_declared`. Every editing step
of `## Plan` landed as written, no later fix undid an earlier one, the one
new failure path (`except PipelineError: view = ""` in `spawn()`) matches
the surrounding code, and nothing landed that no acceptance criterion asked
for. The view reaches an agent on both harnesses: `claude-code.toml` is
`prompt_mode = "system"` and reads the composed prompt at lines 81 and 97,
`codex.toml` is `prompt_mode = "inline"` and gets it through `render()`.

Earlier, the review stage passed the change with three non-blocking findings
recorded in `## Thread`; all 8 acceptance criteria hold. I re-ran the suite:
`uv run --group dev pytest -q tests` -> `188 passed in 8.62s` (the
implementing stage's `190` is this plus the 2 test functions pytest collects
from the guard file at the repo root). The guard is unchanged:
`git diff main...HEAD --stat` lists no file under `pipeline/hooks/`.

`stage_view()` (`pipeline/core/ticket.py`) keeps every ticket section
except `## Thread` whole and bounds only the thread to `VIEW_KEEP_KINDS`
(question/answer/rejection/approval/escalation/decision, plus any blocking
finding) at any depth, and `VIEW_RECENT = 8` trailing entries of any kind,
clipping the rest at `VIEW_CLIP = 2000` chars with a counted omission
notice. `spawn()` builds the view and `compose_prompt()` rides it into the
composed system prompt; the ticket file on disk is unchanged. The work
message (both `claude-code.toml` templates and `render()`'s inline path)
and `_common.md` rules 1 and 4 stopped ordering a whole-file read.

Measured on this ticket at review time: 50602 file bytes -> 39303 view
chars, thread trimmed to 9 of 20 entries, with both the omission notice and
one clip notice present.

The three non-blocking findings: the `severity=blocking` branch of
`_view_keep()` never fires on a real ticket, because no stage prompt tells
an agent to write a `finding` header; `pipeline resume`'s `human`/`note`
entry is bounded by recency; and `stage_view()` sits above the
`ThreadEntry` it annotates. Details and evidence are in the review entry in
`## Thread`.

A stage is handed a bounded view of the ticket instead of the whole file.

The thread is the only part of a ticket that grows without bound: 46168 of
TICKET-016's 56294 bytes (82%) sit inside `## Thread`. Every other section is
rewritten by the stage that owns it, so its size does not depend on how many
stages ran before. `stage_view()` therefore keeps every section except
`## Thread` verbatim and trims only the thread: the human-written kinds are
never dropped, plus the last 8 entries, each non-kept entry clipped at 2000
characters. Every omission is announced with a count and the ticket's path, so
nothing is hidden silently (DEC-016).

The view rides in the composed system prompt, not in a file on disk. The
ticket file is unchanged and stays the protocol between stages.

The write path is where the saving would be lost: an agent that reads the
whole ticket to `Edit` it undoes the view. Agents already edit after a partial
read (`.project/logs/TICKET-016-plan-validation-a1bbd939.log` shows two
`Edit`s after only `Read offset=385 limit=30`), so `pipeline/stages/_common.md`
instructs that explicitly.

The kinds kept at any depth are the ones `pipeline answer` and `pipeline reject`
write. A hand-appended entry parses as `note` and is bounded by recency like any
other note (gotcha 9).

The plan is in `## Plan`: 17 steps, 9 declared files. Implementation has not
started. Planning ran twice -- attempt 1 wrote the plan and died before its
sidecar. Attempt 2 verified that plan against the code at `8f6edac` rather than
rewriting it, corrected two line numbers in `## Digest` and added gotchas 9, 10
and 11. No step changed.

Plan-validation approved the plan unchanged. It re-checked the four claims the
plan leans on hardest against `8f6edac` -- `ThreadEntry` (`ticket.py:410`),
`Ticket.thread()` (`ticket.py:514-527`), `compose_prompt()` (`config.py:52`),
`spawn()`'s prompt build (`supervisor.py:300`) -- and all four match. It also
checked the four regression surfaces: every existing `compose_prompt()` caller
passes 1 or 2 arguments, `test_harness.py:88` rpartitions on `"Work ticket`
which the new sentence keeps, no test asserts the `Read {ticket} first` wording,
and the only two `ThreadEntry` constructor calls are the ones step 2 rewrites.
The riskiest step is 10, the view build in `spawn()`; its fallback is
`except PipelineError: view = ""`, proven by `tests/test_pty.py:393`. Implement
the plan as written.

## Reproduction

`tests/test_ticket.py::test_the_stage_view_is_bounded_by_thread_length`
(commit `8f6edac`).

Command:

```
uv run --group dev pytest -q tests/test_ticket.py -k stage_view
```

Failure:

```
>       small = T.stage_view(t, "implementing")
                ^^^^^^^^^^^^
E       AttributeError: module 'pipeline.core.ticket' has no attribute 'stage_view'

tests/test_ticket.py:458: AttributeError
=========================== short test summary info ============================
FAILED tests/test_ticket.py::test_the_stage_view_is_bounded_by_thread_length
1 failed, 25 deselected in 0.16s
```

expect: AttributeError: module 'pipeline.core.ticket' has no attribute 'stage_view'

The test builds one ticket, appends 5 thread entries, takes a view, appends 200
more, and takes a second view. It asserts the second view is not proportional to
the thread, and that `## Summary`, `## Digest` and `## Plan` survive in it. No
such view exists today, so the call fails before either assertion runs.

`stage_view(ticket, stage) -> str` is the test's name for the missing view, not a
required design. Planning may rename or reshape it; the two properties the test
asserts are what triage reproduced.


## Digest


Files this change touches:
- `pipeline/core/ticket.py` -- add `stage_view()`; `ThreadEntry` gains `raw`.
- `pipeline/core/config.py` -- `compose_prompt()` gains a `view` argument; `render()` stops telling the agent to read the whole ticket.
- `pipeline/daemon/supervisor.py` -- `spawn()` builds the view and hands it to `compose_prompt()`.
- `pipeline/harnesses/claude-code.toml` -- the positional work message in `cmd` and `interactive_cmd`.
- `pipeline/stages/_common.md` -- rules 1 and 4.
- `CLAUDE.md` -- one gotcha line.
- `tests/test_ticket.py`, `tests/test_stages.py`, `tests/test_harness.py`.

Key functions and entry points:
- `spawn()` at `pipeline/daemon/supervisor.py:266`. It builds the prompt at line 300 (`prompt = compose_prompt(stage, hcfg)`) and the command at lines 301-306. `Ticket` and `PipelineError` are already imported there (lines 15, 23).
- `compose_prompt()` at `pipeline/core/config.py:52`. It writes `_common.md` + the stage body + an optional skills block to one temp file. The harness reads that file with `$(cat {stage_prompt})` into `--append-system-prompt`.
- `render()` at `pipeline/core/config.py:74`. Line 92 builds the work message for `prompt_mode = "inline"` harnesses only (`codex.toml`); `claude-code.toml` carries its own copy of that sentence in each template. Both copies must change.
- `Ticket.sections()` at `pipeline/core/ticket.py:501` and `Ticket.thread()` at line 514. `KINDS` is at line 400; `ThreadEntry` at line 410. Verified on `8f6edac`; the bodies quoted in steps 1 and 2 match the file character for character.
- The gate's plan parser is `pipeline/core/gate.py:192-220`, and `MIN_DIGEST_ENTRIES = 3` is at line 23.

Gotchas, each checked against the code:
1. `tests/test_pty.py:393` calls `supervisor.spawn(tmp, tmp, "TICKET-001", "planning", ...)` where `tmp` is a bare tempdir with no ticket file. `Ticket.find` raises `PipelineError` there, so the view build must catch it and fall back to an empty view.
2. `all_tickets()` globs `.project/tickets/*.md`, so a view written as `TICKET-023.view.md` would be loaded as a ticket. This plan writes no view file at all, which sidesteps the glob, the `.gitignore` question and the stale-artifact question together.
3. `tests/test_harness.py:88` splits each template on the literal `"Work ticket` and requires the text before it to end in `--`. The new work message keeps that prefix and that position.
4. `render()` at line 95 calls `.format(**kwargs)`, so an unused keyword is harmless. `codex.toml` and `fake.toml` need no change; `codex.toml` gets the view through `prompt_mode = "inline"`, which reads the composed prompt file.
5. An agent that reads the whole ticket to `Edit` it undoes the saving. Measured: `.project/logs/TICKET-021-implementing-129840a4.log` shows one `cat` and two full `Read`s of a 92965-byte ticket, three copies of it in one context.
6. A partial read is enough for `Edit`. Measured: `.project/logs/TICKET-016-plan-validation-a1bbd939.log` shows `Read ... offset=385 limit=30`, `Read ... offset=505 limit=26`, then two successful `Edit`s of the same ticket.
7. Nothing else constructs a `ThreadEntry`: `grep -rn ThreadEntry pipeline tests` returns only `pipeline/core/ticket.py` lines 410, 515, 521 and 526. A trailing field with a default is therefore safe.
8. The pipeline guard refuses a heredoc whose text will not lex as shell (`command does not parse as a shell command`). Write multi-line content with the file tool, not with `cat <<EOF`.
9. `_parse_header()` (`pipeline/core/ticket.py:418`) returns `kind="note"` for a header it cannot parse, so a hand-appended freeform entry is bounded by recency like any note. The kinds `VIEW_KEEP_KINDS` protects at any depth are the ones `pipeline answer` and `pipeline reject` write; `.claude/skills/file-ticket/SKILL.md:160` already tells a human to use those commands rather than hand-editing a running ticket.
10. The branch `ticket/023` differs from `main` by exactly one file: `git diff --stat main..HEAD` reports `tests/test_ticket.py | 22 ++++++`. Every source line number above was read at that commit.
11. `.claude/skills/file-ticket/SKILL.md` needs no edit. It documents what a human writes into a ticket and which CLI commands exist; this change alters neither, and its one line about `## Thread` (line 23) stays true.

## Decisions checked


- **DEC-016** (active) -- every heading scan over a ticket body consults `_fenced()`; a truncated thread must not hide entries silently; storage stays plain markdown. This plan complies: `stage_view()` adds no fourth scan, it calls `Ticket.sections()` and `Ticket.thread()`, which already consult `_fenced()`. The view is derived and never written back, so the bytes on disk are unchanged. Every omission is replaced by a counted marker naming the ticket path, so no entry is hidden.
- **DEC-018** (active) -- the Tier A gate resolves `## Decisions checked` citations against `.project/decisions/` in the project root, and checks `## Digest` for `MIN_DIGEST_ENTRIES = 3` non-empty lines. The gate reads the ticket file from the root, never a view, so bounding the view changes no gate check.
- **DEC-011** (active) -- the event vocabulary and the socket protocol are frozen. This change emits no new event kind and adds no socket op.
- Grep terms used over `.project/decisions/`: `thread`, `view`, `truncat`, `context`, `token`, `read the ticket`, `summary`, `digest`. DEC-017, DEC-019, DEC-020 and DEC-021 matched none of them and constrain nothing here.

## Plan


1. In `pipeline/core/ticket.py`, add a trailing field `raw: str = ""` to `ThreadEntry` so a hand-written header reaches a view verbatim instead of being reconstructed.

        @dataclass(frozen=True)
        class ThreadEntry:
            ts: datetime | None      # None when a hand-written header does not parse
            stage: str               # "" for freeform
            kind: str                # "note" for freeform
            attrs: dict[str, str]
            text: str
            raw: str = ""            # the `### ` line as written; a view reprints it

2. In `pipeline/core/ticket.py`, populate that field in `Ticket.thread()` by carrying the raw header beside the parsed one.

        def thread(self) -> list[ThreadEntry]:
            out: list[ThreadEntry] = []
            head, raw, buf = None, "", []
            lines = self.section("Thread").splitlines()
            for line, fenced in zip(lines, _fenced(lines)):
                if line.startswith("### ") and not fenced:
                    if head is not None:
                        out.append(ThreadEntry(*head, "\n".join(buf).strip(), raw))
                    head, raw, buf = _parse_header(line[4:]), line[4:], []
                elif head is not None:
                    buf.append(line)
            if head is not None:
                out.append(ThreadEntry(*head, "\n".join(buf).strip(), raw))
            return out

3. In `pipeline/core/ticket.py`, add the view constants and the keep predicate directly below `KINDS`.

        # What a stage is asked to read. The thread is the only part of a ticket
        # that grows without bound -- 46168 of TICKET-016's 56294 bytes (82%)
        # were inside `## Thread` -- because every other section is REWRITTEN by
        # the stage that owns it. These kinds are never omitted: each carries a
        # human's words, or the reason a ticket previously stopped, and a stage
        # that acts without them acts against a decision somebody already made.
        VIEW_KEEP_KINDS = frozenset({"question", "answer", "rejection",
                                     "approval", "escalation", "decision"})
        VIEW_RECENT = 8      # trailing entries of any kind, always kept
        VIEW_CLIP = 2000     # chars per entry that is kept only for recency


        def _view_keep(e: "ThreadEntry") -> bool:
            return (e.kind in VIEW_KEEP_KINDS
                    or (e.kind == "finding" and e.attrs.get("severity") == "blocking"))

4. In `pipeline/core/ticket.py`, add `stage_view()` as a module-level function below `_view_keep`.

        def stage_view(t: "Ticket", stage: str) -> str:
            """The ticket as a stage is asked to read it: every section except
            `## Thread` verbatim, and a bounded slice of the thread.

            The bound does not depend on how many stages ran before. Sections
            are kept whole because they are rewritten, not appended to; only
            the thread grows with stage count.

            DEC-016 is why nothing is dropped silently: an omitted entry
            becomes a counted marker naming the ticket, so a stage that needs
            an older entry knows it exists and where to read it.

            `stage` names the reader in the header. There is deliberately no
            per-stage kind filter: a filter that guesses wrong drops what a
            stage needed, which is the failure TICKET-016 recorded.
            """
            entries = t.thread()
            keep = {i for i, e in enumerate(entries) if _view_keep(e)}
            keep |= set(range(max(0, len(entries) - VIEW_RECENT), len(entries)))
            out = [
                f"# {t.id} -- bounded view for the `{stage}` stage", "",
                f"The full ticket is {t.path}. Every section except `## Thread` "
                f"is below in full; the thread is trimmed to {len(keep)} of "
                f"{len(entries)} entries. To read an omitted entry, run "
                f"`grep -n {chr(39)}^### {chr(39)} {t.path}` and read only that range.", "",
            ]
            for name, text in t.sections().items():
                if name != "Thread":
                    out += [f"## {name}", "", text, ""]
            out += ["## Thread (bounded view)", ""]
            gap = 0
            for i, e in enumerate(entries):
                if i not in keep:
                    gap += 1
                    continue
                if gap:
                    out += [f"*-- {gap} earlier entries omitted; "
                            f"they are in {t.path} --*", ""]
                    gap = 0
                text = e.text
                if not _view_keep(e) and len(text) > VIEW_CLIP:
                    text = (text[:VIEW_CLIP] + f"\n\n*-- clipped here; the full "
                            f"{len(e.text)} chars are in {t.path} --*")
                out += [f"### {e.raw}", "", text, ""]
            return "\n".join(out).rstrip() + "\n"

5. Run the committed reproduction against `pipeline/core/ticket.py` and confirm it now passes: `uv run --group dev pytest -q tests/test_ticket.py -k stage_view`, expected `1 passed`.

6. In `tests/test_ticket.py`, add the test that defends DEC-016 -- the kinds a view must never drop, and the omission notice.

        def test_the_stage_view_keeps_every_human_entry():
            """DEC-016: a view that drops what a later stage needed is worse than
            a large ticket. A human's answer, rejection or approval is never
            recoverable from a summary, so those kinds survive at any depth --
            while a non-blocking finding at the same depth does not, which is
            what keeps the view bounded."""
            d = project()
            t = Ticket.load(d / ".project/tickets/TICKET-001.md")
            t.append("planning", "question", "QUESTION-MARKER: which design?")
            t.append("planning", "answer", "ANSWER-MARKER: the second one")
            t.append("planning", "rejection", "REJECT-MARKER: not that plan")
            t.append("review", "finding", "BLOCKER-MARKER: it drops entries",
                     severity="blocking")
            t.append("review", "finding", "MINOR-MARKER: a nit", severity="minor")
            for i in range(200):
                t.append("implementing", "note", f"filler {i} " + "x" * 400)
            view = T.stage_view(t, "implementing")
            for marker in ("QUESTION-MARKER", "ANSWER-MARKER", "REJECT-MARKER",
                           "BLOCKER-MARKER"):
                assert marker in view, f"the view dropped a {marker} entry"
            assert "MINOR-MARKER" not in view, (
                "a non-blocking finding 200 entries back was kept -- the view "
                "is not bounded")
            assert "earlier entries omitted" in view, (
                "the view omitted entries without saying so -- DEC-016")
            shutil.rmtree(d)

7. Run both ticket tests against `pipeline/core/ticket.py`: `uv run --group dev pytest -q tests/test_ticket.py`, expected `0 failed`.

8. In `pipeline/core/config.py`, give `compose_prompt()` a `view` argument and append the view after the skills block, leaving every other line of the function unchanged.

        def compose_prompt(stage: str, hcfg: dict | None = None,
                           view: str = "") -> Path:
            # ... existing body, up to and including the skills block ...
            if view:
                text += ("\n\n---\n\n# The ticket\n\nThis is a bounded view of "
                         "the ticket named in your instructions -- the ticket's "
                         "own text, trimmed. Read it here; open the file only "
                         "for what the view says it omitted.\n\n" + view)
            f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
            # ... existing tail, unchanged ...

9. In `pipeline/core/config.py`, replace the work message at line 92 so an inline-prompt harness stops ordering a whole-ticket read.

        work = (f"Work ticket {tid}. Your prompt carries a bounded view of "
                f"{ticket_q}; open that file only for what the view says it "
                f"omitted, and read only the lines you need. When finished "
                f"write {result_q}")

10. In `pipeline/daemon/supervisor.py`, add `stage_view` to the `pipeline.core.ticket` import at line 23, and replace line 300 in `spawn()` with the total view build below.

        try:
            view = stage_view(Ticket.find(project, tid), stage)
        except PipelineError:
            # Total: `spawn()` is called directly with no ticket on disk
            # (tests/test_pty.py:393). No view means the agent reads the file,
            # which is exactly what it did before this existed.
            view = ""
        prompt = compose_prompt(stage, hcfg, view)

11. In `pipeline/harnesses/claude-code.toml`, replace the positional work message in both `cmd` and `interactive_cmd` with the sentence below, keeping the leading double-quote plus `Work ticket` and the preceding `--` exactly where they are.

        "Work ticket {id}. Your prompt carries a bounded view of {ticket}; open that file only for what the view says it omitted, and read only the lines you need. When finished write {result_file}"

12. In `pipeline/stages/_common.md`, replace rule 1 and extend rule 4 so the write path cannot reintroduce a whole-file read.

        [rule 1] Your prompt carries a bounded view of the ticket: every section
           except `## Thread`, plus the thread entries your stage acts on.
           Read it before doing anything. Open the ticket file itself only for
           an entry the view says it omitted, and read only that range --
           grep the file for `^### ` to get the line number.

        [rule 4] Append your findings to `## Thread` (never rewrite existing
           entries) and rewrite `## Summary` so the next stage can skip the
           thread. Locate the section by grepping the file for `^## `, then
           read only that range before you edit it. Never read the whole
           ticket file in order to make an edit -- that is the cost the view
           exists to remove.

13. In `tests/test_stages.py`, add the test that the composed prompt carries the view and still builds without one.

        def test_the_composed_prompt_carries_the_stage_view():
            """The view reaches the agent through the system prompt, not a file
            it has to open. A prompt built without one is the pre-TICKET-023
            behaviour and must stay buildable -- `spawn()` falls back to it."""
            f = C.compose_prompt("review", None, "VIEW-MARKER-9137")
            text = f.read_text()
            f.unlink()
            assert "VIEW-MARKER-9137" in text, "the view never reached the prompt"
            assert "Failure protocol" in text, "the shared rules were displaced"
            g = C.compose_prompt("review")
            plain = g.read_text()
            g.unlink()
            assert "VIEW-MARKER-9137" not in plain and "# The ticket" not in plain

14. In `tests/test_harness.py`, add the test that no work message orders a whole-ticket read while every template still names the ticket path.

        def test_the_work_message_points_at_the_view_not_the_whole_ticket():
            """The saving is lost the moment the agent is told to read the file.
            Both claude-code templates and render()'s inline message carry their
            own copy of that sentence, so both are checked."""
            hcfg = config.harness("claude-code")
            for key in ("cmd", "interactive_cmd"):
                tpl = hcfg[key]
                assert "Read {ticket} first" not in tpl, f"{key}: orders a full read"
                assert "bounded view" in tpl, f"{key}: does not name the view"
                assert "{ticket}" in tpl, f"{key}: the agent must still write there"
            prompt = config.compose_prompt("review")
            cmd = config.render(config.harness("codex"),
                                config.stage_config("review"), tid="TICKET-001",
                                project=Path("/proj"), ticket=Path("/proj/t.md"),
                                result_file=Path("/proj/t.result"), session="s",
                                prompt=prompt)
            prompt.unlink()
            assert "Work ticket TICKET-001" in cmd
            assert "Read /proj/t.md first" not in cmd
            assert "bounded view" in cmd

15. Run the suites that cover this wiring: `uv run --group dev pytest -q tests/test_ticket.py tests/test_stages.py tests/test_harness.py tests/test_pty.py`, expected `0 failed`. `tests/test_pty.py` is in the list because the fallback added to `pipeline/daemon/supervisor.py` is what keeps it green.

16. In `CLAUDE.md`, add one gotcha under the "Gotchas, each found the hard way" list.

        - **A stage reads a bounded view, not the ticket file.** `stage_view()`
          (`pipeline/core/ticket.py`) keeps every section except `## Thread`
          whole and trims the thread to the human-written kinds plus the last
          `VIEW_RECENT` entries; `spawn()` puts it in the composed prompt. The
          file on disk is unchanged and stays the protocol. A stage that reads
          the whole file to make an edit undoes the saving -- `_common.md`
          rule 4 is what stops it.

17. Run the full suite and the guard script and paste both outputs into `## Thread`: `uv run --group dev pytest -q`, then `./pipeline/hooks/test_dangerous_commands.py`. The guard is not in `files_declared`, so it must be unchanged and green; the suite covers `pipeline/core/ticket.py`, `pipeline/core/config.py`, `pipeline/daemon/supervisor.py`, `tests/test_ticket.py`, `tests/test_stages.py` and `tests/test_harness.py`.

## Acceptance criteria


1. The committed reproduction passes: `tests/test_ticket.py::test_the_stage_view_is_bounded_by_thread_length`. Command: `uv run --group dev pytest -q tests/test_ticket.py -k stage_view`, expected `1 passed`.
2. No always-kept entry is dropped, a non-blocking finding 200 entries back is dropped, and the omission is announced: `tests/test_ticket.py::test_the_stage_view_keeps_every_human_entry`.
3. The view reaches the agent through the composed prompt, and a prompt built without one still builds: `tests/test_stages.py::test_the_composed_prompt_carries_the_stage_view`.
4. No work message orders a whole-ticket read, and every template still names the ticket path the agent writes to: `tests/test_harness.py::test_the_work_message_points_at_the_view_not_the_whole_ticket`.
5. `spawn()` against a project with no ticket file still returns a record rather than raising: the existing `tests/test_pty.py` test at line 393, which calls `supervisor.spawn(tmp, tmp, "TICKET-001", "planning", ...)` on a bare tempdir.
6. The existing prompt and command contracts still hold: `tests/test_stages.py::test_composed_prompt_has_common_rules_and_no_frontmatter`, and the `rpartition` check at `tests/test_harness.py:88`.
7. The whole dispatcher suite is green: `uv run --group dev pytest -q` reports `0 failed`.
8. The guard is untouched and green: `./pipeline/hooks/test_dangerous_commands.py` exits 0.

## Decisions


The thread is the only part of a ticket that grows without bound, and that is
why `stage_view()` trims only `## Thread`. Every other section is *rewritten*
by the stage that owns it -- `## Digest` by planning, `## Summary` by whichever
stage ran last -- so its size does not depend on how many stages ran before.
Measured on TICKET-016: 46168 of 56294 bytes (82%) sat inside the thread. If a
future section starts being appended to rather than rewritten, it has to join
the bounded half; until then, keeping sections whole is what makes the view
safe to hand a stage.

**These thread kinds are never omitted, at any age or count:** `question`,
`answer`, `rejection`, `approval`, `escalation`, `decision`, and any `finding`
carrying `severity=blocking`. Each is either a human's own words or the reason
the ticket previously stopped, and none is recoverable from a summary.
`pipeline/stages/planning.md` requires reading *every* `rejection` before
writing a plan; a view that dropped one would make that instruction a lie.
Dropped by default, kept only inside the recent window: `note` (the bulk by
bytes), `session`, `transition`, `gate`, and non-blocking `finding`. TICKET-016
exists because a truncated thread silently hid entries, so **every omission is
announced** with a count and the ticket's path. Do not add a silent drop, and
do not add a per-stage kind filter: a filter that guesses wrong drops what a
stage needed, which is the exact failure being guarded against.

**The view rides in the composed system prompt, not in a file on disk.** A view
file under `.project/tickets/` carrying a `.md` suffix would be matched by
`all_tickets()` and loaded as a ticket; any view file there would be a second
copy of the protocol in a git-tracked directory, and would cost the agent a
read turn. Building it into `compose_prompt()` costs none of those. The ticket
file itself is untouched -- it stays the hand-editable protocol between stages
(DEC-016).

**The write path is where this saving is lost, and `_common.md` rule 4 is what
holds it.** An agent that reads the whole ticket in order to `Edit` it puts the
full file back in context and the view has bought nothing: measured on
`.project/logs/TICKET-021-implementing-129840a4.log`, one `cat` plus two full
`Read`s of a 92965-byte ticket, three copies in one context. A partial read is
enough for `Edit` -- `.project/logs/TICKET-016-plan-validation-a1bbd939.log`
shows `Read offset=385 limit=30` and `Read offset=505 limit=26` followed by two
successful `Edit`s of that same file. Do not relax rule 4 back to "read the
ticket file completely".

**The view build in `spawn()` is total.** A ticket that will not load yields an
empty view, and the agent falls back to reading the file, which is what it did
before this existed. `tests/test_pty.py:393` calls `spawn()` against a bare
tempdir with no ticket in it; without the `except PipelineError` that test dies
on the view rather than on anything it is testing.

## Rollback


Revert the merge commit. Nothing here writes to disk in a new format: ticket
files, `.project/decisions/`, the event database and the worktrees are all
untouched, so there is no migration to undo and no artifact to clean up.

The symptom that this shipped and broke something is a stage acting without
information it should have had -- a plan that ignores a `rejection`, a review
that re-raises a finding already answered. The one-line mitigation is to raise
`VIEW_RECENT` in `pipeline/core/ticket.py`, or to make `stage_view()` return
the whole body, which restores the old behaviour without touching the harness,
the stage prompts or `pipeline/daemon/supervisor.py`.

## Thread

### 2026-08-21 08:20:07Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-21 08:22:16Z · triage · note

Reproduced. The symptom is the absence of a bounded stage-facing view, so the
proof is a test that asks for one and fails.

Confirmed the ticket's numbers on disk:

```
$ wc -c .project/tickets/TICKET-016.md .project/tickets/TICKET-021.md
 56435 .project/tickets/TICKET-016.md
 92965 .project/tickets/TICKET-021.md
```

Traced what a stage is actually handed. `pipeline/harnesses/claude-code.toml:77`
spawns the agent with `"Work ticket {id}. Read {ticket} first."` -- `{ticket}` is
the raw file path, and `pipeline/stages/_common.md:9` says "Read the ticket file
completely before doing anything." Nothing between the dispatcher and the agent
narrows the file. `Ticket.thread()` returns typed `ThreadEntry` objects with
`ts`, `stage`, `kind` and `attrs`, so the data a view needs is already parsed;
no caller uses it to build one.

Notes for planning, outside triage's scope:

1. `gate.py:105` checks `## Digest` for non-emptiness only (`.project/known-issues.md:9`).
   A view that leans on `## Digest` inherits that weakness.
2. The test's bound is `len(big) < 2 * len(small) + 4000`. It catches growth
   proportional to the thread. It does not pin an exact budget; pick one in the
   plan if a tighter bound is wanted.
3. TICKET-016's constraint applies: name in the plan which entry kinds are always
   kept. `KINDS` (`pipeline/core/ticket.py`) lists the vocabulary a stage may write.

### 2026-08-21 08:22:38Z · triage · session · session=385b0e3e-2e6f-4241-9fdc-eb2dfb9cdcb1

`triage` ran as session `385b0e3e-2e6f-4241-9fdc-eb2dfb9cdcb1`
- replay: `claude --resume 385b0e3e-2e6f-4241-9fdc-eb2dfb9cdcb1`
- log: `.project/logs/TICKET-023-triage-385b0e3e.log`

### 2026-08-21 08:22:38Z · triage · transition · to=planning · result=ok

**triage -> planning** (result: `ok`)

✓ Reproduced: no bounded stage view exists; failing test committed as 8f6edac

### 2026-08-21 08:33:45Z · planning · note

Plan written. 17 steps, 9 declared files.

Design: `stage_view()` keeps every section except `## Thread` verbatim and
bounds only the thread. Non-thread sections are rewritten by the stage that
owns them, so they do not grow with stage count; the thread does.

Always kept, at any depth: `question`, `answer`, `rejection`, `approval`,
`escalation`, `decision`, and `finding` with `severity=blocking`. Recent
window only: `note`, `session`, `transition`, `gate`, non-blocking `finding`.
Every omission is announced with a count and the ticket path (DEC-016).

The view goes into the composed system prompt, not a file on disk. A view
file under `.project/tickets/` with a `.md` suffix would be loaded by
`all_tickets()` as a ticket.

Finding outside this stage's scope, recorded rather than fixed: the write
path is what decides whether the view pays off. Measured on
`.project/logs/TICKET-021-implementing-129840a4.log`, the implementing agent
put three copies of a 92965-byte ticket in one context: one `cat` and two
full `Read`s. Step 12 rewrites `pipeline/stages/_common.md` rule 4 to forbid
that; the evidence it is achievable is
`.project/logs/TICKET-016-plan-validation-a1bbd939.log`, where two `Edit`s of
the ticket succeeded after only `Read offset=385 limit=30` and
`Read offset=505 limit=26`. If a later measurement shows stages still reading
the file whole, the next step is a CLI write path, not a bigger prompt rule.

Second finding, outside scope: the pipeline guard rejects a heredoc whose
text will not lex as shell. `cat > /tmp/x <<EOF` with prose containing
apostrophes returned `command does not parse as a shell command`. Multi-line
content has to go through a file tool. Recorded as gotcha 8 in `## Digest`.

### 2026-08-21 08:33:45Z · planning · session · session=44a1f678-ffad-4819-b93f-37e148384f66

`planning` ran as session `44a1f678-ffad-4819-b93f-37e148384f66`
- replay: `claude --resume 44a1f678-ffad-4819-b93f-37e148384f66`
- log: `.project/logs/TICKET-023-planning-44a1f678.log`

### 2026-08-21 08:33:45Z · planning · note

`planning` wrote no .result sidecar (attempt 1) -- will respawn

### 2026-08-21 09:00:00Z · planning · note

Planning attempt 2. The plan attempt 1 wrote is complete; it died before its
sidecar. No `rejection` entry exists, so nobody asked for a different plan. I
verified the existing plan against the code rather than rewriting it, and I
report it as this stage's output.

What I checked, and the result:

1. Steps 1 and 2 quote `ThreadEntry` and `Ticket.thread()`. Both match
   `pipeline/core/ticket.py` character for character at `8f6edac`.
2. Step 10 replaces `prompt = compose_prompt(stage, hcfg)`. That line is
   `pipeline/daemon/supervisor.py:300`, exactly as the digest says, and
   `Ticket` and `PipelineError` are already imported at lines 24 and 15.
3. Step 9 replaces `render()`'s work message. `pipeline/core/config.py:92`
   reads `work = f"Work ticket {tid}. Read {ticket_q} first. When finished
   write {result_q}"`.
4. Step 11 replaces two template copies. `grep -n 'Work ticket'` returns
   `pipeline/harnesses/claude-code.toml:77` and `:93`, both carrying
   `Read {ticket} first`. No other harness file matches.
5. Step 12 replaces `_common.md` rules 1 and 4. Rule 1 today reads "Read the
   ticket file completely before doing anything."
6. All three cited decision ids resolve: `DEC-011.md`, `DEC-016.md` and
   `DEC-018.md` are in `.project/decisions/`. `grep -n 'superseded-by'` over
   that directory returns nothing, so all three are active and this plan
   complies with each.
7. The reproduction's bound holds under step 4's code. The test keeps 5
   entries in `small` and 8 in `big` at ~430 chars each, so `big` grows by
   roughly 1300 chars against a budget of `len(small) + 4000`.
8. `T.sections(t.body)[name] in big` holds: step 4 emits each section's text
   verbatim, and `pipeline/templates/ticket.md` has all of `## Summary`,
   `## Digest` and `## Plan`.

Three corrections to `## Digest`, all line numbers, none changing a step:
`KINDS` is at line 400 not 402, `Ticket.sections()` at 501 not 504. Added
gotcha 9, which attempt 1 missed: `_parse_header()` returns `kind="note"` for
a header it cannot parse, so a *hand-appended* thread entry is bounded by
recency like any note. The human kinds the view protects at any depth are the
ones `pipeline answer` and `pipeline reject` write, which is the path
`.claude/skills/file-ticket/SKILL.md:160` already tells a human to use. Added
gotchas 10 and 11 recording the commit the line numbers were read at and why
the `file-ticket` skill needs no edit.

Finding outside this stage's scope, recorded rather than fixed: the earlier
`no_result` cost this ticket a spawn for a plan that was already on disk. The
dispatcher cannot tell "the agent crashed before writing" from "the agent did
nothing", so it re-ran a stage whose work was complete. A cheap guard would be
for the respawned stage to read what is already in the ticket first, which is
what this run did.

### 2026-08-21 08:37:12Z · planning · session · session=9acd6cd7-5d58-4757-9a28-b1605154113c

`planning` ran as session `9acd6cd7-5d58-4757-9a28-b1605154113c`
- replay: `claude --resume 9acd6cd7-5d58-4757-9a28-b1605154113c`
- log: `.project/logs/TICKET-023-planning-9acd6cd7.log`

### 2026-08-21 08:37:12Z · planning · transition · to=plan-validation · result=ok

**planning -> plan-validation** (result: `ok`)

✓ Plan verified against code at 8f6edac and reported: 17 steps, 9 files; attempt 1 wrote it and died before its sidecar

### 2026-08-21 08:41:00Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_ticket.py::test_the_stage_view_is_bounded_by_thread_length` fails as required
```
===============================
_______________ test_the_stage_view_is_bounded_by_thread_length ________________

    def test_the_stage_view_is_bounded_by_thread_length():
        """The symptom of TICKET-023: what a stage is asked to read grows with the
        thread. A stage is handed a view, and its size must not depend on how many
        stages ran before it -- while `## Summary`, `## Digest` and `## Plan`, the
        parts a later stage acts on, stay in it."""
        d = project()
        p = d / ".project/tickets/TICKET-001.md"
        t = Ticket.load(p)
        for i in range(5):
            t.append("implementing", "note", f"early entry {i} " + "x" * 400)
>       small = T.stage_view(t, "implementing")
                ^^^^^^^^^^^^
E       AttributeError: module 'pipeline.core.ticket' has no attribute 'stage_view'

tests/test_ticket.py:458: AttributeError
=========================== short test summary info ============================
FAILED tests/test_ticket.py::test_the_stage_view_is_bounded_by_thread_length
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.04s ===============================

```
- ok: `tests/test_ticket.py::test_the_stage_view_is_bounded_by_thread_length` fails on base `main` too -- the bug is not already fixed upstream
```
"
        t = Ticket.load(p)
        for i in range(5):
            t.append("implementing", "note", f"early entry {i} " + "x" * 400)
>       small = T.stage_view(t, "implementing")
                ^^^^^^^^^^^^
E       AttributeError: module 'pipeline.core.ticket' has no attribute 'stage_view'

tests/test_ticket.py:458: AttributeError
=========================== short test summary info ============================
FAILED tests/test_ticket.py::test_the_stage_view_is_bounded_by_thread_length
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.16s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-12b47doo/base
      Built pipeline @ file:///tmp/pipeline-base-12b47doo/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-21 08:55:00Z · plan-validation · approval

Plan approved. Every item passes; the reasoning per item follows.

**Root cause.** A stage is handed the whole ticket file, and the thread is the
one section that grows with every stage that ran before it (46168 of 56294
bytes on TICKET-016). Two paths carry that cost: the work message orders a
full read (`pipeline/core/config.py:92` and both `claude-code.toml` templates,
lines 77 and 93), and `_common.md` rule 1 orders it again. The plan fixes both,
plus the write path (rule 4), not only the read path. It does not make the test
pass by adding a stub -- steps 8 to 12 wire the view into the prompt that
`spawn()` builds.

**Decision conflict.** DEC-016 is the one that constrains this plan, and it
constrains it twice. It requires every heading scan to consult `_fenced()`:
`stage_view()` adds no scan, it calls `Ticket.sections()` (`ticket.py:501`)
and `Ticket.thread()` (`ticket.py:514`), which already do. It forbids entries
vanishing silently: step 4 replaces each omission with a counted marker naming
`t.path`. DEC-018's gate reads the file, not the view, so no gate check moves.
DEC-011 freezes the event and socket vocabulary; this change adds neither.

**Scope discipline.** 17 steps over 9 files, class `feature` -- 6 source files
and 3 test files, and every source file is a link in one chain: view builder
(`ticket.py`), prompt (`config.py`), spawn (`supervisor.py`), work message
(`claude-code.toml`), stage rules (`_common.md`). Step 16 (a `CLAUDE.md`
gotcha) is the only step no acceptance criterion names. It is a documentation
line this repo's own conventions require, so I do not count it as creep.

**Falsifiable criteria.** Criterion 2's test fails on both sides: an
implementation that kept everything trips `assert "MINOR-MARKER" not in view`,
and one that dropped human entries trips the four marker assertions. Criterion
3 asserts a literal `VIEW-MARKER-9137` reaches the composed prompt and is
absent from a prompt built without one. Criterion 4 asserts
`"Read {ticket} first" not in tpl` for both templates. None is vacuous.

**No research left.** Every step names a file and a symbol, and the code it
quotes matches `8f6edac`. I checked the four the plan leans on hardest:
`ThreadEntry` has exactly the 5 fields step 1 extends (`ticket.py:410`);
`Ticket.thread()` is character-for-character what step 2 rewrites
(`ticket.py:514-527`); `compose_prompt()` takes `(stage, hcfg)` today
(`config.py:52`); `spawn()` builds the prompt at `supervisor.py:300` with
`Ticket` and `PipelineError` already imported (lines 23 and 15).

**Riskiest step and its fallback.** Step 10, the view build inside `spawn()`:
it runs for every stage of every ticket, and a raise there kills the spawn
rather than the view. The plan states the fallback in the step and again in
`## Decisions` -- `except PipelineError: view = ""`, and the agent reads the
file as it did before. `tests/test_pty.py:393` is the case that proves it:
`supervisor.spawn(tmp, tmp, "TICKET-001", "planning", harness("fake"), plain)`
against a bare tempdir with no ticket in it.

**Regression surface.** Four surfaces, each with a test named in the criteria.
1. `compose_prompt()`'s new third argument defaults to `""`; all 8 existing
   callers pass 1 or 2 arguments (`test_stages.py:20,62,67`,
   `test_harness.py:39,59,106,154`, `test_pty.py:355`), so none breaks.
2. The `--` separator before the positional prompt: `test_harness.py:88`
   rpartitions on `"Work ticket`, which the new sentence keeps.
3. The inline work message: `test_harness.py:50` asserts only
   `"Work ticket TICKET-001" in cmd`. Nothing in `tests/` asserts the
   `Read {ticket} first` wording, so removing it breaks no existing test.
4. `ThreadEntry`'s new field: the only constructor calls are
   `ticket.py:521` and `526`, both rewritten in step 2.

**Blast radius matches class.** A `feature` ticket, 6 source files, and the
change is one new function plus one argument threaded through two callers.
`git diff --stat main..HEAD` is `tests/test_ticket.py | 22 ++++++` -- the
reproduction only.

**One trade the plan states rather than hides.** The view is bounded in the
kinds it clips, not in every dimension: `VIEW_KEEP_KINDS` entries are kept at
any depth and unclipped, so a ticket with many rejections still grows. The
`## Decisions` section chooses that deliberately ("a filter that guesses wrong
drops what a stage needed") and `## Rollback` names `VIEW_RECENT` as the knob.
The reproduction appends only notes, so it holds.

### 2026-08-21 08:44:33Z · plan-validation · session · session=36406001-7ca7-4fa0-80ec-d78c24be342f

`plan-validation` ran as session `36406001-7ca7-4fa0-80ec-d78c24be342f`
- replay: `claude --resume 36406001-7ca7-4fa0-80ec-d78c24be342f`
- log: `.project/logs/TICKET-023-plan-validation-36406001.log`

### 2026-08-21 08:44:33Z · plan-validation · transition · to=awaiting-approval · result=ok

**plan-validation -> awaiting-approval** (result: `ok`)

✓ Plan approved: root cause named, DEC-016 complied with, step 10's fallback stated, 4 regression surfaces checked against 8f6edac.

### 2026-08-21 08:45:24Z · human · approval · by=chezzijr

**approved by chezzijr**

### 2026-08-21 08:55:40Z · plan-validation · gate · verdict=PASS

**Tier A gate: PASS**

- ok: `tests/test_ticket.py::test_the_stage_view_is_bounded_by_thread_length` fails as required
```
===============================
_______________ test_the_stage_view_is_bounded_by_thread_length ________________

    def test_the_stage_view_is_bounded_by_thread_length():
        """The symptom of TICKET-023: what a stage is asked to read grows with the
        thread. A stage is handed a view, and its size must not depend on how many
        stages ran before it -- while `## Summary`, `## Digest` and `## Plan`, the
        parts a later stage acts on, stay in it."""
        d = project()
        p = d / ".project/tickets/TICKET-001.md"
        t = Ticket.load(p)
        for i in range(5):
            t.append("implementing", "note", f"early entry {i} " + "x" * 400)
>       small = T.stage_view(t, "implementing")
                ^^^^^^^^^^^^
E       AttributeError: module 'pipeline.core.ticket' has no attribute 'stage_view'

tests/test_ticket.py:458: AttributeError
=========================== short test summary info ============================
FAILED tests/test_ticket.py::test_the_stage_view_is_bounded_by_thread_length
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.08s ===============================

```
- ok: `tests/test_ticket.py::test_the_stage_view_is_bounded_by_thread_length` fails on base `main` too -- the bug is not already fixed upstream
```
"
        t = Ticket.load(p)
        for i in range(5):
            t.append("implementing", "note", f"early entry {i} " + "x" * 400)
>       small = T.stage_view(t, "implementing")
                ^^^^^^^^^^^^
E       AttributeError: module 'pipeline.core.ticket' has no attribute 'stage_view'

tests/test_ticket.py:458: AttributeError
=========================== short test summary info ============================
FAILED tests/test_ticket.py::test_the_stage_view_is_bounded_by_thread_length
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
============================== 1 failed in 0.15s ===============================
Using CPython 3.13.11
Creating virtual environment at: .venv
   Building pipeline @ file:///tmp/pipeline-base-ymlt4arh/base
      Built pipeline @ file:///tmp/pipeline-base-ymlt4arh/base
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 18 packages in 10ms

```

### 2026-08-21 08:55:40Z · revalidating · transition · to=implementing · result=ok

**revalidating -> implementing** (result: `ok`)

re-gated after rebasing onto base:
- clean

### 2026-08-21 09:30:00Z · implementing · note

Implemented the plan as approved, all 17 steps, no deviation.

`stage_view()` added to `pipeline/core/ticket.py`: `ThreadEntry` gained
`raw`, `Ticket.thread()` carries it, `VIEW_KEEP_KINDS`/`VIEW_RECENT`/
`VIEW_CLIP`/`_view_keep()` added below `KINDS`, `stage_view()` added below
`_view_keep()`. `compose_prompt()` gained a `view: str = ""` argument
(`pipeline/core/config.py`) and appends it after the skills block.
`render()`'s inline work message and both `claude-code.toml` templates
(`cmd`, `interactive_cmd`) stopped ordering `Read {ticket} first` and now
name the bounded view instead. `spawn()` (`pipeline/daemon/supervisor.py`)
builds the view with `Ticket.find()` + `stage_view()`, catching
`PipelineError` to `view = ""` for the no-ticket-on-disk case. `_common.md`
rules 1 and 4 rewritten to point at the view and forbid a whole-file read
before an edit. `CLAUDE.md` gotcha added.

Reproduction: `uv run --group dev pytest -q tests/test_ticket.py -k stage_view`
-> `1 passed, 25 deselected`.

New tests added and passing: `test_the_stage_view_keeps_every_human_entry`
(`tests/test_ticket.py`), `test_the_composed_prompt_carries_the_stage_view`
(`tests/test_stages.py`), `test_the_work_message_points_at_the_view_not_the_whole_ticket`
(`tests/test_harness.py`).

Wiring suites: `uv run --group dev pytest -q tests/test_ticket.py
tests/test_stages.py tests/test_harness.py tests/test_pty.py` ->
`63 passed`.

Full suite: `uv run --group dev pytest -q` -> `190 passed in 8.61s`.

Guard: `./pipeline/hooks/test_dangerous_commands.py` -> `guard: all passed`,
exit 0. The guard file itself is unchanged, as `files_declared` requires.

Committed as `feat: hand a stage a bounded view of the ticket instead of the whole file`.

### 2026-08-21 08:59:40Z · implementing · session · session=a97eea3a-04f4-4ee0-b4fc-43d13d6eb299

`implementing` ran as session `a97eea3a-04f4-4ee0-b4fc-43d13d6eb299`
- replay: `claude --resume a97eea3a-04f4-4ee0-b4fc-43d13d6eb299`
- log: `.project/logs/TICKET-023-implementing-a97eea3a.log`

### 2026-08-21 08:59:40Z · implementing · transition · to=review · result=ok

**implementing -> review** (result: `ok`)

✓ Implemented all 17 plan steps; stage_view() bounds the thread, wiring commits at a97e7b7, 190 tests pass, guard passes.

### 2026-08-21 10:05:00Z · review · note

Reviewed the delta `main...HEAD`: commits `85f59c4` and `a97e7b7`, 9 files,
193 insertions. This is the first review pass, so the delta is the whole
branch. No blocking findings. Three non-blocking findings below.

Evidence I ran myself:

1. `uv run --group dev pytest -q tests` -> `188 passed in 8.48s`. The
   implementing stage reported `190`; the difference is the 2 test
   functions pytest collects from `pipeline/hooks/test_dangerous_commands.py`
   when it runs at the repo root. Both counts are the same suite.
2. `git diff --stat main...HEAD -- pipeline/hooks/` prints nothing, so the
   guard is byte-identical to `main` and acceptance criterion 8 holds
   without re-running it. I could not run the guard script: the read-only
   allowlist has no entry for it, and `python <path>` is rejected because
   `GUARDED["python"]` accepts only `-m`.
3. `git status --porcelain -- . ':(exclude).project'` prints nothing. I
   changed no file except this ticket.
4. `stage_view()` on this ticket file: 50602 file bytes -> 39303 view chars,
   thread trimmed to 9 of 20 entries. The view contains
   `*-- 11 earlier entries omitted; they are in .../TICKET-023.md --*` and
   `*-- clipped here; the full 2680 chars are in .../TICKET-023.md --*`.
5. The rendered `claude-code` command lexes to 24 tokens and its last token
   is the whole work message, so the new sentence's `;` and `--` stay
   inside one positional argument.

Acceptance criteria, each checked:

1. Reproduction passes -- in the 188.
2. `test_the_stage_view_keeps_every_human_entry` passes -- in the 188.
3. `test_the_composed_prompt_carries_the_stage_view` passes -- in the 188.
4. `test_the_work_message_points_at_the_view_not_the_whole_ticket` passes.
5. `tests/test_pty.py` passes, so the `except PipelineError: view = ""`
   fallback holds. `Ticket.load()` wraps every load exception in
   `PipelineError` (`ticket.py:517-520`), so the `except` is total for a
   ticket that will not load.
6. Both existing contracts pass -- in the 188.
7. `0 failed`.
8. Guard untouched, per evidence 2.

Plan conformance: all 17 steps landed as written. `files_declared` lists 9
files and the diff touches exactly those 9. No file outside it changed.
Nothing in `pipeline/hooks/`, `transition()`, `validate_meta()` or
`CONTROL_FIELDS` was touched, so the CLAUDE.md human-review-before-merge
rule is not triggered by the code (the human approval gate still is).

Findings:

1. **minor** -- The `severity=blocking` branch of `_view_keep()`
   (`pipeline/core/ticket.py:415-417`) never fires on a real ticket. It
   requires a thread header of the form
   `### <ts> · <stage> · finding · severity=blocking`, but no stage prompt
   asks an agent to write one: `pipeline/stages/review.md:31` says only
   "Append findings as a numbered list with a severity on each", so a
   review agent writes one `note` entry -- this entry is one. Only
   `t.append(..., "finding", severity="blocking")` produces that header,
   and `grep -rn '\.append("' pipeline/` shows no non-test caller doing so.
   `test_the_stage_view_keeps_every_human_entry` therefore passes on an
   entry shape production never creates. Not blocking: a blocking finding
   still reaches the next review through recency. Counted on this ticket's
   own history, a review run appends 3 entries (note, session, transition)
   and an implementing run appends 3, so a finding from review 1 sits 6
   entries from the end when review 2 reads it, inside `VIEW_RECENT = 8`.
   The margin is 2 entries, and `## Decisions` claims the protection is
   unconditional. Either instruct the finding header in `review.md` or
   correct the claim.
2. **minor** -- `pipeline resume` writes `t.append("human", "note", ...)`
   (`pipeline/cli/main.py:171`), so a human's own resume entry is bounded
   by recency like any other note, while `## Decisions` says human words
   are never omitted. The text is bookkeeping ("**resumed** by human ->
   `<stage>`, reset [...]"), not an instruction a stage acts on, so the
   loss is small.
3. **nit** -- `stage_view()` and `_view_keep()` are defined at
   `ticket.py:415-462`, above the `ThreadEntry` dataclass at line 473 that
   they annotate. The annotations are strings, so this runs; it is only
   reading order. The plan placed them "directly below `KINDS`", which is
   what happened, so this is the plan's choice, not drift.

Two things I checked and found correct, recorded so a later stage does not
re-check them: `sections()` drops any body text before the first `## `, but
`pipeline/templates/ticket.md` starts at `## Summary`, so the view's claim
to carry every section in full holds; and `.claude/skills/file-ticket/SKILL.md`
needs no edit, as `## Digest` gotcha 11 states -- its only line about the
thread (line 23) names `pipeline answer` / `reject`, both of which write
kinds the view keeps at any depth.

### 2026-08-21 09:04:43Z · review · session · session=ae7b649e-163f-45ba-8865-7879d35fb015

`review` ran as session `ae7b649e-163f-45ba-8865-7879d35fb015`
- replay: `claude --resume ae7b649e-163f-45ba-8865-7879d35fb015`
- log: `.project/logs/TICKET-023-review-ae7b649e.log`

### 2026-08-21 09:04:43Z · review · transition · to=holistic-review · result=ok

**review -> holistic-review** (result: `ok`)

✓ Reviewed commits 85f59c4 and a97e7b7: all 8 acceptance criteria hold, 188 passed, guard untouched; 3 non-blocking findings appended.

### 2026-08-21 09:20:00Z · holistic-review · note

The accumulated change is coherent. `result: ok`.

Scope. `git diff main...HEAD --stat` reports 9 files and
`193 insertions(+), 12 deletions(-)`, exactly the 9 files in
`files_declared`. Two commits: `85f59c4` (reproduction) and `a97e7b7`
(implementation).

The sum matches `## Plan`. Every editing step landed as written: steps 1-4 in
`pipeline/core/ticket.py`, step 6 in `tests/test_ticket.py`, steps 8-9 in
`pipeline/core/config.py`, step 10 in `pipeline/daemon/supervisor.py`, step 11
in `pipeline/harnesses/claude-code.toml`, step 12 in
`pipeline/stages/_common.md`, steps 13-14 in `tests/test_stages.py` and
`tests/test_harness.py`, step 16 in `CLAUDE.md`. Steps 5, 7, 15 and 17 are
commands, not edits. Nothing landed that no acceptance criterion asked for.

No later fix undid an earlier one.
`git diff 85f59c4 a97e7b7 -- tests/test_ticket.py` adds only
`test_the_stage_view_keeps_every_human_entry` and changes no line of the
reproduction. The implementation did not weaken the test that defines it.

The wiring is complete end to end, which no single diff shows. `spawn()`
builds the view, `compose_prompt()` appends it, and
`pipeline/harnesses/claude-code.toml` lines 81 and 97 read that file with
`--append-system-prompt "$(cat {stage_prompt})"`. Its `prompt_mode = "system"`
(line 15) selects that path. `codex.toml` is `prompt_mode = "inline"` and gets
the same text through `render()`. The view reaches a real agent on both
harnesses.

No stale instruction survived. Grep over the worktree for `Read the ticket`,
`Read {ticket}`, `ticket file completely` and `read the whole ticket` returns
two hits, both intended: `pipeline/stages/_common.md:22` (the new prohibition)
and `tests/test_harness.py:102` (the assertion that the old wording is gone).
No stage prompt under `pipeline/stages/` orders a whole-ticket read.

Error handling did not drift between iterations. The change adds exactly one
failure path: `except PipelineError: view = ""` in `spawn()`. It matches how
the rest of `supervisor.py` treats a ticket it cannot load.

I re-ran the suite: `uv run --group dev pytest -q tests` -> `188 passed in
8.62s`. I did not run the guard script. The guard is unchanged --
`git diff main...HEAD --stat` lists no file under `pipeline/hooks/` -- and the
review stage recorded its output.

I re-litigate none of the review stage's three non-blocking findings; they
stand as recorded.

### 2026-08-21 09:06:49Z · holistic-review · session · session=b4793688-82ec-4a2e-bfaf-c651674c275f

`holistic-review` ran as session `b4793688-82ec-4a2e-bfaf-c651674c275f`
- replay: `claude --resume b4793688-82ec-4a2e-bfaf-c651674c275f`
- log: `.project/logs/TICKET-023-holistic-review-b4793688.log`

### 2026-08-21 09:06:49Z · holistic-review · transition · to=verifying · result=ok

**holistic-review -> verifying** (result: `ok`)

✓ Coherent: 9 files as declared, every plan edit landed, no step undone, view wired to both harnesses; 188 passed

### 2026-08-21 09:06:58Z · verifying · transition · to=merging · result=ok

**verifying -> merging** (result: `ok`)

regression suite exit 0
```
...HEAD
ok  allow [always] cargo build --release
ok  BLOCK [readonly] sed -i s/a/b/ x.py
ok  BLOCK [readonly] echo hi > file.txt
ok  BLOCK [readonly] git commit -am wip
ok  BLOCK [readonly] cp a b
ok  BLOCK [readonly] pip install requests
ok  BLOCK [readonly] mv a b
ok  BLOCK [readonly] python3 -c "open('/tmp/x','a').write(1)"
ok  BLOCK [readonly] git -C . commit -am wip
ok  BLOCK [readonly] pytest 2>out
ok  BLOCK [readonly] pytest >> log.txt
ok  BLOCK [readonly] git worktree add /tmp/x main
ok  BLOCK [readonly] python3 setup.py install
ok  BLOCK [readonly] tee /tmp/x
ok  BLOCK [readonly] curl https://example.com -o /tmp/x
ok  BLOCK [readonly] make install
ok  BLOCK [readonly] cargo run
ok  BLOCK [readonly] npm install
ok  BLOCK [readonly] echo $(whoami)
ok  allow [readonly] pytest -x
ok  allow [readonly] git diff main...HEAD
ok  allow [readonly] grep -rn foo .
ok  allow [readonly] git log --oneline
ok  allow [readonly] cat thing.py
ok  allow [readonly] python3 -m pytest --deselect x
ok  allow [readonly] ls -la
ok  allow [readonly] git show HEAD
ok  allow [readonly] git blame thing.py
ok  allow [readonly] rg evict src/
ok  allow [readonly] pytest -x 2>&1
ok  allow [readonly] find . -name '*.py'
ok  allow [readonly] cargo test
ok  allow [readonly] go test ./...
ok  allow [readonly] git status --porcelain
ok  allow [readonly] wc -l thing.py
ok  allow [readonly] python3 -m unittest
ok  allow [readonly] git diff main...HEAD | head -50
ok  end-to-end exit codes

guard: all passed

```

### 2026-08-21 09:06:59Z · merging · transition · to=done · result=ok

**merging -> done** (result: `ok`)

merge exit 0
```
$ git merge --no-edit main || exit 1
head=$(git -C /home/chezzijr/proj/claude-setup rev-parse --abbrev-ref HEAD) || exit 1
[ "$head" = main ] || { echo "main checkout is parked on $head, not the base branch -- refusing to land"; exit 1; }
git -C /home/chezzijr/proj/claude-setup merge --ff-only ticket/023


Already up to date.
Updating 5c1483e..a97e7b7
Fast-forward
 CLAUDE.md                           |  7 ++++
 pipeline/core/config.py             | 12 +++++--
 pipeline/core/ticket.py             | 72 ++++++++++++++++++++++++++++++++++---
 pipeline/daemon/supervisor.py       | 12 +++++--
 pipeline/harnesses/claude-code.toml |  4 +--
 pipeline/stages/_common.md          | 11 ++++--
 tests/test_harness.py               | 22 ++++++++++++
 tests/test_stages.py                | 15 ++++++++
 tests/test_ticket.py                | 50 ++++++++++++++++++++++++++
 9 files changed, 193 insertions(+), 12 deletions(-)

```

### 2026-08-21 09:06:59Z · merging · decision

decision recorded as `DEC-023`
