<!-- hook: no-silent-except -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: condition was a content regex over the diff: the checker must return 0 fast when absent runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep, RULES_EXCLUDE
# An except block logs, re-raises, or explains — never swallows silently

Applies WHOLE-TREE: the checker scans every tracked `*.py` module on every
run (`git ls-files`, minus `tests/`, `scripts/` and `.claude/`), so a new
silent handler blocks wherever it lands — not only in the staged diff. (It
was scoped to handlers added by the staged diff until 2026-08-22, when the
stock was cleared and the scope flipped; see below.)

The consumer's `.amg-rules.yaml` `exclude:` pathspecs are appended to that
listing, exactly as `lib/amg_hooks/amg-hooks-grep` appends them — a rule says what it
bans, the consumer says where it does not look. Until 2026-09-07 they were
not, because this checker walks the tree itself instead of through
`rules-grep`: notes-repo carried about a hundred latent hits inside trees its
config had already declared out of scope.

FAIL when an `except` block does nothing but `pass`, `continue`, or return
a constant — with no logger call, no re-raise, and no comment saying why
silence is correct. Quote the handler as evidence. PASS handlers that log
(any level), re-raise, chain, or carry an explanatory comment
("best-effort teardown" counts).

Why: 94 silent handlers were measured by grep across the four backend packages (`aii_lib`, `aii_server`, `aii_pipeline`, `aii_runpod`, excluding `**/tests/**` — named here 2026-08-25 because the figure below could not otherwise be re-measured), of 475 `except Exception` sites — still 475 on 2026-08-22, and 477 on 2026-08-25 — and each was a place a real failure disappeared. The grep undercounted: the checker's AST put the true stock at 157, the sweep below cleared every one, and the whole-tree count has read 0 since.
The repo's own rule 3 ("explicit exception handling, no silent fallbacks")
already says this; nothing enforced it.

Fix when blocked: `logger.exception(...)` for surprises, `logger.debug`
plus a comment for expected noise, or one comment line explaining why
silence is the correct behavior here.

Delete-check: cannot delete — exceptions exist; ruff's S110/S112 are
narrowed away in this repo, so judgment is the enforcement.

Flipped whole-tree (2026-08-22): the true stock was 157 handlers (the
checker's own AST judgment, not the crude grep). All cleared in one
reviewed sweep — 156 gained an honest WHY comment written from reading
each site, one was a real defect (declared ability venv failing to
resolve was silently skipped; it now logs a warning naming the ability).
The checker scans every tracked module every run; a new silent handler
blocks wherever it lands.

CONDITION WIDENED 2026-08-25 — it now carries `[ "$RULES_MODE" = all ] ||`, so
`rules.py all` actually runs it.

The checker enumerates `git ls-files '*.py'` — every tracked module, 1291 of
them — and this body already describes itself whole-tree ("the whole-tree count
has read 0 since"). The CONDITION did not match that: it fired only when a
staged diff added a line containing `except`, so the one sweep an owner runs to
ask "is everything green" skipped the rule entirely and reported 48 passes
without it. A whole-tree scanner that the whole-tree sweep cannot reach is the
same scope mismatch `rule-user-dir-one-layering-rule` records, in the opposite
direction.

Costs 0.40 s over those 1291 files, and the tree exits 0 today, so the sweep
went from 114 skip / 48 pass to 113 / 49 with no new work. Commit behaviour is
unchanged and was checked rather than assumed: with `RULES_MODE=commit` and
nothing staged the condition still exits 1 and the rule still skips.

`rule-module-docstrings` was examined alongside it and deliberately NOT changed.
Its checker reads `git diff --cached --diff-filter=A`, so it asks only whether a
NEWLY ADDED module carries a docstring; existing modules are grandfathered, and
running it whole-tree would ask a question the rule does not make.

DENOMINATOR RE-MEASURED 2026-08-25 — it is stable, and the population is now
named so that stays checkable.

The 475 could not be reproduced as written. Under the CHECKER's population (all
tracked `*.py` less `tests/`, `scripts/`, `.claude/`) the count is 490 at
2026-08-22 and 494 today — nowhere near 475, because that grep covered a
narrower set than the checker scans. Recovering it took measuring each package
separately: `aii_lib` + `aii_server` + `aii_pipeline` + `aii_runpod` gives 479
at that date and 477 today, with `aii_launcher` (8 sites) excluded. Close
enough to identify the population, not exact — so the sentence above now names
it rather than saying "the four backend packages".

Nothing needed fixing. The denominator drifts by a handful as code is written,
which is expected of a denominator; the number this rule GATES on is the silent
handler count, and the checker exits 0 today exactly as the body claims. A
denominator that cannot be re-measured is still worth repairing, because the
next reader cannot tell a stable figure from a stale one without redoing the
work — which is the whole cost this note removes.
