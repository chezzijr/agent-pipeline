---
name: pipeline-config
description: Set up or fix this project's .project/pipeline.toml for the agent pipeline. Use when the pipeline was just installed here, when a stage or the Tier A gate runs the wrong test command, when the gate says a test "errored rather than failed" or "exited 0 -- it must fail before implementation", or when the user says "configure the pipeline", "set up pipeline.toml", "the pipeline can't run my tests", when a stage was killed at its budget cap, when builds interfere across ticket worktrees, or when the user asks which keys `.project/pipeline.toml` takes.
---

# Configuring `.project/pipeline.toml`

Three commands decide whether the pipeline works at all. Get them wrong and the
Tier A gate rejects good tickets with confusing findings.

**Do not guess the test runner.** Read `Cargo.toml`, `package.json`,
`pyproject.toml`, `go.mod`, the CI workflow — then run the bare suite once
yourself before you write anything.

## What `{test}` is

`test_file` holds one test, `<path>::<name>` (e.g.
`tests/repro.rs::test_add_is_wrong`), or a list of them, for a bug that needs
more than one failing test to reproduce. `{test}`, `{path}` and `{name}` are
substituted with a regex, not `str.format`, after `shlex.quote`. For a single
test each is a bare value. For a list, a bare placeholder is every value
space-joined; `{test:<prefix>}` repeats `<prefix>` before each value, which is
the only way a flag that takes one value at a time (like pytest's
`--deselect`) can exclude more than one test in a single run; `{test:}` is the
space-joined form written out, for a runner that takes several values after
one flag.

Your three commands must satisfy exactly this:

| Key | Must do | Gate checks |
|---|---|---|
| `test_one` | run **only** that one test, once per listed test | exits non-zero **and** `the name` appears in the output; exits non-zero when the selector matches NO test |
| `test_suite` | run everything | `verifying` passes only on exit 0 |
| `test_suite_without_new` | run everything **except** every listed test, in one run | non-zero **and** a reported test result means pre-existing breakage |

Three traps behind that table:

- `<path>` must be a real file. The gate copies it onto a checkout of `base`
  and re-runs `test_one` there, to prove the bug is not already fixed upstream.
- `<name>` must reach the output. A compile error or a missing dependency also
  exits non-zero, and without the name check it reads as a successful
  reproduction.
- A selector that matches **no** test must still exit non-zero. A runner that
  treats the selector as a filter may exit 0 and print `0 filtered out`, and
  the gate would read that as `the reproduction PASSES`. Wrap the runner when
  it cannot -- a `run-test.sh` that prints `FILTER MATCHED NO TEST -- refusing
  to report success` and exits 1. `pipeline register` probes exactly this and
  refuses a config that fails it.
- `test_suite_without_new` exiting non-zero is not enough on its own: the gate
  also needs evidence a test actually ran. It accepts exit 1 or 101, or output
  containing `3 failed`, `Ran 7 tests`, `test result:`, or a line starting
  `FAIL`. A runner that exits otherwise on failure and prints none of those
  must be wrapped, the same way the selector trap above is.

`{test}` is the whole `<path>::<name>` value; `{path}` and `{name}` are its
two halves. All three are `shlex.quote`d and substituted; every other brace
reaches the shell unchanged.

```toml
# cargo
test_one               = "cargo test {name}"
test_suite             = "cargo test"
test_suite_without_new = "cargo test -- --skip {name}"
```

`--skip` takes one value at a time, so a two-test ticket needs
`cargo test -- {name:--skip }` instead.

## Prove it before you claim it works

Pick a test that already exists and currently **fails** (write a throwaway
failing one if none does), then run the real substitution — same `shlex.quote`
and `.format` the gate uses:

```sh
python3 - <<'PY'
import re, shlex, subprocess, tomllib, pathlib
cfg = tomllib.loads(pathlib.Path(".project/pipeline.toml").read_text())
tests = ["tests/repro.rs::test_add_is_wrong"]     # <- your real failing test(s)
RE = re.compile(r"\{(test|path|name)(?::([^{}]*))?\}")
def fill(template, ts):
    def sub(m):
        parts = [{"test": t, "path": t.split("::")[0], "name": t.split("::")[-1]}[m.group(1)] for t in ts]
        return " ".join((m.group(2) or "") + shlex.quote(v) for v in dict.fromkeys(parts))
    return RE.sub(sub, template)
def run(c):
    p = subprocess.run(c, shell=True, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr
for t in tests:                                   # test_one: one run per test
    rc, out = run(fill(cfg["test_one"], [t]))
    print("test_one", t, "| rc =", rc, "| name in output =", t.split("::")[-1] in out)
for k in ("test_suite", "test_suite_without_new"):        # one run, all tests
    rc, out = run(fill(cfg[k], tests))
    print(k, "| rc =", rc, "| names in output =", [t.split("::")[-1] in out for t in tests])
PY
```

