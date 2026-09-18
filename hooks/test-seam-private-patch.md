# A newly added monkeypatch.setattr does not name a private seam

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 1s | active |

Converted from the retired rule engine's `general/commit/rule-commit-checklist-ack`,
item 6 of the consumer's `COMMIT_CHECKLIST.md`. The ack gate itself is deleted,
and so is the tree that held it — neither `general/commit/` nor `_decisions/`
exists in this repo, so both names are provenance rather than somewhere to look.
This hook is the first of the two
items that gate covered by asking rather than by measuring, so the slug is new
rather than inherited.

## Why

Item 6: a test that reaches into the module under test is coupled to that
module's file layout, not to its behaviour. Move `_run_probe` to another file
and `monkeypatch.setattr(mod, "_run_probe", fake)` stops biting — the test
still passes, while exercising the real dependency it meant to replace. The
same edit against a public attribute (`monkeypatch.setattr(httpx, "get", …)`)
survives the move, because the object is the same one everywhere.

The item carries its own measurement — 1204 `monkeypatch.setattr` sites, 264 of
them naming a `_`-prefixed target — and its own instruction for re-taking it:
"re-count both with an AST walk for `monkeypatch.setattr` calls whose second
argument is a string literal; a grep undercounts, since the multi-line spelling
is common." Re-counted here at `3f1060fa7`: 1627 string-named `setattr` calls,
441 of them private, against 390 that a single-line grep of the same pattern
finds — the grep misses 51 sites, 12% of the population, all of them the
multi-line spelling. So the item was right that only an AST walk can hold the
number, and the number is what this hook now keeps.

The ack gate asked an agent to confirm it had considered this. It fired 321
times without ever counting anything.

## Mechanism

`check.py` walks the AST of each in-scope test module and reports every call
whose function is an attribute named `setattr` and whose patched name starts
with `_`. pytest's `MonkeyPatch.setattr` has two shapes and dispatches on
argument count, so the walk does the same.

| failure mode | mechanism |
|---|---|
| `setattr(obj, "_x", f)` | 3 args, `args[1]` is the name |
| `setattr("pkg.mod._x", f)` | 2 args, last dotted segment |
| receiver renamed to `mp` | keyed on `.setattr`, not on a name |
| multi-line spelling | AST, and the whole call span |
| builtin `setattr(o, "_x", v)` | an `ast.Name` call, out of scope |

Every run judges the whole tracked tree: there is no narrower per-commit scope,
and a pre-existing private-seam call now blocks a commit exactly as a newly
added one does. This is the debt list, and it is also the gate.

Reads are index reads. Enumeration is non-recursing on both the live `check.py`
(`amg-hooks-ls-files`, `lib/amg_hooks/amg-hooks-ls-files`) and the ported `dispatch.py`
(`svc.tracked()`) — both honour `RULES_EXCLUDE`, and neither recurses into a
vendored submodule: its own test population is that submodule's own concern,
judged by its own gate, not this consumer's.

## Stock

Re-measured 2026-09-15 in `/home/<user>/projects/research-monorepo`, whole-tree,
index reads, `check.py` and `dispatch.py` enumerating identically (no
recursion): **481 findings across 117 distinct modules**, out of 982 tracked
test modules. 4 of the findings are under `.claude/skills/amg-hooks/`
(3 distinct modules, across `lib/amg_hooks/tests/` and `amg-hooks/hooks/`), 477 under
`tests/unit/`. The 2026-09-14 figure (480 across 116, out of 909) was taken
with the standalone `check.py` still recursing into vendored submodules, and
the tracked population also grew in the interim, so the two numbers are not
directly comparable.

There is no narrower per-commit scope any more: the checker blocks on the whole
stock, so this measured figure is exactly what a commit now needs to clear.

Worth knowing when re-measuring: a working-tree read can differ from an index
read, because the submodule's worktree carries modified or deleted paths the
index does not while other agents work in the same checkout. The index number is
the one for the tree under judgment.

## Fragility

| refactor | effect | guard |
|---|---|---|
| tests renamed `*_test.py` | population empties | exit 2 floor |
| fixture aliased to `mp` | none | keyed on `.setattr` |
| `_helper` made public | finding clears | that is the fix |

The vacuity floor is `AMG_MIN_TEST_MODULES`, default 10, the same on both
`check.py` and `dispatch.py`: neither recurses into a vendored submodule, so a
consumer's own tracked-test count (notes-repo: 16) must clear it unaided. It exists
to catch "the tree moved and this check now sees nothing", not to track growth.
A whole-tree run below it exits 2, which under lefthook blocks — meaning fix
the hook now, not fix the commit.

## Residue

The checklist item's second half — prefer injection with a default, resolved
inside the body rather than in the signature — is guidance for a rewrite a
human designs. The hook detects the fragile shape; it neither proposes the
replacement nor verifies one.

Not covered, deliberately: `unittest.mock.patch("pkg.mod._helper")` is the same
seam through a different library and a different population, and belongs to its
own hook rather than to a widened definition of this one. Patching a public
attribute of a private object (`mod._registry.get`) is not read as a private
name. `monkeypatch.setenv` and transport fakes, which the item names as the
durable alternatives, are not scored at all.

Stock was left as debt in the earlier, per-commit-scoped design. 436 sites is a
rewrite programme, not a single commit; that stock now blocks every commit
until it is retrofitted down.
