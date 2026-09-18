<!-- hook: shell-exit-capture-adjacent -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:engine-git
# `=$?` captures the status of the immediately preceding command — never the first line after fi, done, or a closing brace

Incident 1e3a65b29 'fix(keepalive): report the bake's real exit code, not the
if's' — an `rc=$?` placed after `fi` read the if-statement's status, so a
failed bake reported success, the exact silent-success shape of defect class 7
(also ded281229, 3429ca006). shellcheck does not catch this placement (SC2181
covers comparing $? in a condition, not stale capture-into-variable). Scanned
all 17 first-party .sh files today with the predecessor-line check: 0 live
instances — the tree is clean and the rule pins the end-state so the keepalive
incident cannot recur.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: cross-cutting)

Mechanism (implemented 2026-08-26, `scripts/check_exit_capture.py`):

    .venv/bin/python $RULE_DIR/scripts/check_exit_capture.py

Scans every tracked `.sh`, not the four directories the proposal named. That
scope said 17 files; the tree has **69**, because most first-party shell now
lives under `.claude/skills/`. Re-measured: 20 standalone captures, 0 whose
predecessor closes a block — the tree is clean and this pins it.

Three distinctions the mechanism has to make, each verified by probe:

- **`else` is not a block end.** Inside an `else`, `$?` is still the failed
  condition's status — which is exactly what the keepalive now does, its
  `rc=$?` sitting eleven comment lines below `else` explaining why. Treating
  `else` as a block end would flag the FIX for `1e3a65b29` as the bug.
- **Only standalone captures count.** `tar "$@" || ec=$?` puts command and
  capture on one line, so it cannot be stale; it is a correct idiom.
- **A `$?` inside a quoted string or a comment is not a capture.**
  `scripts/runpod/run_server.sh` has one in a `trap '…rc=$?…' EXIT`, evaluated
  when the trap fires rather than where it is written, and
  `upload_to_dropbox.sh` has one in a comment documenting the `|| ec=$?` idiom.
  An unanchored search reports both.

Probed with seven cases: captures after `fi`, `done` and `}` all fire; the
`else` form, the same-line `||` form and a capture adjacent to a plain command
correctly do not.

Superseded proposal:

    python3 $RULE_DIR/scripts/check_exit_capture.py  # scans scripts/ aii_runpod/ aii_launcher/ aii_public/ *.sh: for each `=$?` line, walk back over blanks/comments; fail if the predecessor is fi/done/} — verified today, 17 files, 0 hits

Proposed condition: `git diff --cached -U0 -- '*.sh' | grep -q '=\$?'`

Delete-check: Partially deletable: many captures vanish under `if cmd; then` composition,
but the watchers legitimately hold rc across retry/report loops (aii-ci-
watcher.sh:226,439,469,487 — all correctly adjacent), so the capture idiom
stays and adjacency is the invariant worth pinning.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Winner of the $?-placement pair: incident-backed silent-success shape
(keepalive logged failures as rc=0), shellcheck does not catch the placement,
and the watchers legitimately hold rc across retry loops so the convention
cannot be composed away.
- KILL: Duplicate: same incident (1e3a65b29), same invariant, same regex
check. Keep one. [merge->rule-exit-status-read-at-source]
- KEEP: Survivor of the two exit-status proposals: scan .sh files for `=\$\?`
whose previous non-blank line is fi/done/} — near-zero FP, catches a silent-
success incident shellcheck misses. Implementable, loud.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **holds, count grown.**

Non-skill shell files: **19** today against the stated 17. Growth in the
same direction as `rule-shell-strict-mode`, whose 62 is now 63 — the shell
surface is expanding slowly and both censuses age the same way.