This regex and its `sub` mirror `format_tests_cmd()` in
`pipeline/core/config.py` and must be kept in step with it.

Expect, with a red test: every `test_one` run non-zero **and** its own name in
output; `test_suite` non-zero; `test_suite_without_new` **zero** and printing
none of the names. Anything else is a broken config, not a broken pipeline.
Show the operator this output. Then run `test_one` once more with a name no
test has: it must be non-zero there too.

## Then commit it

The dispatcher reads this file from **git HEAD**
(`git show HEAD:./.project/pipeline.toml`), so an uncommitted edit is inert.
This is deliberate: it stops a stage rewriting the commands the gate trusts.
If `.project/` is git-ignored here (`pipeline init --private`) there is
nothing to commit. The dispatcher pinned a copy outside the repo on first
read, under `~/.config/pipeline/pinned/<hash of the project path>/`, and
every later edit stays inert until you run `pipeline config --sync`.
`pipeline config` prints `source:  pinned` and warns when the working tree
differs from the pin. Say both to the operator.

`base` must name the branch tickets are cut from, and the main checkout must be
parked on it while the dispatcher runs, or `merging` refuses to land.

## Every other key

`test_one`, `test_suite`, `test_suite_without_new` and `base` are the
only keys this file needs. The rest are optional. These five are the
ones an operator reaches for, and the file's own comments do not carry
them all.

### `[stages.<name>] max_usd` -- the per-stage dollar cap

Every stage spawns under a dollar cap. A stage killed at it escalates
the ticket naming the cap, and nothing retries into the same spend.
That is the lever for "the stage ran out of budget":

```toml
[stages.planning]
max_usd = 10
```

Then `pipeline resume TICKET-066 --stage planning --reset budget_kills`.
Defaults come from the stage's own file: `quick-review` 2, `triage` 3,
`plan-validation` 3, `review` 4, `holistic-review` 4, `planning` 5,
`implementing` 8. A `max_usd` here PINS the cap -- see `scale_usd`.
Only `[stages.<name>] max_usd` is read; a top-level one is ignored.

### `[stages.<name>] scale_usd` -- opt in to size-scaled caps

`review`, `quick-review` and `holistic-review` grow their cap by one
dollar per 4 declared files or per 8 plan steps, whichever is larger,
capped at twice the stage's own number. Your `max_usd` pins the cap and
is never scaled past unless you also set `scale_usd = true`;
`scale_usd = false` turns scaling off for a stage that scales by
default.

```toml
[stages.review]
max_usd   = 6      # 6 flat; with the next line, 6 to 12 by plan size
scale_usd = true
```

### `worktree_setup` -- one command per new checkout

Top level, under no table. It runs in every worktree the dispatcher
creates, after `git worktree add` and before the first stage, and in
the throwaway checkout of `base` the gate re-runs `test_one` in. Copy
an env file, install dependencies, key a build cache:

```toml
worktree_setup = "cp ../../.env . && npm ci --prefer-offline"
```

**Key any build cache per checkout.** Every ticket gets its own
worktree. `ln -s ~/.cache/cargo-target target` points them all at one
directory, and one ticket's stale artifact is then served into
another's build: a test goes red for a reason that is not in that
ticket's diff, and clears only when the source is touched. Use
`CARGO_TARGET_DIR=~/.cache/cargo/$(basename $PWD)`, a `ccache` prefix
per branch, or leave the cache unshared.

### `.project/stages/<name>.extra.md` -- prose for one stage

A file, not a key. Its text is appended after the packaged stage prompt
and before the ticket view, so it adds instructions and can never relax
one: there is no frontmatter in it to override a setting with. Settings
go in `[stages.<name>]`; wording goes here.

```sh
mkdir -p .project/stages
echo 'Run `make lint` before every commit.' > .project/stages/implementing.extra.md
git add .project/stages/implementing.extra.md   # read from HEAD, like the config
```

`.project/stages/` is fenced, so a committed change parks the ticket at
`awaiting-merge` for a human to read.

### Still in the file's own comments

The other `[stages.<name>]` keys (`model`, `effort`, `write`, `tools`,
`hooks`, `permission_mode`, `skills`), `[mcp.<name>]`,
`[readonly] allow` and `max_parallel` are documented in the comments of
`.project/pipeline.toml` itself. Read them there rather than inventing
keys -- an unknown key is silently ignored.
