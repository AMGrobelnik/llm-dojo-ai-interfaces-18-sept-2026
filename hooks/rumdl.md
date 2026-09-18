<!-- hook: rumdl -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every tracked .md outside .claude/skills, .agents/skills and neurips/resources passes rumdl (four rules disabled)

rumdl is the Rust port of markdownlint — same rule IDs (MDxxx), reads
existing .markdownlint config, ~30-100× faster than the npx
markdownlint-cli we used previously. Disable list is comma-separated
(markdownlint-cli used space-separated).

Every run re-scans the whole tracked tree, but the scope is narrower than
"project-wide" and the statement says so: `check.sh` drops everything under
`.claude/skills/` and `.agents/skills/`, plus `neurips/resources/**`.
Measured 2026-08-28: 515 tracked `.md`, 26 linted, 489 excluded — and 381 of
the excluded are this repo's OWN rule corpus under `amg-hooks`, not
vendored bundles. Filtering via `git ls-files | grep -v` keeps the exclusions
co-located with the run command, so the scope is one line away from the tool
call.

**Why the corpus stays excluded here when `rule-md-table-width` narrowed its
`:!.claude/**` to vendored-only on 2026-08-26 for the same files.** Table
width was already all but met there (10 wide rows), so narrowing cost
nothing. rumdl over the corpus alone reports 980 issues in 375 of 381 files
(measured 2026-08-28 with the same `-d MD013,MD033,MD041,MD057` disable
list; 968 are auto-fixable by `rumdl fmt`). Narrowing this exclusion the same
way is a corpus-wide reflow first and a one-line filter change second — an
owner-sized change, not a statement fix. Until it lands the two markdown rules
deliberately differ in scope, and this paragraph is the record of why.

The other exclusions stand on their own grounds. `neurips/resources/**` is
research-paper draft prose with citation tables, `<details>`/`<summary>`
HTML and intentional phase-numbered lists, where strict markdown rules fight
authorial intent. Genuinely vendored skill bundles (`anthropic-*`, the
generated handbooks, `.agents/`) ship with upstream-determined formatting and
are not ours to reflow.

Disabled: MD013 line-length, MD033 inline-html, MD041 first-line-h1,
MD057 relative-link-target-exists (too brittle: aii_public/README.md
links to LICENSE/CONTRIBUTING.md that exist in the deploy-target repo,
not this repo; planning docs reference docs not yet written). Install
once: `uv tool install rumdl` (puts the binary on PATH; skips uvx's
per-run overhead).

The `[ -f ]` filter mirrors whitespace-format's stat filter: `git
ls-files` reads the INDEX, and during a pathspec commit (`git commit --
<paths>`) git hands hooks a TEMPORARY index of HEAD + only the named
paths — a deletion staged by anyone else is not applied there, so the
dead path gets listed, rumdl can't open it, and every pathspec commit in
the repo fails. Lint only what exists on disk; deleted files have
nothing to lint.

Fix when blocked: rumdl names file, line and MDxxx rule — fix the
markdown; do not grow the disable list without owner approval.

Delete-check: tool-enforced, cannot delete — markdown renders anywhere,
so broken structure is invisible until someone reads the rendered page.
