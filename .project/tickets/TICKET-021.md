---
id: TICKET-021
stage: triage
class: feature
branch: ticket/021
test_file: null
files_declared: []
counters:
  plan_validation_attempts: 0
  review_loops: 0
  blocked_count: 0
  lease_expiries: 0
lease:
  holder: null
  expires: null
---

## Summary

typing into an attached stage suspends the whole app to read one line

`action_send` (`pipeline/tui/app.py:422`) is the only way to send a keystroke to an
interactive stage. It suspends the Textual app, prints a shell prompt, and blocks on
`input()`:

    send to terminal (empty = just Enter): _

The TUI is gone while that prompt is up -- no tree, no PTY pane, no way to see what
you are answering. Answering one approval prompt on a running stage looked like this
in practice (2026-08-21, three stages parked at once):

    ↓↑            moves the ticket cursor, never reaches the terminal
    i             app disappears, shell prompt appears
    1 <Enter>     lands in the pty, app repaints, agent continues
                  ... and the next Bash command asks again

The docstring is honest about why -- "capturing every keystroke would mean giving up
the keybindings this app is" -- but the result is that the one feature the PTY exists
for is unusable, and a stage that needs steering is easier to kill and rerun.

Expected: a raw mode. A key (`i` is the natural one) hands every subsequent keystroke
to the attached PTY -- arrows, Tab, Ctrl-C, shift+Tab -- until an escape sequence
(`Esc Esc`) returns to the tree, with the mode visible in the footer. The keybindings
stay exactly as they are outside raw mode.

The protocol needs nothing new: `_op_input` (`daemon/server.py:580`) already takes
base64 keystrokes, ≤4096 bytes per op, writer-only. This is a client-side change.

Related: TICKET-019 fixes the pane size, and it edits the same file, so the two will
serialize on `files_conflict` rather than run together. Raw mode into a 40x120 box
inside a wide pane is still a usability problem, so 019 landing first is the better
order but not a hard dependency.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread

### 2026-08-21 04:29:43Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup
