<!-- hook: shellcheck -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every tracked shell script passes shellcheck (warning severity, project-wide)

Native `shellcheck` binary instead of uvx-wrapped shellcheck-py — kills
~10s cold-start. Install once: download the static binary from
https://github.com/koalaman/shellcheck/releases
(`shellcheck-vX.X.X.linux.x86_64.tar.xz`) and place on PATH.
`--severity=warning` keeps info-level noise (SC2015, SC2086) out of the
output.

`-x -o check-unassigned-uppercase`: follow `source`d files (the runpod
scripts carry `# shellcheck source=` path hints — the check runs from the
repo root) and flag reads of never-assigned UPPERCASE vars — the
silent-misspelling class that plain severity filtering can't see. The
directive is a path hint, not a suppression — shellcheck verifies the
assignments in the sourced file. (Example: a misspelled PROJECT_ROOT
read.)

Project-wide: every run re-scans every tracked `.sh`/`.bash` so a stale
shellcheck issue anywhere blocks the next commit. Whole-repo scan is
~2.3 s (93 scripts once this rule's own check.sh is counted, re-measured
2026-09-06).

`check.sh` materializes those scripts from the INDEX into a scratch tree
(`git checkout-index --prefix`) and runs shellcheck there, rather than over
the working copy. A whole-tree gate that reads disk judges whatever a
concurrent agent has half-written: on 2026-09-05 a peer's unstaged file
failed two unrelated commits in this family of rules. The index is the tree
under judgment in both commit lanes — `git commit --only` points
`GIT_INDEX_FILE` at a temporary index of HEAD plus the named paths, a plain
commit's `.git/index` is what lands — and in `RULES_MODE=all` the sweep runs
on a checked-out commit, where the two agree. `--prefix` keeps the relative
paths, so the `# shellcheck source=scripts/runpod/*.sh` hints still resolve
under `-x` (those files are `.sh` and so are in the scratch tree) and every
reported path reads exactly as before.

Fix when blocked: apply the modern best-practice fix to the flagged code
smell — quote the expansion, assign the variable, fix the sourced path —
never a blanket `# shellcheck disable` for a real issue.

Delete-check: tool-enforced, cannot delete — shell has no compiler, so
shellcheck is the only pre-runtime defect gate the language gets.
