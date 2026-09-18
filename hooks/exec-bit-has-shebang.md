<!-- hook: exec-bit-has-shebang -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every tracked file with the executable bit (mode 100755) starts with a shebang, so nothing invoked as ./script is ever handed to sh with the wrong interpreter.

The invariant HOLDS today — every tracked file carrying the executable bit
starts with `#!` (102 executables, re-measured 2026-09-06; the count drifts
as scripts land, the zero-violation stock is the pin) — and the command is
wired in the frontmatter, so approval is a `git mv` away rather than a
mechanism to build. A clean zero-stock consistency pin: the stocks this body's History
section records were cleared before wiring. No condition: the check is a
single `git ls-files` and two bytes per executable, and an exec bit can be
added by a `chmod` in any commit, so there is no narrower diff that reliably
predicts it.

Both halves are read from the INDEX. The mode always came from
`git ls-files -s`; the two bytes now come from the blob that entry names
(`git cat-file blob`) rather than from `head -c2` on the working-tree file. A
whole-tree gate that reads disk judges whatever a concurrent agent has
half-written — on 2026-09-05 that shape failed two unrelated commits across
this family of rules — and the index is exactly the tree under judgment
(`git commit --only` points `GIT_INDEX_FILE` at a temporary index of HEAD plus
the named paths; a plain commit's `.git/index` is what lands). It also deletes
the `[ -f "$f" ]` guard the disk read needed: a path staged and then removed
from the working tree has a blob and is judged, instead of silently skipped.
~0.13 s whole-tree (2026-09-06).

The reverse direction is deliberately NOT checked: the repo's convention is
bash-invoked non-exec scripts (rule-engine check.sh files,
scripts/runpod/race_barrier.sh invoked as 'bash .../race_barrier.sh' at
run_server.sh:111), and a missing exec bit only bites something invoked as
`./script`, which nothing in the tree is. This is pre-commit's
check-executables-have-shebangs, the standard mechanization; nothing else in
the claimed rules touches file modes.

**The proposed one-liner is kept in shape but hardened, and the difference is
worth one line.** It split `git ls-files -s` on whitespace and took `$4`, which
is the path only while no path contains a space. Given a tracked
`dir with space/spaced.sh`, it still exits 1 — but reports `dir`, a path that
does not exist, so the finding cannot be acted on. Splitting on the TAB that
`ls-files -s` actually uses reports the real name. Verified both ways in a
throwaway repo.

Proven to bite: a shebang-less executable is named, a shebang-carrying one is
not, and a non-executable plain file is ignored.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: git-repo-hygiene)

Superseded proposal — the whitespace-split one-liner as first filed, kept
for the record; the hardened TAB-split form the paragraph above argues for
is the one wired in the frontmatter:

    bad=$(git ls-files -s | awk '$1==100755{print $4}' | while read -r f; do [ -f "$f" ] && head -c2 "$f" | grep -q '^#!' || echo "$f"; done); [ -z "$bad" ] || { echo "$bad"; exit 1; }

Delete-check: Considered deleting exec bits repo-wide instead (no 100755 at all) — fails:
rules-grep/rules.py/rules-fe-root and the watcher .sh files
(scripts/local/watchers/aii-image-watcher.sh etc., installed into
~/.local/bin) are executed directly and correctly carry both bit and shebang.
The parity rule enforces the minimal correct state: the six vestigial bits
found at filing were deleted (History below), and the legitimate ones — 92
at the 2026-08-28 re-measure — stay.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Six live findings, standard-hook territory (pre-commit's check-
executables-have-shebangs) that the repo's adopted hook family (#130-135
rules) doesn't include yet, and no claimed rule overlaps. Drop the six
vestigial bits when landing; the check is one git ls-files -s pass.
- KILL: All 6 violations live in vendored anthropic-* skill trees where the
bit is inert and a fix fights upstream re-syncs; the prevented defect
(./invocation handed to sh) is theoretical for files nobody dot-slashes. Cost
is low but value is lower.
- KEEP: Standard-tool mechanization exists (pre-commit's check-executables-
have-shebangs — prefer adopting it over hand-rolling); 6 live findings; non-
vacuous. House already runs that hook family (#130-135).

## History — superseded stocks

STATUS (2026-08-22): stock cleared. The verifier re-measured the claim
independently — mode histogram {100644: 2710, 100755: 81}, and exactly
the six cited files carried the executable bit without a `#!` line. All
six are invoked as `python <script>` / `node <script>` from their own
SKILL.md, never as `./script`, so the bit did nothing except set a trap:
`./pack.py` with no shebang executes under sh and fails confusingly.
Mode-only change, no content touched. The rule can therefore be approved
against a clean stock and could reasonably ship whole-tree from day one.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **partly-wrong**, and the
correction moves this from a defect fix to a consistency rule.

Both directions were measured over the tracked tree:

| direction | count |
|---|---|
| exec bit set, no shebang | **0** |
| shebang present, exec bit unset | 75 |

So the "6 live findings" figure does not reproduce in the direction the
rule name implies — that stock is empty. The 75 in the other direction
break down as 70 under `.claude/` (skill scripts), plus exactly five
elsewhere: `aii_frontend/dev/prod-component-dashboard.ts`,
`scripts/runpod/pg_boot_guard.sh`, `scripts/runpod/race_barrier.sh`,
`tests/preflight/ability.py`, `tests/preflight/pipeline.py`.

**None of the five is a live defect**, and this proposal already says so
at its own lines 15-16 — they are "invoked as `bash .../race_barrier.sh`".
Each invocation site was checked: `bun dev/prod-component-dashboard.ts`
from `dev-server.sh:34`, and `bash` for the RunPod pair. A missing exec
bit only bites something invoked as `./script`, and nothing does.

Also corrected: "House already runs that hook" does not hold. There is no
`.pre-commit-config.yaml` in this repo, and `lefthook.yml` configures no
shebang or executable check. Whatever runs, it is not
`check-executables-have-shebangs`.

What remains is a real but smaller case for the rule: a shebang states
"run me directly", and 75 files say that while being unable to. That is
worth a consistency gate; it is not worth approving on the belief that it
fixes six live findings, because it fixes none.
