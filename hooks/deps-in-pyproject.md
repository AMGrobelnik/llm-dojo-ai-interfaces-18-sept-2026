<!-- hook: deps-in-pyproject -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep, RULES_EXCLUDE
# No new requirements.txt — dependencies go in pyproject.toml

House rule (global CLAUDE.md #8), with one measured exception already in
the stock: the ten `server_requirements.txt` files under .claude/skills/
are a deliberate second system provisioning the ability venv — nine live
skills plus one under `skills/archive/` (measured 2026-08-22 at 10;
previously written as nine, which counted only the live skills). The
dependency audit flagged the split as a cost, and widening it further
makes that worse.

This blocks ADDING any new `requirements*.txt` outside .claude/skills/.

The consumer's excluded pathspecs are appended to the `git ls-files` listing,
exactly as `lib/amg_hooks/amg-hooks-grep` appends them — a rule says what it bans, the
consumer says where it does not look. They come from the repo-root `.amg-hooks-exclude`
(one pathspec per line) plus `AMG_HOOKS_EXCLUDE`, which `lib/amg_hooks/amg-hooks-env` reads into
`RULES_EXCLUDE`; the `.amg-rules.yaml` this line used to name belonged to the
retired rule engine. Until 2026-09-07 they were not appended at all, because
this checker walks the tree itself instead of through
`amg-hooks-grep`: notes-repo failed on 18 vendored third-party requirements files
under `archive/` and `resources/skills/` that its config had already declared
out of scope.

Fix when blocked: declare in the package's pyproject.toml (uv workspace
member) and run `uv sync`.

Delete-check: the skills exception is the deletable half — folding ability
deps into the main closure is an open owner decision; this rule at least
stops the pattern spreading.

RE-MEASURED 2026-08-24 — **ten is right, and it reconciles an apparent
contradiction with CLAUDE.md.**

Ten `server_requirements.txt` files are tracked (re-verified 2026-08-28).
CLAUDE.md:485-486 says "the 9 skill `server_requirements.txt` files"
(re-anchored 2026-08-28 — the sentence sat at :419 when this was written),
and both are correct: one of the ten is
`.claude/skills/archive/aii-image-gen-openai/`, an archived skill. Live
skills carry nine; the tracked file count is ten. Anyone reconciling the
two numbers later should not treat the gap as drift in either document.
