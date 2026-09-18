<!-- hook: no-shell-true -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |
# No code-execution or deserialization sink takes a value this repo did not write

Seven clauses, one shape: a call where an argument crosses from data into
CODE. `subprocess.*(shell=True)`, `os.system`/`os.popen`, `eval`/`exec` on a
non-literal, `yaml.load` without a safe loader, `pickle.load`/`loads`,
`mark_safe` on a non-literal, and React's `dangerouslySetInnerHTML`.

## Why it is a dispatch.py and not a hook of its own

It rides `general-ast-checks` — one process for the whole set, one parse per
file shared by every check in it. A standalone process would re-list the tree
and re-parse every `*.py` for the sake of seven `ast.Call` predicates.

Measured 2026-09-16 against research-monorepo (whole index, aarch64), by running the
dispatcher with this `dispatch.py` present and with it moved aside:

| dispatcher run | wall |
|---|---|
| first run of the day, cold page cache | 51.1 s |
| warm, with this check | 11.0 s, 12.8 s |
| warm, without it | 13.1 s, 24.3 s |

Its marginal cost is below the dispatcher's own run-to-run spread — it adds
no parse and no `ls-files`, only a walk of trees that were parsed anyway.
That is the whole argument for the framework: a seventh sink costs nothing to
add, and a seventh PROCESS would have cost a second or two every commit.

## Why an AST and not a grep

`shell=True` as TEXT appears in every comment that argues about it — this
README, the dispatch module's docstring, a review note. As a keyword argument
it appears only where it is real. Same for `eval`: `model.eval()` is a torch
module going to inference, `eval(x)` is arbitrary code, and no regex separates
them while `ast.Name` does it exactly.

`dangerouslySetInnerHTML` is the one clause checked as text: the attribute
name is unique enough to have no false-positive class worth a TypeScript
parse, and a prose mention of it is what the marker below is for.

## Why non-literal

`exec("import x")` with a literal is a fixed program someone typed — a
readability problem, not a security one. The clause is stated against an
argument the reader cannot see, so a `Constant`, or an f-string of constants,
passes.

## The escape: `# nosec`, never an exclude

One line is accepted by a `# nosec <ID>  # <reason>` marker (`// nosec` in
TypeScript). It is deliberately bandit's own marker: it already means exactly
this to every reader, `no-lint-silencers` does NOT ban it (unlike `# noqa` and
`# type: ignore`), and a marked line shows up in the diff that adds it. A path
in an exclude list does not — and a directory that stops being scanned for
`pickle` stops being scanned for the next sink too, which is why there is no
blanket exclude here and no way to add one.

Test trees are skipped wholesale (the `no-silent-except` `_skip` predicate): a
test pickles its own fixture and execs its own generated source by design, and
the threat model — attacker-supplied input reaching a shipped code path —
does not describe any of it. The same predicate also skips a pytest module by
its basename — `test_*.py`, `*_test.py`, `conftest.py` — at any depth, so a
test that sits next to the code it exercises is recognized without needing a
`tests/` directory.

## The stock, when this landed

research-monorepo's whole index, 2026-09-16: `shell=True` 0, `os.system`/`os.popen`
0, unsafe `yaml.load` 0, `mark_safe` 0, `dangerouslySetInnerHTML` 0 across the
entire frontend, `exec` 3 (all under `tests/`, skipped), `pickle.loads` 1 —
`aii_lib/src/aii_lib/run/events/_query/_decode.py:29`, decoding a blob this
repo itself wrote to its own event store. That one line carries the marker
and its reason. Nothing was excluded.

Delete-check: deleting the check deletes the invariant, which is what the
sweep and `gate-can-fire` cover for every hook in the set.
