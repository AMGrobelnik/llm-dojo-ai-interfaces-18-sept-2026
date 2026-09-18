<!-- hook: typos -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_ENGINE_DIR, RULES_REPO
# The working tree is free of spelling errors (typos)

`check.sh` runs `typos --force-exclude . .claude` — a walk of the working
tree from `.`, plus `.claude` named explicitly — so a typo in a file this
commit never touched surfaces now, not when someone next edits it. The
second argument is not decoration: a walk skips hidden directories, so
until 2026-09-03 nothing under `.claude/` (the rule engine's ~1,300 tracked
files) had ever been spell-checked by this gate, and CI's `--all-files`
form did not close the gap either. Measured by running typos over the
tracked file list explicitly: one finding, in a rule-engine test, that had
been invisible to every commit since it landed. Naming `.claude` walks its
non-hidden children (the config's excludes still apply) and adds 0.02 s. That is the owner directive of
2026-08-22 (file-examining checks cover the entire codebase; the script's own
header records the flip), and this statement says what the script does: it
is not scoped to the staged files and does not read `$RULES_STAGED`. This
body used to argue the opposite — a staged-list scan, with the walk's
hazards as the reason — while the script already walked; the two now agree.

The walk honors `.gitignore` (typos' default; the `--no-ignore*` flags that
disable it are not used), so ignored scratch is out of scope — but an
UNTRACKED, un-ignored file is IN scope, tracked or not. A concurrent agent's
throwaway dump at the repo root once blocked every agent's commit exactly
this way; the remedy is to gitignore scratch locations or correct the file,
never to edit another agent's live file to get past it. Cost is not a
consideration either way: the whole-tree walk measures 0.08 s (typos-cli
1.48.0, re-measured 2026-08-28), and the CI `hooks` job runs the same suite
with `--all-files`, so commit and CI see the same tree.

`_typos.toml` carries the project's domain-term allowlist (gen_strat, fpr,
lamda, etc.) — add new entries there with a comment WHY when typos flags a
real false positive. Exclusions live in its `[files] extend-exclude`. That
file belongs to the CONSUMER's root and only there: typos (1.48.0) finds a
config by walking UP from the search root, so one shipped inside this engine
is never read by a consumer walking the engine as a subdirectory — measured
2026-09-07 in a plain subdirectory, in the flagged file's own directory, and
in a nested git repo; all three were ignored, and `typos --dump-config -`
from the consumer root reports `extend-exclude = []`.

That is why one exclusion is a command-line `--exclude` instead: the engine's
own `notes-repo/hooks/` bodies quote the author letter for letter, misspellings and
all — 32 findings across 13 files as of 2026-09-07 — and
rule-his-quotes-stay-verbatim forbids correcting them. Do not name those
misspellings here either: this file is not exempt, and quoting one to
illustrate the problem re-creates it. `check.sh` derives that
glob from `$RULES_ENGINE_DIR` relative to `$RULES_REPO`, so it names THIS
engine's shelf and not a consumer's own `notes-repo/hooks/` directory, and skips
the exclusion entirely when the engine sits outside the repo being checked.
Nothing else in the engine is exempt.
`--force-exclude` overrides the upstream `--write-changes` default; we report
typos and block, not silently rewrite source files. Install once:
`cargo install typos-cli`.

`check.sh` exists only to normalize exit codes: typos exits 2 on findings,
while the engine blocks only on 1; genuine infrastructure codes (126/127)
pass through loud.

Fix when blocked: correct the spelling, or for a genuine domain term add
it to `_typos.toml` with a WHY comment in the same commit.

Delete-check: tool-enforced, cannot delete — free-text spelling cannot be
pinned away, only checked.
