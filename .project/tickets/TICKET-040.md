---
id: TICKET-040
stage: rejected
class: feature
branch: ticket/040
test_file: null
files_declared: []
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
  stage: triage
  id: af211217-1f8a-4402-9b0d-45234fc583e1
  log: .project/logs/TICKET-040-triage-af211217.log
---

## Summary

a finished ticket can only be merged to base, never opened as a pull request

`merge_cmd()` (`pipeline/daemon/supervisor.py:486`) merges base into the ticket
branch and then fast-forwards the main checkout onto it. That is the only way a
ticket can land. On a shared repository the base branch is protected and work
arrives by pull request, so the pipeline cannot be used there at all: every
ticket that reaches `merging` either rewrites a branch nobody is allowed to
rewrite, or fails.

    $ git config branch.main.protected   # a shared repo
    $ pipeline ls
    TICKET-041   escalated     # merging failed; the work is done and stranded

Expected: `merge_mode = "pr"` in `.project/pipeline.toml` (`"merge"` stays the
default, so nothing changes for a solo project). In PR mode `merging` keeps the
`git merge --no-edit <base>` step -- it is what proves the branch is mergeable
-- then pushes the ticket branch and runs `gh pr create`. It fails closed with
no extra work: a missing `gh`, no remote, or a rejected push exits non-zero, and
`transition("merging", "fail")` escalates with the conflicted worktree intact.
The `[ "$head" = <base> ]` refusal is specific to the fast-forward and should
not run in PR mode.

Two consequences to settle in the plan, not to discover later. First,
`commit_record()` (`supervisor.py:445`) commits the ticket and
`.project/decisions/` onto base in the main checkout; in PR mode those records
must ride the branch instead, or the decision records that stop `planning`
re-deciding settled questions never reach anyone else's clone. The recorded
frontmatter will say `stage: merging`, because `done` is not reached until the
command returns -- that is accepted and should be documented, not worked around.
Second, `done` starts meaning "PR opened" rather than "landed"; record the PR
URL in `## Thread`.

The failure a test should show is `merge_cmd()` rendering a `git merge --ff-only`
command where `merge_mode = "pr"` requires a `gh pr create`.

## Reproduction

## Digest

## Decisions checked

## Plan

## Acceptance criteria

## Decisions

## Rollback

## Thread

### 2026-08-23 14:21:54Z · new · transition · to=triage · result=new

**new -> triage** (result: `new`)

dispatcher pickup

### 2026-08-23 14:39:00Z · triage · triage · result=rejected

**triage** (result: `rejected`)

Stopped without reproducing. `lease.holder` in this ticket's own frontmatter
is `triage-132297`, a live `pipeline run` process (PID 132297) already
running triage on this exact ticket and worktree while I ran too. Every edit
I made to `tests/test_dispatch.py` (a new test calling `merge_cmd()` with
`merge_mode: "pr"` and asserting `"gh pr create" in cmd`) reverted to `HEAD`
within seconds -- confirmed twice, `git status` came back clean both times
right after a successful `Edit`. That worktree is not safely mine to write
while another live instance holds the lease on it.

Confirmed before stopping: `merge_mode` does not appear anywhere in
`pipeline/`, `tests/`, or `.project/pipeline.toml` (`grep -rn "merge_mode"`
returned nothing outside this ticket's own text), and `merge_cmd()`
(`pipeline/daemon/supervisor.py:486`) unconditionally renders
`git merge --ff-only`. The ticket's premise is accurate; I could not leave a
committed reproduction because of the concurrent-lease conflict, not because
the bug is unreal.

Rerun triage once the concurrent `pipeline run` (PID 132297) has released the
lease or finished its own attempt on this ticket.

### 2026-08-23 14:40:02Z · triage · session · session=af211217-1f8a-4402-9b0d-45234fc583e1

`triage` ran as session `af211217-1f8a-4402-9b0d-45234fc583e1`
- replay: `claude --resume af211217-1f8a-4402-9b0d-45234fc583e1`
- log: `.project/logs/TICKET-040-triage-af211217.log`

### 2026-08-23 14:40:02Z · triage · transition · to=rejected · result=rejected · marker=yes

**triage -> rejected** (result: `rejected`)

✓ Could not commit a reproduction: a live pipeline run (lease.holder triage-132297) already held this ticket's worktree and reverted every edit to tests/test_dispatch.py within seconds; ticket's premise (merge_cmd always renders --ff-only, no merge_mode anywhere in the code) is otherwise confirmed.
