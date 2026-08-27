---
name: pipeline-config
description: Set up or fix this project's .project/pipeline.toml for the agent pipeline. Use when the pipeline was just installed here, when a stage or the Tier A gate runs the wrong test command, when the gate says a test "errored rather than failed" or "exited 0 -- it must fail before implementation", or when the user says "configure the pipeline", "set up pipeline.toml", "the pipeline can't run my tests".
---

# Configuring `.project/pipeline.toml`

Three commands decide whether the pipeline works at all. Get them wrong and the
Tier A gate rejects good tickets with confusing findings.

**Do not guess the test runner.** Read `Cargo.toml`, `package.json`,
`pyproject.toml`, `go.mod`, the CI workflow — then run the bare suite once
yourself before you write anything.

## What `{test}` is

It is the ticket's whole `test_file` value: `<path>::<name>`, e.g.
`tests/repro.rs::test_add_is_wrong`. The gate substitutes it with
`str.format` after `shlex.quote`.

Your three commands must satisfy exactly this:

| Key | Must do | Gate checks |
|---|---|---|
| `test_one` | run **only** that one test | exits non-zero **and** `<name>` appears in the output |
| `test_suite` | run everything | `verifying` passes only on exit 0 |
| `test_suite_without_new` | run everything **except** that test | red here means pre-existing breakage |

Two traps behind that table:

- `<path>` must be a real file. The gate copies it onto a checkout of `base`
  and re-runs `test_one` there, to prove the bug is not already fixed upstream.
- `<name>` must reach the output. A compile error or a missing dependency also
  exits non-zero, and without the name check it reads as a successful
  reproduction.

**Never write a literal `{` or `}` in a command.** `str.format` raises
`KeyError: 't##*'` on `${t##*::}`. Use `$(...)`:

```toml
# cargo
test_one               = "cargo test \"$(echo {test} | sed 's/.*:://')\""
test_suite             = "cargo test"
test_suite_without_new = "cargo test -- --skip \"$(echo {test} | sed 's/.*:://')\""
```

A runner whose selector is the file (`pytest`, `jest <path>`) can drop the
`sed` and pass `{test}` straight through.

## Prove it before you claim it works

Pick a test that already exists and currently **fails** (write a throwaway
failing one if none does), then run the real substitution — same `shlex.quote`
and `.format` the gate uses:

```sh
python3 - <<'PY'
import shlex, subprocess, tomllib, pathlib
cfg = tomllib.loads(pathlib.Path(".project/pipeline.toml").read_text())
test = "tests/repro.rs::test_add_is_wrong"          # <- a real failing test here
name = test.split("::")[-1]
for k in ("test_one", "test_suite", "test_suite_without_new"):
    c = cfg[k].format(test=shlex.quote(test))
    p = subprocess.run(c, shell=True, capture_output=True, text=True)
    out = p.stdout + p.stderr
    print(k, "| rc =", p.returncode, "| name in output =", name in out)
PY
```

Expect, with a red test: `test_one` non-zero **and** name in output;
`test_suite` non-zero; `test_suite_without_new` **zero**. Anything else is a
broken config, not a broken pipeline. Show the operator this output.

## Then commit it

The dispatcher reads this file from **git HEAD**
(`git show HEAD:./.project/pipeline.toml`), so an uncommitted edit is inert.
This is deliberate: it stops a stage rewriting the commands the gate trusts.

`base` must name the branch tickets are cut from, and the main checkout must be
parked on it while the dispatcher runs, or `merging` refuses to land.

## The rest of the file

`[stages.<name>]`, `[mcp.<name>]` and `[readonly] allow` are documented in the
comments of `.project/pipeline.toml` itself. Read them there rather than
inventing keys — an unknown key is silently ignored.
