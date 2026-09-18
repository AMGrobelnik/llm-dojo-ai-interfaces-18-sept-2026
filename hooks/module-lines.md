<!-- hook: module-lines -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Package-source Python modules stay under 600 code lines

Blank and comment-only lines are free: this repo explains itself in prose,
and counting comments would push writers toward terser code AND thinner
explanations at once. A THRESHOLD, not a ratchet — over the cap fails
whether or not the commit made it worse, because a ratchet lets a module
sit at 1500 forever so long as nobody adds to it, which is the state this
ended. WHOLE-TREE: the gate walks every tracked .py on every run —
flipped 2026-08-22 by owner directive, as check.sh's own comment records —
so the verdict does not depend on what the commit touches. Tests,
.claude/skills and generated clients are outside the
gate by a DIRECTORY rule rather than a list — no module is named in the
script, so a new oversized one always fails and nothing has to be
maintained to keep that true. ~90 ms whole-tree over 600 modules
(re-measured 2026-09-06).

The bytes counted come from the INDEX (`git ls-files -s` plus one
`git cat-file --batch`), never from the working tree. A whole-tree gate that
reads disk judges whatever a concurrent agent has half-written: measured
2026-09-06, four of the 600 modules had a working-tree count different from
their index count, and on 2026-09-05 exactly that shape failed two unrelated
commits elsewhere in this family. The index is the tree under judgment —
`git commit --only` points `GIT_INDEX_FILE` at a temporary index of HEAD plus
the named paths, a plain commit's `.git/index` is what lands, and in
`RULES_MODE=all` the sweep runs on a checked-out commit where the two agree.
The population is unchanged either way (600 modules, same set).

The checker is `scripts/lint/check_module_lines.py`;
`.claude/skills/amg-hooks/research-monorepo/unit-tests/lint-gates-actually-bite/test_module_lines_gate.py` pins its counting and scope rules.
`check.sh` is a bare `exec` of the checker in its no-args mode, which
enumerates the whole tracked tree through git.

Fix when blocked: split into a sibling `_[name]/` package — layout,
re-export rule and equivalence proof are in CLAUDE.md, "Splitting a
module that got too big". Do not add an exemption to the script.

Delete-check: tool-enforced, cannot delete — module size is a real
dimension of variation and the unbounded state (a 1500-line module
nobody could split) is what this cap was introduced to end.
