<!-- hook: shell-strict-mode -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_MODE, RULES_STAGED
# A shell script declares some `set -` strictness mode in its first ten lines

Re-measured 2026-08-26: **70 of 70** tracked scripts declare a strictness
mode within their first ten lines, which is what this check enforces —
and **37** use one of the two house modes (`set -euo pipefail` for short
tools, `set -uo pipefail` for long-running loops that must survive a
failing step). The other 33 take the weaker bare `set -u` or `set -eu`,
so tightening the check to the two house modes would flag those 33. The
stock is clean against the check as written, so the first violation is
the regression. Per-mode counts are in the Stock table below.

The body used to read "17 of 19 .. the two stragglers are where
unset-variable bugs hide silently", which was both a narrower population
and long out of date: 14 scripts were brought into line that day, each
after a per-script audit of every expansion (see the commits naming
`aii-image-watcher`, `release-tag-guard` and the pod-boot family). Two
findings from those audits are worth keeping, because they are the
reasons a mode cannot be applied mechanically: `release-tag-guard.sh`
runs under dash via lefthook's `runner: sh`, where `set -o pipefail` is
an illegal option that aborts the hook, so it takes `set -eu`; and the
pod-boot scripts already ran under the inherited mode of the entrypoints
that source them, so "adding" it there mostly codified the status quo.

This check requires any staged `.sh` file to contain a `set -` line within
its first 10 lines. Which mode is a judgment the script's comments should
defend; that a mode was chosen is mechanical.

**Exemption: files meant to be `source`d into an interactive shell.** An
rc/alias file (e.g. `claude-alias.sh`) has no exit code of its own to trip
and must not impose `set -e`/`set -u` on the caller's interactive shell, so
it is skipped rather than made to declare a mode. A file is exempt when
either holds:
- its name matches `*alias*.sh`, `*rc.sh`, or `*.rc`; or
- its first 10 lines carry `# sourced`, or carry `# shellcheck shell=bash`
  with no `#!` shebang on line 1 (a sourced file has no shebang of its own).

**Ten CODE lines, read from the INDEX** (2026-09-14). Both halves were
wrong before, and both silently. The population came from git
(`RULES_STAGED`) while the content came from disk (`head -10 "$f"`), so a
path joined the list because it was STAGED and was then judged by bytes
that were not — this checkout is shared, so another agent's unsaved edit
decided the verdict, in either direction. Worse, the `[ -f "$f" ]` guard
SKIPPED a path staged with content but since deleted from disk: a green
for a file the commit adds. `git cat-file blob :<path>` reads what the
commit will hold. And `head -10` counted raw lines, so a header comment
spent the window — a script that explains why it takes the mode it takes,
which is what this repo asks for everywhere else, pushed its own
declaration out of view and was reported as having none. Blanks,
comment-only lines and the shebang no longer count against the ten. That
is strictly more permissive and never less (a declaration inside the first
ten raw lines is inside the first ten code lines too), so no tree that
passed can start failing; a mode arriving after ten lines of real code is
still a finding, which is what keeps the widening from being a deletion.
The one-line statement in `general/lefthook.yml` still says "first ten
lines" and wants the same word — that file has a single writer.

Fix when blocked: add `set -u` (and `-e -o pipefail` unless a failing step
must not kill the script — say so in a comment when omitting `-e`).

Delete-check: cannot delete — shell has no safe default; the dimension is
only closeable by declaration.

Stock (2026-08-22, whole tree): the backlog is worked — all 62 tracked
`.sh` files now carry a first-10-lines declaration, including the four
once named here (shared_init.sh, release-tag-guard, install-hook-tools,
dep_audit); previously 6+ lacked one.
RE-MEASURED 2026-08-26 — **holds; 70 of 70 now.**

| mode | 08-22 | 08-24 | 08-26 |
|---|---|---|---|
| `set -u` | 31 | 31 | **32** |
| `set -euo pipefail` | 21 | 21 | **24** |
| `set -uo pipefail` | 9 | 10 | **13** |
| `set -eu` | 1 | 1 | 1 |
| no mode declared | 0 | 0 | **0** |

Eight scripts have been added since the first measurement: seven took a
house mode and one took the bare `set -u`. So the drift is growth, not
decay — the house-mode share went 30/62 to 37/70 while the count lacking
any declaration stayed at zero. That last row is the one this check actually enforces; the rest
is stock the check does not yet require. The lone `set -eu` is still
`.lefthook/pre-push/release-tag-guard.sh`, and the reason still holds:
`lefthook.yml:140` runs it with `runner: sh`, where `set -o pipefail` is
an illegal option that aborts the hook.

**Method note for whoever mechanises this.** Classifying by searching the
first ten lines for the mode STRING gets the wrong answer, and this rule
is the worst case for it. `release-tag-guard.sh` opens with a comment
explaining its choice — "``set -eu``, not the house ``set -euo
pipefail``" — so a text search finds BOTH modes in a comment, two lines
before the real directive. Three passes were needed here: the first was
fooled by that comment, the second used a regex that rejected
`set -euo pipefail` (the flags are followed by a bare `pipefail`, not
`-o pipefail`) and reported 31 scripts as undeclared. Skip comment lines,
and anchor on a line that is ONLY a `set` directive.
