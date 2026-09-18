<!-- hook: tracked-script-carries-no-hook-bypass -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

# No tracked `*.sh` or `*.py` ships a git-hook bypass or a sweeping `git add`

A tracked shell or python script must not carry `--no-verify`, `--no-gpg-sign`,
`core.hooksPath=/dev/null` (or `=''` / `=""`), `git add -A`, `git add .`, or
`git add --all`. The global CLAUDE.md states both invariants in its strongest
register — "Never bypass git hooks" and "stage your own files by explicit path
(never `git add -A` / `git add .`)" — and they are universal to both consumer
repos, so the hook lives in `general/`.

## Why this hook, when the guard already exists

The consumer already runs a `PreToolUse` guard,
`.claude/hooks/guard_destructive_git.py`, that surfaces exactly these tokens the
instant before a command runs. That guard catches the LIVE, one-off case — an
agent typing `git commit --no-verify` at the prompt. It is blind to a bypass that
is COMMITTED INTO A SCRIPT: the guard sees a command once, as it is dispatched,
while a script's `git add -A` runs every time the script runs and never passes
through the guard at all. `lefthook` is the only layer that sees the script's
source before it ships. This hook closes that seam — it judges the tracked source
text, so a bypass baked into a shell or python file blocks the commit that would
ship it.

## Mode: tree (every occurrence blocks)

The invariant admits ZERO stock, so this is a TREE-mode check: every occurrence
blocks, at commit AND at sweep, and a COMMITTED bypass is as much a violation as a
newly added one (the bites test pins this). The one vacuity bail is an empty
population — no tracked `*.sh`/`*.py` in scope means the trees moved and the ban
would pass on everything, so it raises `CannotRunError` (rc 2) rather than a
hollow green.

## Text scan, not AST — and how the false positives are removed

The population is `*.sh` AND `*.py`, half of which never parses as Python, so this
reads each file's INDEX text (`svc.staged_text`) and scans it one physical line at
a time, `git grep` style. The false positives an AST walk would remove are removed
by three deliberate filters instead:

- **comment lines are skipped** — a comment is a line whose first non-blank
  character is `#` (the marker shell and python share), so a line that only talks
  ABOUT a bypass does not flag. Only a full-line `#` comment is excused; the rule
  is intentionally that simple.
- **word boundaries reject lookalikes** — `--no-verify(?![-\w])` rejects
  `--no-verify-ssl`; `\bgit\s+add\s+…` rejects `git added`; the `core.` prefix and
  the `/dev/null`/empty value together reject `hooksPath=/etc/hooks` and
  `core.hooksPath=/etc/hooks`.
- **PATHSPEC subtracts the DATA trees** — test fixtures asserting the guard, the
  rule-engine's own `.claude/` tree, migrations and archives, where these tokens
  live as data rather than as invocations.

**Deliberate divergence from the guard, in the strict direction.** The guard is
warn-only, so it can afford `--no-verify\b`, which also fires on
`--no-verify-ssl`; harmless when it only prints a note. This hook BLOCKS, so it
must not fire on a lookalike, and uses `(?![-\w])` instead of `\b`. The
`core.hooksPath` and `git add`-sweep patterns are ported from the guard as-is
(their boundaries are already tight), so a script bypass and a live bypass are
surfaced by the same shape of rule. `git add -A rail` — a scoped `-A` — is flagged
exactly as the guard reads it: the ban is on the flag, not on the absence of a
pathspec.

## Subset / drop-set (COND 2)

By construction the check produces a finding ONLY from a line a banned pattern
matched, so findings ⊆ candidate lines trivially — there is no second AST stage
that could introduce a finding on an unmatched line. There is likewise no
regex-vs-AST drop set to classify: the only lines the scan drops are the ones the
three filters above remove (comment / lookalike / excluded path), and the bites
test's NEGATIVES exercise each of those classes so the filters stay pinned.

## Whole-tree dry-run (two consumers, 2026-09-10)

Run whole-tree (`AMG_HOOKS_SWEEP=1`) over both consumer checkouts, the hook was the only
one discovered. Findings are all `git add -A` in shipped scripts — GENUINE
occurrences of a banned token, not false positives (the owner decides fix vs
waive):

- **research-monorepo: 3** — `aii_public/sync.sh:81`, `:121`, `:233`. (Line 58, a `#`
  comment mentioning `git add -A`, is correctly NOT flagged.) These operate on a
  separate staging clone, but the flag is what the ban names.
- **notes-repo: 6** — `areas/styling/deploy-{rail,wardrobe,weekender}.sh`,
  `projects/hammock/deploy-hammock.sh`, `projects/jacuzzi/deploy-jacuzzi.sh` (each
  a `git add -A <path> .nojekyll`), and `resources/github/deploy-gh-page.sh:36`
  (a bare `git add -A`).

No comment-line, lookalike, string-literal, or excluded-path false positive
appeared in either tree. The vendored `amg-hooks` / `amg-rule-engine`
submodules are gitlinks, so `git ls-files` never lists their internals and they
are out of scope automatically.

## Wiring

ADDITIVE + UNWIRED — `lefthook.yml` is edited by the wiring peer, not here. This
is a pure `dispatch.py` check (`SCOPE = "tree"`, `GLOBS = ["*.sh", "*.py"]`,
`PATHSPEC` applied inside `run()`), run through the shared dispatcher
`lib/amg_hooks/ast_dispatch.py`, wrapped by `amg-hooks-env` (which supplies `RULES_EXCLUDE` from
the consumer's `.amg-hooks-exclude`, puts `lib/amg_hooks` on PATH, and sets cwd to the repo
root). **Mode is TREE — internal to `dispatch.py` (it ignores `svc.sweeping` and
judges the whole index); no `--tree` flag exists for a dispatch check, and
`amg-hooks-env`'s stage stays `commit`** (`amg-hooks-env` understands only `commit`/`checkout`/
`push`, and flips to the whole-index lane on its own under `AMG_HOOKS_SWEEP=1`).

The run line to hand the wiring peer:

```yaml
tracked-script-carries-no-hook-bypass:
  glob: ['*.sh', '*.py']
  run: '{amg_hooks}/lib/amg_hooks/amg-hooks-env {amg_hooks}/general/hooks/tracked-script-carries-no-hook-bypass commit -- .venv/bin/python {amg_hooks}/lib/amg_hooks/ast_dispatch.py {amg_hooks}/general/hooks {staged_files}'
```

Discovery note the peer needs: `ast_dispatch.py <dir>` discovers `<dir>/<name>/
dispatch.py` for every SUBDIRECTORY — so the target is the SET dir
(`{amg_hooks}/general/hooks`), which co-runs every general dispatch check in one process
(the intended cutover shape), NOT the hook's own folder (which has no `dispatch.py`
subdir and would discover nothing). To run this hook ALONE before cutover, point
`ast_dispatch.py` at a dir whose only child is `tracked-script-carries-no-hook-bypass/`.
`run()` rebuilds its population from `svc.tracked` regardless of `{staged_files}`,
so the staged list only gates whether the hook fires (via `glob`), never what it
scans.
