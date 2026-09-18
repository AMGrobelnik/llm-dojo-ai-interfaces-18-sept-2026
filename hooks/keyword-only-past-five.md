<!-- hook: keyword-only-past-five -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep, RULES_EXCLUDE, RULES_MODE
# A Python def takes at most five positional parameters — the rest go behind a bare `*` so callers name them

House rule. The global CLAUDE.md's Python section names "keyword-only
parameters past the fifth positional" as one of the conventions that are now
rules in this engine; this is that rule. It is ruff's `PLR0917` with
`max-positional-args = 5`; callers name what they pass. A six-argument call site is unreadable at the call and
silently wrong when two arguments of the same type swap places.

**This repo runs no ruff** — `lefthook.yml` records that as a decision, not
an oversight ("no Python package here, just loose scripts") — so this script
IS the enforcement of PLR0917, with the same semantics: `self` and `cls` are
not counted, `*args` / `**kwargs` are not counted, and everything after a
bare `*` or a `*args` is keyword-only and out of scope. Positional-only
parameters (before a `/`) count.

FAIL evidence: the `path:line: <name> takes N positional params` the checker
prints.

Fix when blocked: insert a bare `*` after the fifth parameter —

    def select(pool, lane, k, seed, floor, *, weights=None, verbose=False):

and update the call sites to name the arguments past it. If the signature
genuinely needs eight related values, the better fix is usually a small
dataclass carrying them.

Mode: ADDED LINES. Measured 2026-09-07 by this checker's own AST over the
247 in-scope modules: **21 signatures already exceed five, spread over 15 of
those modules**, the widest an 8-parameter `blended_score` in
`apps/lantern/tools/simulate.py` and a 9-parameter `__init__`
in `resources/research/proposals/<proposal>-stage-1-basic.py`. Blocking on those
would block every commit that
touches those files, so the checker judges only signatures the staged diff
TOUCHES — a def counts as touched when an added line falls inside its
signature — and prints the whole-tree stock as an advisory in all-mode. That
is exactly `rules-grep`'s contract, done over an AST because the property is
not a regex. Flip the checker to whole-tree when the 21 reach zero.

Scope: tracked `*.py` minus any `.claude/` tree and test files, minus
whatever the consumer's `.amg-hooks-exclude` file adds — one git pathspec per line,
plus anything in `AMG_HOOKS_EXCLUDE`, which `lib/amg_hooks/amg-hooks-env` reads into
`RULES_EXCLUDE` for every command. The `.amg-rules.yaml` this line used to
name belonged to the retired rule engine.

Delete-check: deletable the day this repo adopts ruff and turns PLR0917 on
— at that point the linter says it and this rule is a second copy. Until
then nothing else enforces it.
