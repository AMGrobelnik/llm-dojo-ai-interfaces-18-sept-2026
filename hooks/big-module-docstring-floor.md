<!-- hook: big-module-docstring-floor -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A package-source module over 200 code lines opens with a multi-line WHY docstring, tree-wide

Measured: 153 package-source modules exceed 200 code lines; 146 carry a multi-
line docstring (116 at 6+ lines), and exactly 7 carry a bare one-liner
filename restatement —
aii_lib/src/aii_lib/abilities/ability_server/discovery.py ('Skill discovery,
venv setup, and environment checks.'),
aii_lib/src/aii_lib/claude_oauth/autologin/oauth_flow.py,
aii_lib/src/aii_lib/claude_oauth/_accounts_health/__init__.py,
autologin/_browser_login/_helpers.py,
aii_lib/src/aii_lib/utils/deploy_github/repo_ops.py,
aii_pipeline/src/aii_pipeline/steps/_4_gen_paper_repo/utils/readme.py,
aii_server/dashboard/api/files/_run.py. rule-module-docstrings only fires on
ADDED files (condition: --diff-filter=A) and judges register agent-side; these
7 predate it and nothing will ever revisit them. A whole-tree mechanical floor
(docstring >= 2 lines on 200+ code-line modules) is the cmd backstop for the
pinned add-time norm.

Mechanism (implemented 2026-08-26, `scripts/check_docstring_floor.py`):

    .venv/bin/python $RULE_DIR/scripts/check_docstring_floor.py

**It arrives GREEN, and it did not start that way.** The rule was written
against 7 modules over the threshold whose docstring was a one-line filename
restatement; all 7 have since been written, so all 154 large modules now carry
a multi-line docstring. The floor was deliberately NOT relaxed to accommodate
them — a floor that exempts its own backlog is not a floor — so the exemption
lived in the pending-mechanism runner, with its reason, until the last module
landed. That list is checked in both directions, so the runner itself demanded
the exemption be deleted the moment this went green.

None of the 7 was invented from its filename. Each was assembled from
arguments already made in comments further down the same module and moved to
where a reader arrives — a WHY guessed from a filename is worse than the
one-liner it replaces, because it reads as though someone had checked.

Re-measured 2026-08-26: 154 modules exceed 200 code lines (the body said 153),
148 now carry a multi-line docstring (was 146), 117 carry six or more (was
116). Every census moved by one as the tree grew; the violation set did not
move at all until it was worked.

The threshold and the population are shared with `rule-module-docstrings` on
purpose — same six package trees, tests excluded, same 200 code-line
definition of "big", code lines being non-blank non-comment. Two gates
disagreeing about what big means would let a module be big for one and small
for the other.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: docs-comments)

Proposed command (implemented at approval):

    python3 $RULE_DIR/scripts/check_docstring_floor.py  # ast per tracked package-source module (same dir scoping as module-lines: not tests, not scripts/, not generated); count non-blank non-comment lines; if >200, require ast.get_docstring with >=2 lines; print offenders file:docstring-line-count

Delete-check: Cannot delete — docstring presence IS the dimension, and the 600-line cap
deliberately excludes comments to encourage exactly this prose. Fix the 7
offenders first (write their WHYs), then the rule enforces the achieved end-
state. Not redundant with ruff D100: presence exists, the MULTI-LINE floor on
big modules does not.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Complementary to rule-module-docstrings, which is added-modules-only
and register-focused (verified); this is the whole-tree mechanical floor that
catches the 7 existing offenders and edits to existing big modules, which the
staged-only agent rule structurally cannot.
- KILL: A parameter tweak to the existing module-docstrings rule (require
multi-line WHY above 200 code lines), not a new rule. Fix the 7 one-liner
offenders and raise the existing gate's floor. [merge->module-docstrings]
- KEEP: AST: code-line count >200 → require multi-line module docstring.
Deterministic, 7 offenders to fix at adoption, complements the comment-
friendly 600-cap culture. Loud.
