<!-- hook: no-actions-invocations -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# No script or package invokes GitHub Actions workflows (`gh workflow run`, `gh run ... --workflow=...`) — builds, CI and deploys are 100% local

The stock is ZERO — re-verified 2026-08-28: the proposed grep returns no
hits tree-wide — so this is a pure regression guard over a class that has
already recurred once (a wrong-scope systemctl reading once misled an agent
into dispatching Actions; CLAUDE.md Notes). The convention is prose-only
(repo CLAUDE.md Notes: 'NEVER build or deploy via GitHub Actions'; Actions
is billing-blocked and publish-images.yml was removed — verified:
.github/workflows/ holds only ci.yml). rule-launcher-retired-entrypoints
covers only the launcher's --gh flag (deploy.py:295-300 fails fast); nothing
covers shell. The regex must stay specific to workflow invocations — the CI
watcher's `gh api repos/.../statuses` (aii-ci-watcher.sh:156) is the REST
API and legitimate.

## History — the one live violation, since removed

When proposed, one live violation remained: aii-builder-keepalive.sh:163-164
fell back to `gh run list --workflow=publish-images.yml` for its SHA — a
dead query against a retired workflow that silently returned nothing. It was
removed in `9362f9adb` (re-measured 2026-08-24); the keepalive now carries a
comment at the same spot saying the lookup used to live there, and the SHA
chain falls through to origin/main, losing nothing.

Type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: shell-watchers)

## ADOPTED 2026-09-06 — with `--tree`, which the proposal omitted

`metadata.command` carries the proposal's regex and pathspecs unchanged, plus
`--tree`. Without it `rules-grep` greps only the lines the staged diff ADDS,
which makes the rule a stock-drift advisory in a sweep and blind to any
invocation it did not itself introduce; the engine's own guidance is that a
file-examining check holds over the entire tree whenever the stock is clean,
and it is — re-measured 2026-09-06, the whole-tree grep returns nothing, the
zero this body has recorded since the keepalive's dead fallback went in
`9362f9adb`.

Proven to bite 2026-09-06, in a throwaway `git init` tree under the scratch
dir — never against the repo's own files:

| probe | exit |
|---|---|
| `gh api repos/x/y/statuses/$sha` (the CI watcher) | 0 |
| `gh workflow run publish-images.yml` | 1, the line printed |
| `gh run list --workflow=publish-images.yml` | 1, line printed |
| both removed | 0 |

One spelling detail, because it looks like noise and is not. The second
alternative is `run[[:space:]](list|…)`, not `run (list|…)`:
`test_every_rule_command_resolves.py` reads a command head as the first word
after `;`, `&` or `|` and does not know about quoting, so a literal `|run `
inside the regex is read as a command named `run` and reported as resolving
nowhere. The bracket expression matches the same text and keeps that guard
able to parse this value.

Delete-check: Deletion already happened (workflow file removed, --gh
retired, the keepalive's dead fallback removed in 9362f9adb); this rule
enforces the deleted end-state.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Prose-only convention with one live dead invocation remaining; delete
the keepalive fallback lines then enforce. Absorbs rule-no-retired-actions-
refs (same grep) and rule-workflows-dispatch-only (the combined check also
asserts .github/workflows holds only dispatch-only ci.yml).
- KEEP: Enforces a documented retirement with one live dead-code violation
(keepalive's gh run list fallback). Absorbs rule-no-retired-actions-refs
(identical) and rule-workflows-dispatch-only (same invariant from the
workflow-file side) — one cheap rule: no Actions invocations anywhere,
.github/workflows holds exactly dispatch-only ci.yml.
- KEEP: Grep executable lines for 'gh workflow run' / 'gh run ... --workflow'
/ publish-images.yml. Deterministic, loud, one dead fallback
(keepalive:163-164) to delete at adoption. Absorbs rule-no-retired-actions-
refs.

## Ported to dispatch.py (2026-09-14)

Relocated onto the one-pass AST dispatcher
(`general/hooks/no-actions-invocations/dispatch.py`); the standalone
`amg-hooks-grep` line is removed from `general/lefthook.yml` in the same commit —
`dispatch.py` folders under a set that already wires `general-ast-checks`
are auto-discovered by `lib/amg_hooks/ast_dispatch.py`.

`_CANDIDATE` is the live ERE verbatim, byte-identical to the wired command
(the bracket-expression form the paragraph above explains, kept exactly so
this port does not reopen that `test_every_rule_command_resolves.py`
concern), and `PATHSPEC` is the same four `--` tokens the run line carries.
Two readers, one per tracked extension: `.sh` via `lib/amg_hooks/shast.py`
(`FileFacts.in_comment_or_string`, gated to `FileFacts.comments` only —
strings are not dropped, see below), `.py` via `tokenize`-derived comment
spans (the same technique `astcheck.py`'s own comment-aware checks use).
**What the confirm step drops, and only this**: a candidate sitting inside
a `#` comment in either language. **What it deliberately keeps**: a hit
inside a Python string literal or a quoted shell string — a command built
one piece at a time as a string constant and handed to `subprocess`/
`os.system` is exactly the shape this rule exists to catch (see the
dispatch module's own "WHAT IT KEEPS" paragraph), so the confirm step never
asks "is this inside a string?", only "is this inside a comment?" — the
same asymmetry `watcher-log-stamps-utc` draws for its own commonest real
shape.

Stock is 0 (the one historical live violation, `aii-builder-
keepalive.sh:163-164`, was removed in `9362f9adb`, as this README already
records), so the drop is exercised only by
`test_no_actions_invocations_bites.py`'s synthetic comment cases, not by
any real consumer-tree specimen.

### Drop-set audit against the consumer (research-monorepo, 2026-09-14)

OLD is the live ERE via `git grep --cached` over the consumer INDEX under
the live pathspec; NEW is this port under `AMG_HOOKS_SWEEP=1`.

| population (`*.sh` `*.py` `:!.claude/skills/**` `:!**/archive/**`) | OLD | NEW | DROPS | ADDED |
|---|---|---|---|---|
| 672 tracked files | 0 | 0 | 0 | 0 |

The population is non-empty (672 files) and both sides agree on zero, so
ADDED is 0.

### COND-1

The live run line's `glob:` key (`*.sh`, `*.py`, `.github/**`) is a strict
superset in form of what `PATHSPEC` (`*.sh`, `*.py`) can select, so
`GLOBS` admits everything `PATHSPEC` can select and the TREE-mode judge is
never triggered short of its full population.
