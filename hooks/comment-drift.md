# Prose that names a path, a line or a symbol names one that exists

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 5s | active |

## Why

The agent rule behind this was applied 1748 times and blocked 707 — the
single biggest blocker in the ledger. Its FAIL clause is *"the adjacent
comment or docstring now plainly says something FALSE"*, and its body
states outright that this cannot be mechanized.

That is true of the general claim and false of the population. The rule
already shipped a mechanized slice of itself, and the FAIL evidence is
overwhelmingly one shape: prose that NAMES something — a path, a line number,
a parameter, a symbol — which the repository can be asked about directly.

So the decomposition is to keep every claim whose subject the tree can
resolve, and drop every claim about meaning.

## Mechanism

`check.py` extracts prose (comments and docstrings for Python via `ast` plus a
comment scan, a regex extractor for TS/TSX) and asks the tree about each
claim.

| id | claim judged |
|---|---|
| D1 | a cited repo-relative path resolves nowhere |
| D2 | a `path:LINE` citation is past that file's EOF |
| D3 | a docstring documents a parameter not in the signature |
| D4 | prose names a symbol this diff deletes the last of |
| D5 | prose asserts `NAME = <number>`, the code binds another |
| D6 | a `path:Symbol` target defines no such symbol |
| D8 | a Sphinx role or `{@link}` names an absent symbol |

D1/D2/D6 resolve against a suffix index over the tracked paths, which is one
`git ls-files` and no file parsing. D3 is per-file. D5 puts its question to
one batched `git grep` for the names the judged prose actually mentions. D8
resolves against a whole-tree token index built by reading the tracked files
once with their prose stripped — batching greps was the first design, and it
dies with an argument-list limit as soon as one file cites a few hundred
names. D4 needs a diff and is inert without `--staged`.

**Both sides come from the git INDEX** — the prose judged and the tree it is
resolved against. Reading a peer's unstaged edits would report findings the
author cannot fix by changing their own work, and an unstaged definition would
silence findings the commit does contain. A gitignored overlay has no index
entry by construction, and prose naming one is correct prose, so
`Index.resolves` asks `git check-ignore` about a citation the index lacks:
the rules answer the same in the real checkout, a clone and a CI worktree,
where the disk holds no overlay. The one deliberate disk read left is the
existence test after that, for a path neither tracked nor ignored.

**At a real commit, D1/D2/D3/D5/D6/D7/D8 are further scoped to the lines this
commit ADDS or REWRITES** (`git diff --cached`, the same walk D4 already did).
A staged file's untouched prose can carry stock a whole-tree adoption sweep
already counted in `.amg-hooks-debt`; judging it again at commit time would fail an
unrelated change for debt the sweep tolerates, on a line the author did not
write. A sweep (`AMG_HOOKS_SWEEP=1`) stays whole-file: nothing is staged then, so a
diff-based restriction would silence every finding rather than narrow them.
D4 is unaffected — it already reasons about the diff and already excludes
lines the commit touches, on the opposite ground that a rename the same
change explains is not drift.

The checker is split into sibling modules (`_config`, `_gitio`, `_prose`,
`_cites`, `_resolve`) under the 600-code-line module cap, imported by plain
name because a script's own directory is on `sys.path`. The dispatcher port
(`dispatch.py`) shares `_config` and `_prose` with it unchanged and owns
`_dispatch_gitio`, `_dispatch_cites` and `_dispatch_resolve`, whose I/O is
rewired onto the dispatcher's `Services`; it imports all five relatively,
each hook being loaded as its own package.

## Stock

**The stock is now zero.** Measured 2026-09-10 over research-monorepo at
`8d88939e0`: `--summary` reports 0 findings in every sub-check (D1-D8, D7 not
run by default) across 1494 source files judged against 3871 tracked paths,
2.9 s direct and 6.1-6.7 s through lefthook's whole-tree lane. The shipped
invocation is scoped to the staged files and costs **0.6 s**, of which 0.5 s is
the token index D8 needs; without D8 the checker is 55 ms.

The 15 findings this section used to record were paid off, not tuned away:

| id | n | what they were |
|---|---|---|
| D2 | 4 | two files split; the cites kept the old lines |
| D3 | 1 | a parameter that moved into a tuning dataclass |
| D8 | 10 | dotted and bare symbols that no longer existed |

All 15 were read one by one and all 15 were true — a 0% false-positive rate on
a small denominator, small **because** tuning removed the classes that
produced volume rather than because the check is narrow. Across five rounds 56
findings were classified by hand; the rounds removed tracked-only path
resolution (11 of 19 early findings were gitignored overlays), the general
identifier question, docstring indent confusion, counterfactual prose, and
self-documenting renames.

The hook still judges only the staged files at commit, and (per the scoping
rule above) only the lines a commit touches within them; the no-argument
whole-tree mode is the sweep, and it is what measured the zero above. A stock
of zero is the condition for flipping this hook to a whole-tree gate, which is
a decision this README does not take on its own.

## Fragility

| refactor | effect and guard |
|---|---|
| source globs repointed, pool empty | exit 2, judged nothing |
| the token index reads nothing | exit 2, index is empty |
| a typo in `--only` | exit 2, unknown sub-check |
| `GIT_INDEX_FILE` from the hook | every `GIT_*` var is scrubbed |
| history markers grow | ordinary English, pinned by fixtures |

No checkout at all is the one environment verdict: `skipped: not a git
checkout` and exit 0, because with no index and no tree there is nothing to
say about a commit. Every other way of seeing nothing stays exit 2.

The remaining honest fragility is D8's precision, which rests on the words
that ATTRIBUTE a symbol elsewhere ("the SDK's `:func:`..."), matched over the
citing line and the one above it. A vendor whose name is not in that list
produces a finding — loudly, not silently.

## Residue

Comment/code MEANING is dropped: "this function retries three times" beside
code that retries five is undecidable, and it is the rule's core claim.
Adjacency goes with it — the rule speaks of the *adjacent* comment, and
binding a comment to the statement it describes is itself the undecidable
part, so prose is judged wherever it sits in the file.

D7, the general "is this identifier defined anywhere" question, is
implemented and off. Measured in order: 6751 findings with bare CamelCase
admitted (366 `OpenRouter`, 193 `GitHub`), 578 with only backticked names, 7
restricted to unambiguous call form — of which exactly one was drift. English
capitalises product names the way code capitalises classes and no repository
index separates them. D8 is what survives of the idea: the same question,
asked only where prose has declared the name to be code.

Numeric assertions inside counterfactual prose are deliberately not judged.

The rule's own `scripts/stale_test_paths.py` is a strict subset of D1 — it
greps for `tests/test_*.py`-shaped strings and checks existence — and reports
nothing on the tree today. D1 covers the same strings for every extension and
directory, and D8 catches the dotted form it cannot see, which is where two of
the stock findings live. Deleting it is a separate owner decision and is not
done here.
