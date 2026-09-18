<!-- hook: shfmt -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every tracked shell script is shfmt-formatted (-i 4 -ci, check-only)

The formatter half of the shell toolchain: `shellcheck`
(rule-shellcheck) lints, `shfmt` enforces one consistent layout — the
same lint+format pairing as ruff↔ruff-format and oxlint↔oxfmt. Shell was
the one language that linted but never auto-formatted. `-i 4 -ci`:
4-space indent (matches the repo's Python) with indented switch-cases.
Check-only (`-l` lists drift, never rewrites) — mirrors
ruff-format/oxfmt's `--check` gate instead of auto-fixing, so it can't
pull another agent's unstaged edits into your commit. Project-wide:
every run re-scans every tracked `.sh`/`.bash` so a stale style issue
anywhere blocks the next commit. Vendored skill bundles are excluded
like every other formatter (they ship with upstream-determined
formatting). The `[ -f ]` filter mirrors rumdl/whitespace-format: during
a pathspec commit `git ls-files` can list a path another agent staged as
deleted, which shfmt can't open — lint only what's on disk. Whole-repo
scan is ~5 ms. Install once: download the static binary from
https://github.com/mvdan/sh/releases onto PATH.

Fix when blocked: `shfmt -w -i 4 -ci <file>` then `git add` and
re-commit.

Delete-check: tool-enforced, cannot delete — an autofix-on-commit
alternative was deliberately rejected because stage-fixed rewrites can
absorb another agent's unstaged edits; check-only is the safe shape.
