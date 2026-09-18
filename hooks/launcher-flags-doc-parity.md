<!-- hook: launcher-flags-doc-parity -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# The launcher flag table in README matches the aii_launcher argparse surface

README.md's "All flags" table (lines ~86-100) documents the flag set and must
match aii_launcher/src/aii_launcher/deploy.py's argparse surface. A table titled
"All flags" that omits some is worse than no table, because it is read as
exhaustive.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: docs-comments)

Proposed command (implemented at approval):

    python3 $RULE_DIR/scripts/check_flag_parity.py  # AST-parse deploy.py for add_argument('--x') set; regex-extract --flags from the doc table; fail on flag absent from argparse, and on argparse flag absent from README's table

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: The README flag table documents the single control surface; drift there
misleads readers. Cheap AST-vs-table check.
- KEEP: The flag table is the primary documentation for aii_launcher; maintaining
accuracy is essential for agent interfaces and end users alike. Mechanical
parity against the argparse surface is a small, high-value check.
- KEEP: python -c argparse introspection vs markdown-table flag extraction —
both deterministic. Implementable, loud.

IMPLEMENTATION NOTE (2026-09-15):
Root CLAUDE.md was deleted in commit 7fab460b9 as part of consolidating
documentation. This hook now checks README.md only. The hook source
(scripts/check_flag_parity.py) has been updated to drop the CLAUDE.md check.

Previously (2026-08-26), the hook found README's "All flags" table listed **11 of 15**
flags, omitting --rebuild, --redeploy, --public-sync and --gh entirely. Those four
were added to README in the same change, so the check now passes cleanly.
The omission was deliberate in substance: the four missing flags are build/image-push/
export/retired operations that belonged in CLAUDE.md's ops table rather than the
run-time flags documented in README.

## Implementation details

**The check runs one way only, deliberately.** Flags come from argparse and
must appear in README. The reverse — every `--flag` in README must exist in
argparse — is not checked, because the file discusses other tools' flags at
length: a naive reverse sweep reports 8 "ghost" flags in README (--json,
--once, --platform, --no-verify, --no-deps, --python, --port), and every one
is a correct mention of git, docker, uv or the watcher. Scoping the reverse
would mean parsing the table region, which drifts faster than the flags do.

So a REMOVED flag left in the table is not caught. `--gh` shows why that matters
less than it sounds: retired, yet still declared in argparse precisely so it
fails fast — the exact shape a reverse check would misread as a ghost.

Flags are read from every tracked `aii_launcher/**.py`, not one module, so the
split into `_deploy/` parts cannot hide a declaration.
