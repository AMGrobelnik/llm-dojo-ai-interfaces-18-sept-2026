# A commit subject does not openly join two concerns

| stage | scope | budget | status |
|---|---|---|---|
| commit-msg | file | 1s | active |

## Why

A commit that carries two concerns defeats bisection, makes churn analysis
guesswork, and leaves no single scope that fits — so the conventional-commit
vocabulary cannot be closed while subjects keep joining things.

The rule body measured it: over a rolling six months, **440 of 3,149**
subjects contained `" + "`, and the worst of them touched **862 files**
(`c5bab7cb6d38`). Re-measured two days later the window had gained 152
commits while joined subjects fell by 9 — the census moves that way only if
what enters complies better than what ages out.

The agent lane then spent 860 applications and 444 blocks on it. Every
recorded PASS argued one of two things — "one line, no second change
possible", or "the other packages are mechanical fallout" — and every one
ended with the same clause: *the subject carries no joiner*. That clause is
one regular expression over one line of text.

## Mechanism

`check.py` reads the subject line of the commit message file lefthook hands
it as `{1}` (the first non-comment, non-blank line), strips the
conventional-commit prefix, neutralises arithmetic uses of `+`, and matches a
closed list of three joiner shapes.

| failure mode | mechanism |
|---|---|
| `one thing + another thing` | `\s\+\s` after prefix strip |
| `... and also ...` | word-bounded `and also` |
| `misc cleanups` | word-bounded `misc` |
| `feat(api+frontend):` scope | prefix stripped before the scan |
| `at 320 + 200%`, `L133 + L143` | both operands numeric: discounted |
| `Merge`/`Revert`/`fixup!`/`squash!` | git-generated, exempt |
| joiner in the body, not the subject | only the subject is read |

With no argument the checker sweeps the last 300 subjects — the history
analogue of a whole-tree pass, since a commit message is not a tracked file.
`--history N` widens the window. It reads no tracked file, so there is no
index-versus-worktree distinction to get wrong.

Six commit rules are already subsumed by the sibling well-formed-commit
hook; this is a natural seventh member and is not in that table today.

## Stock

Measured against `/home/<user>/projects/research-monorepo` at `3f1060fa7`:

| window | subjects | flagged |
|---|---|---|
| last 100 | 100 | 0 |
| last 300 | 300 | 0 |
| last 1000 | 1000 | 0 |
| all history | 4525 | 496 |

**Zero in the last 1000 commits**, so the gate blocks nothing today: the
invariant is already trained in and this is a ratchet, not a backlog. The
496 across all history are immutable — past subjects cannot be edited — so
they are a census, not debt to work off.

Runtime: 0.03 s for the 300-subject sweep, 0.18 s for all 4,525, 0.04 s for
one message file (the only mode that runs at commit time).

## Fragility

| refactor | effect | guard |
|---|---|---|
| a join phrased otherwise | walks past | one CONFIG list |
| subject grammar moves | a scope reads as a joiner | CONFIG prefix |
| a subject does arithmetic | false positive | numeric discount |
| wired without the message | nothing to read | exit 2 |
| the repo has no commits | sweep sees nothing | exit 2 |

Rows two and three are pinned by tests: `feat(api+frontend):` must pass, and
so must the four real arithmetic subjects. A hook wired without `{1}` exits 2
rather than passing silently, and so does a sweep over an empty history.

The first row is deliberate. The rule's own delete-check
says a bare grep "would just train different phrasing", which is true and is
the reason the diff half below is dropped rather than approximated: what
survives is a gate on the honest spelling, not a claim to catch every
two-concern commit.

## Residue

The other half of the rule's FAIL clause — *the staged diff contains a
second change materially unrelated to the named concern* — is dropped, not
approximated. The obvious proxy (cluster the staged files by top-level
directory, flag more than N clusters) was built and run over the last 300
non-merge commits: **69 (23%)** tripped it, and of the fifteen sampled and
read in full, **none** carried two unrelated concerns. Every one was the
rule's own explicit PASS case — mechanical fallout landing across packages
as one coordinated change — and the biggest single driver was that a commit
which also documents a rule touches the rules tree, which is not a second
concern. A 23% false-positive rate on a commit gate trains people to work
around it.

Also not attempted: judging whether two things named in one subject really
are related, and the waiver the rule allowed for genuinely inseparable
cross-cutting changes. Both need the diff read for meaning.
