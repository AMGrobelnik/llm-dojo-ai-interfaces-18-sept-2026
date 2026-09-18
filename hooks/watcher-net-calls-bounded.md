# Every network-reaching command in a watcher script carries a numeric `timeout`

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 1s | active |

## Why

An unbounded tags fetch in `aii-image-watcher.sh`'s `handle_tags` hung the
watcher for the whole of the GitHub reachability windows on 2026-08-03 and
2026-08-05 — multi-hour, and silent, because a poll loop blocked inside one
syscall writes no log line. The bounded main-branch fetches beside it "logged
and moved on precisely because they carry a timeout", which is still the
script's own comment on the fix; `imagetools` got its bound for the same
stated reason, that a registry stall would wedge the poll loop indefinitely.

The convention then regressed where conventions do — at the next call site
added. `aii-site-watcher.sh` shipped three unbounded calls and they stayed
until `efb800726` and `d1bafb661` bounded them. Two were fetches; the third
was `git push`, which the rule's own proposed grep could not see at all,
because its verb list did not carry `push`. So the failure is not only "a
call was added without a bound" but "the detector did not cover the verb",
and both are what this hook is built against.

The heavier alternative — an external watchdog — half-exists as
`SUITE_DEADLINE_SECS` and `TimeoutStopSec`, and neither can unwedge a loop
blocked in a syscall. A per-call bound is the mechanism the incidents forced.

This hook is in the `research-monorepo` set: the watcher directory, its four
scripts and the deploy verbs they call are this repo's.

## Mechanism

`check.py` tokenises each watcher into SIMPLE COMMANDS rather than grepping
lines. A logical line joins `\` continuations, then splits on `;`, `&&`,
`||`, `|` and `&`, with `$( … )` substitutions extracted first and leading
keywords (`if`, `while`, `!`, `{`) stripped. Each command's head is resolved
by basename, so `/usr/bin/curl` counts. A head in the verb table is a network
call site; `git`, `docker`, `gh`, `uv`, `bun`, `npm` and `pip` additionally
need an allowed subcommand, found by an OPTION WALK — `git -C "$REPO" fetch`
resolves to `fetch`, so a new global flag can neither blind the check nor
redden `git -C "$REPO" log`.

A site is bounded when `timeout N`, `timeout "$VAR"` or a discovered bounded
wrapper appears anywhere in that same simple command. Wrappers are found by a
brace-matched scan for a function whose body applies `timeout` to `"$@"`
(`run_in` in `aii-ci-watcher.sh`). That scan spans the whole watcher
directory even in per-file mode, because a helper one script defines could be
used by a sibling; scanning only the staged file would read a bounded call as
unbounded.

| failure mode | mechanism |
|---|---|
| a new unbounded call site | a bound per simple command |
| a verb the old grep missed | head -> subcommand table |
| a call inside `$( … )` | substitutions split out first |
| `timeout` with no bound | reported as its own finding |
| a bounded in-script wrapper | wrappers found by body scan |
| the population collapses | floors -> `cannot run:` |

Content comes from the index (`git ls-files -s` plus one `git cat-file
--batch`), never the working tree, so another agent's unstaged edit in the
shared checkout cannot change the verdict. A path argument that is not in the
index is read from disk, which is the case of a new watcher checked by hand
before it is staged. The repo root comes from `git rev-parse --show-toplevel`.

Every knob — the watcher directory, the verb table, the two floors — is in
the `CONFIG` dict at the top of `check.py`.

## Stock

**Zero findings** against `/home/<user>/projects/research-monorepo` at HEAD
`3f1060fa7499`. Population: 4 tracked scripts, 20 discovered call sites
(`aii-builder-keepalive.sh` 2, `aii-ci-watcher.sh` 11,
`aii-image-watcher.sh` 7, `aii-redeploy-watchdog.sh` 0), one discovered
bounded wrapper (`run_in`). Both whole-tree floors clear with margin.

Whole-tree runtime 0.09 s (median of three: 0.10 / 0.09 / 0.09); per-file, as
lefthook runs it, 0.06 s. Budget is set to 1s, the floor.

The checker was verified against the regression the rule was written after,
not only against a clean tree: `aii-site-watcher.sh` as it stood at
`efb800726^` produces exactly three findings — `:99` fetch, `:116` push,
`:126` fetch — and the same file with the three `timeout` wrappers the
bounding commits added exits 0. Both fixtures are embedded in the bites test,
so that evidence does not depend on the consumer repo being present.

Re-measured after the consumer moved on, at HEAD `eaf82761cddc` (2026-09-08), in one sequential pass over all eleven hooks of this
integration: **0 findings**, whole-tree 0.03 s. The figures above are
from the earlier HEAD and are unchanged by the move.

## Fragility

| refactor | effect | guard |
|---|---|---|
| watcher dir renamed | population gone | `skipped:` |
| scripts rewritten | under 3 scripts | exit 2 |
| calls move to a lib | under 10 sites | exit 2 |
| a new verb appears | site unseen | none — edit CONFIG |

The `skipped:` row is deliberate: the hook set is vendored into repos with no
watcher directory at all, and that is an environment the check cannot run in
rather than a collapse. A directory that still exists but has lost its
scripts is a collapse, and exits 2.

## Residue

The old rule asked an agent to judge things the program does not:

- a verb reached through a variable (`$CMD fetch`), or a network call made by
  a program the watcher `exec`s or interprets;
- whether a numeric bound is a sensible one. `timeout 999999` passes; the
  choice of 60 s for a fetch against 7200 for a push stays a review call;
- whether the bound is on the right layer when both `flock -w` and `timeout`
  wrap a bake — the check only requires that the `timeout` is present;
- keeping the installed copy under `~/.local/bin` in step, which is the
  separate `watchers-installed-and-current` group's job.
