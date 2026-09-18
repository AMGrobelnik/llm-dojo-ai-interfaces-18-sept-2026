<!-- hook: pip-audit-py -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 5s | active |
# The resolved Python dependency set carries no known vulnerability that is not an allowlisted ID

`pip-audit` over `uv export`'s rendering of `uv.lock` — every package and
version this repo actually resolves, across every workspace member and every
extra. Triggered by `uv.lock` and `pyproject.toml`, because those are the only
files that can change the answer.

## What is audited, and the trap

**The lock, never the invoking interpreter.** A bare `pip-audit` with no
argument audits the environment it is running in. Under `uv tool install` that
is pip-audit's own private venv — three packages, none of them this repo's —
so it reports clean forever and says nothing about it. That is exactly how an
audit step passes for a year while auditing nothing, so the export is
explicit and there is no argument-less path through `check.sh`.

`--no-deps` goes with it: the export is already a complete resolution, and
letting pip-audit re-resolve it would both cost a network round trip per
package and audit versions this repo never installs.

`--no-hashes` on the export, because pip-audit refuses a partially hashed
requirements file and a `git+` dependency cannot carry a hash at all; the
`git+` lines are then dropped, which costs nothing — an advisory database
keyed on (name, version) has nothing to say about a commit sha.

## The allowlist

`PIP_AUDIT_IGNORE` names a file of `ID  # reason` lines, one per known
advisory with no fixed release. Everything else blocks, so a NEW finding still
fails the gate while a tracked one does not — which is the whole difference
between an allowlist and turning the check off. research-monorepo's is
`aii_public/pip-audit-ignore.txt`, today one line:

| ID | package | reason |
|---|---|---|
| PYSEC-2026-2858 | paramiko 4.0.0 | no fixed release published; reachable only from the operator-driven RunPod SSH path, never from user input |

An entry is removed the moment a fix ships — the allowlist is part of the
cache key, so editing it re-audits immediately.

## Cache, and the timings

Keyed on a sha256 of `uv.lock` plus the allowlist, under
`<git-common-dir>/amg-hooks/cache/pip-audit-py/` of the REAL checkout —
resolved from `AMG_HOOKS_WORKTREE`, not from the cwd, for the reason
react-compiler-fe's README sets out at length: this hook can run inside the
whole-index snapshot, which carries a `.git` of its own, and a cache resolved
from there is reaped at post-commit and never hit again. Sibling worktrees
share one warm cache.

Measured 2026-09-16 against research-monorepo (589 resolved packages, aarch64):

| run | wall |
|---|---|
| unchanged lock (cache hit) | **0.21 s** |
| lock changed, pip-audit's own HTTP cache warm | 6.0 s |
| lock changed, everything cold | 51.4 s |

Only the first number is paid on an ordinary commit — `uv.lock` has to be
staged for the hook to run at all, and then the lock has to differ from the
last audited one. The 51.4 s cold case is over the 30 s cap and is recorded
rather than hidden: it is a first-ever run on a machine, and the alternative
(no audit) is worse. If it becomes routine, audit only the (name, version)
pairs that differ from the last audited lock.

The advisory database is deliberately NOT in the cache key. It moves under us
continuously, and keying on it would mean a full re-audit several times a day
for a result that has not changed. A vulnerability published against a lock
that is already committed is caught by the next lock change, or by a `weekly`
CI run of the same command — not by this gate.

## Offline

A vulnerability service that cannot be reached is not a finding. `check.sh`
matches the connection-shaped failures, warns, and exits 0: a gate that blocks
every commit whenever the network is down is a gate nobody keeps. Nothing is
skipped, only deferred — the lock is unchanged by the failure, so the next
commit on a reachable network audits the same content and blocks then.
Deliberately not exit 2 (`cannot run`), which under this repo's contract
blocks; the trade is written down here rather than hidden in an exit code.

Fix when blocked: `uv lock --upgrade-package <name>` to a fixed release. If
there is no fixed release, add the ID and the reason to the allowlist.

Delete-check: tool-enforced, cannot delete. A transitive CVE arrives without a
diff anyone here writes, so nothing else in the gate can see it.
