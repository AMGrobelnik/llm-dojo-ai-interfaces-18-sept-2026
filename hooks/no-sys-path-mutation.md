<!-- hook: no-sys-path-mutation -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# No mutation of `sys.path` — imports resolve through the package layout, not through a patched search path

House rule. The global CLAUDE.md's Python section names "no `sys.path`
edits" as one of the conventions that are now rules in this engine; this is
that rule. Proper package structure, no patching at import time. A patched
search path works from one working directory and one entry point and silently
breaks from any other; it also hides the real question, which is where the
shared code lives.

**Every spelling, not two.** The regex named `append` and `insert` alone until
2026-09-10, so `sys.path[:] = ...`, `sys.path[0:0] = ...`, `sys.path += ...`
and `sys.path.extend(...)` walked past a hook whose name is
"no-sys-path-mutation" — as did a plain `sys.path = [...]` rebind. It now names
the mutating methods (`append`, `insert`, `extend`, `remove`, `pop`, `clear`)
and any assignment to `sys.path` or to a slice of it. Assignment is spelled as
`=` NOT followed by a second `=`, which is what keeps the reads clean:
`for p in sys.path`, `sys.path[0]` on a right-hand side, `sys.path[0] == x` and
`sys.path != x` all stay silent, and the fixture in
`test_the_ere_catches_every_way_to_mutate_sys_path.py` pins both halves through
`git grep -nE` itself. `del sys.path[0]` is still not matched; no tree here
carries one.

FAIL evidence: the added line the grep prints.

Fix when blocked: put the shared code in a package with an `__init__.py` and
a `pyproject.toml` beside it, install it editable (`uv pip install -e .`),
and import it by name. For a one-file helper next to the script, a plain
relative import inside a package directory is enough. If the script really
must run from anywhere without an install, run it as a module
(`python -m pkg.script`) so Python does the path work.

Mode: ADDED LINES, downgraded from the whole-tree form this rule was drafted
in. Measured 2026-09-07 in notes-repo, with the two-method pattern that widening
has since replaced: **94 occurrences in 94 files in scope** — 63 of
the 94 in `apps/lantern/tools/`, 59 of those 63 reaching at
`sys.path.insert(0, "/home/<user>/lantern-tools")`, an absolute path
outside the repo, and 25 in `areas/food/grocery/`, 21 of those 25 naming
the `_lib/` sibling they import from (`sys.path.insert(0,
str(Path(__file__).resolve().parent.parent / "_lib"))`); 145 occurrences in
144 files tree-wide before the exclusions. That is a real backlog — the
tools want an installed package and `_lib/` wants to be one — not a set of
false positives, so it rides as an all-mode advisory and only new lines
block. Flip to `rules-grep --tree` once both are packages and the count
reaches zero.

In research-monorepo the stock is small and the widening is what surfaces the worst
of it. Measured 2026-09-10, whole-index lane: **3 findings before, 4 after**,
the difference being
`aii_server/agent_abilities/worker.py:135` —
`sys.path[:] = added + [p for p in sys.path if p not in added]`, a rebind of the
entire search path that the hook reported as clean while blocking a one-line
`append`.

Delete-check: cannot delete — the imports have to resolve somehow; the rule
says they resolve the way the language intends.
