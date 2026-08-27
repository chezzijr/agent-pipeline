---
id: TICKET-067
stage: new
class: feature
branch: ticket/067
test_file: null
files_declared: []
counters: {plan_validation_attempts: 0, review_loops: 0, blocked_count: 0, lease_expiries: 0}
lease: {holder: null, expires: null}
---

## Summary

the test commands get {test} but not its {path} and {name} parts

The three commands in `.project/pipeline.toml` are formatted with one
placeholder: `cfg["test_one"].format(test=shlex.quote(test))`, where `test` is
the whole `<path>::<name>` value. The gate itself has already split it --
`test.split("::")[0]` for the file check and the base-checkout copy,
`test.split("::")[-1]` for the name-in-output check -- and then hands the
project the unsplit string back.

Every project whose runner selects by name, or by a target derived from the
path, therefore re-implements that split in shell:

    test_one = "cargo test \"$(echo {test} | sed 's/.*:://')\""

and a project whose runners differ by path writes a dispatcher script instead.
Two traps make that worse than it looks: `str.format` raises
`KeyError: 't##*'` on a literal `${t##*::}`, so the obvious shell idiom is
unavailable; and a command that silently selects nothing exits 0 (TICKET-064).

Expected: `test_one`, `test_suite` and `test_suite_without_new` can name
`{path}` and `{name}` as well as `{test}`, quoted the same way, so a project
writes its selector without parsing. A config using only `{test}` keeps
working unchanged -- `str.format` with unused keywords is a no-op.

A project whose targets genuinely differ by path still needs its own script;
the point is that the script stops re-deriving what the gate computed.
`.project/pipeline.toml` in this repo uses `{test}` and must keep passing.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread
