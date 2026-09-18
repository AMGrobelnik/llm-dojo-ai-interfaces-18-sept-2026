# A skeleton's cites resolve, and a subject edit reaches its skeleton

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 1s | active |

## Why

The agent rule this replaces fired on **every** frontend commit: its condition
was `git diff --cached --name-only -- 'aii_frontend/' | grep -q .`, and each
firing asked for a whole-tree parity review. Replayed over the last 150
frontend commits, the mechanical trigger here fires on **6**. That 25x
narrowing is the point — the judgement half stays with the agent, but it is
asked far less often and it is handed the pair to look at.

What the nine-pass campaign kept rediscovering by hand is what got converted:
eight commits in five days moved a subject while its skeleton stayed put, and
two of them (`931b88dc3`, `86c732deb`) moved 14 and 3 cites without touching
the prose that pointed at them.

Replayed out of git objects, the historical twin map catches **4 of 8** of
those commits; today's cite graph catches **8 of 8**. The four it adds are the
ones the rule body predicts, where the map resolves a consumer while the real
subject is named only in prose.

## Mechanism

`check.py` reads the skeleton modules named in `CONFIG`, follows every
`_<stem>/` part they re-export, and builds the cite graph out of the comments
inside each export's own span.

| finding | what it is |
|---|---|
| A | a cite whose target file does not hold that line |
| B | a cite whose target line moved in this change |
| C | a layout-bearing subject edit, twin body unchanged |
| D | `Skeleton` not at the end of an export name |
| E | an export with no consumer and no cite |

B is the one the campaign paid for: a HEAD-to-index line map over the changed
subject, reporting a cite the change left alone whose target has moved.

A cite is matched to the changed file by PATH, through the same
`resolve_cite` A uses, and only when that resolution is unambiguous. Matching
on basename alone reported two correct cites — `trace/page.tsx:19` and
`r/[runId]/page.tsx:37` — as stale against a one-line comment added to
`app/login/page.tsx`, because 24 tracked files are named `page.tsx` and the
ambiguity guard passed whenever the changed file was merely one of them. 219
of the 222 resolvable cites name their file unambiguously; the other 3 are
unqualified basenames and B stays silent on them, since nothing in the cite
says whose line moved.

Two resolutions find the twin of a changed subject, and their union is what
scores 8 of 8: the changed file's own mentions of skeleton exports, and the
cite graph read backwards. Neither is a hard-coded pair list.

The judged snapshot is the git INDEX on both sides — the skeleton prose and
the subject it cites. A hook runs in a checkout other people are editing, so
a peer's unstaged edit must not create or silence a finding in this commit.

## Stock

Whole tree, at HEAD: **0 findings**, 0.49-0.51 s. One changed component costs
0.14 s, which is what the hook actually pays.

The population is real rather than empty: 224 cites across 3 home modules
(137 in `page-skeletons.tsx`, 53 in `skeletons.tsx`, 34 in
`_page-skeletons/review.tsx`) naming 52 distinct subject files. 219 of the 224
resolve to exactly one tracked file; 3 are ambiguous basenames and 2 name a
dependency. All 17 exports end in `Skeleton`, and every unpaired export cites
a subject.

Because A and B guard a convention that landed after both cite-moving commits,
they were measured by injection instead: 219/219 stale cites and 216/216
dangling cites caught in a sandbox, with a clean negative control.

## Fragility

| refactor | effect and guard |
|---|---|
| skeleton modules move | `--skeleton-module`; floor exits 2 |
| a module splits | `_REEXPORT` follow, pinned by a test |
| the cite convention lapses | exit 2, the convention is gone |
| the frontend moves | `--frontend`; empty set exits 2 |
| a cite names a dependency | skipped by `DEP_PREFIXES` |

Four of those are exit 2 rather than a quiet pass, which matters here more
than usual: this rule's recorded history is of guards that were green and
checking nothing. A cite written parenthesised was exactly that — `(` is a
legal path character for Next.js route groups, and a capture that swallowed
the opening paren left 168 of 224 cites unresolved while the check still
exited 0.

## Residue

Layout parity itself stays an agent check: heights, unit mixes,
`max(rem,px)` against `calc(rem+px)`, elements that cost no layout. So does
"was this change structural?" — C's layout-token test is a proxy, and reading
its six fires by hand, three are drift and three are popover chrome that costs
the skeleton nothing.

The JSX-open count is deliberately not converted; the rule body proves it is
directionally incapable, because the count is a signature of the skeleton's
own shape and sits still exactly when a subject drifts. Runtime-assembled
class names are already guarded elsewhere at 976/976 and are not duplicated
here. Ambiguous cite basenames resolve permissively rather than being
reported. A cite that was wrong when written is not detectable from a line
map.
