<!-- hook: gitignore-tells-truth -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# The .gitignore and the index never contradict each other: no tracked file matches an ignore pattern, and every ! negation re-includes a tracked file or is recorded as dead.

(Statement trimmed under 200 chars 2026-08-28; the mechanical form of the
first half is `git ls-files -i -c --exclude-standard` returning empty, and the
recorded-dead caveat is the implemented mechanism's own semantics — see
IMPLEMENTED below: 11 negations, 2 dead and both recorded, and a live negation
recorded as empty is reported as stale.)

(Superseded 2026-08-26: direction (a) is CLEAN, and 4 of the 6 dead negations
were fixed rather than recorded. See IMPLEMENTED at the end.)

Both directions are violated right now. (a) .claude/projects/-home-<user>-
projects-research-monorepo/memory/ui_design_sidebar_reference.md is tracked (since
42e0689e0) while .gitignore:322 ignores .claude/projects/ as 'Claude Code per-
machine runtime state (never tracked)' — a session-memory file living in
history. (b) 6 of the 13 negation lines are dead, measured against git ls-
files: :13 !aii_server/**/lib/ (0 matches), :14 !inperson_agent/**/lib/
(inperson_agent has 0 tracked files), :73-74 two .gitkeep negations naming
untracked files (ineffective per the re-include-under-ignored-dir quirk the
file itself documents at :121-123), and :125+:127 — the /image-gen/<private-dir>-
processes/ carve-out silently overridden by /image-gen/ at :331, so
_bypass_gen.py is NOT tracked despite prose at :121 claiming it 'stays in
git'. That override pattern is the unique gitignore failure mode: a later line
kills an earlier negation with no warning. The public export depends on
negation liveness (.gitignore:172-174: 'without its negation the public export
loses a file it asserts on'). Distinct from killed rule-gate-scopes-live
(lint-gate pathspecs, different object) and pending rule-fe-exclusions-live
(FE tool configs) and pending rule-private-config-never-tracked (two pinned
globs only): this rule checks git's own tracking semantics with git's own
machinery, and catches the negation-override quirk neither of those can see.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: git-repo-hygiene)

Proposed command (implemented at approval):

    bash scripts/gitignore_truth.sh  # SUPERSEDED — built as one python
    # scripts/gitignore_truth.py doing both parts. part 1: test -z "$(git ls-files -i -c --exclude-standard)"; part 2: python scripts/negations_live.py — fnmatch each '!' line (gitignore semantics: no-slash patterns match any depth, dir patterns get /** appended) against git ls-files -z

Delete-check: Every current violation is fixed by deletion — git rm --cached the memory file
(relocate its content to a tracked docs path if wanted) and delete the 6 dead
negation lines including the false :121-127 stanza. The rule enforces that
deleted end-state; the /image-gen/ override proves recurrence is real, not
hypothetical.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Both directions violated right now (tracked file under an ignored
path, dead ! negation), verifiable in one git ls-files pipeline, and no
claimed rule covers general index-vs-ignore consistency (rule-private-config-
never-tracked is two specific globs). Fix the violations by deletion when
landing, per its own analysis.
- KEEP: Both directions violated right now, two stock git commands,
generalizes pending private-config-never-tracked without duplicating its
specific files.
- KEEP: Both directions violated right now; git ls-files -i -c --exclude-
standard is a one-liner and the dead-negation half is implementable by testing
each ! pattern against the index. Loud, closed, no overlap with pending rule-
private-config-never-tracked (specific globs vs whole-file contradiction).

STATUS (2026-08-22): the one contradiction the verifier confirmed is
FIXED. `.claude/projects/` was a blanket ignore whose comment said
"never tracked", while
`.claude/projects/*/memory/ui_design_sidebar_reference.md` was tracked
and had been deliberately committed twice (42e0689e0, 574e1983e) — a
curated design reference, not per-machine runtime state. Untracking it
would have destroyed intent, so `.gitignore` now admits it instead.
The naive negation is silently inert here (git cannot re-include a file
whose parent DIRECTORY is excluded), so the entry uses the
descend-then-exclude form and was verified in a scratch repo with
`git check-ignore`: memory/ re-included, sibling runtime state still
ignored. That trap is worth pinning in the rule itself — an inert
negation looks correct and does nothing.


RE-MEASURED 2026-08-25 — **both figures in the body are stale, and direction
(a) is resolved in a way the body does not anticipate.**

(a) `git ls-files -i -c --exclude-standard` is EMPTY. The file the body names —
`.claude/projects/.../memory/ui_design_sidebar_reference.md` — is still tracked,
but `.gitignore:329` now carries `!.claude/projects/*/`, which re-includes it.
So the ignore and the index no longer contradict: the negation makes the
tracking legal. Whether that file SHOULD be tracked is a separate question this
rule does not decide, and the body's "a session-memory file living in history"
framing reads as an unresolved violation when the contradiction is gone.

(b) 8 of 15 negation lines re-include nothing tracked, not 6 of 13 — the file
grew and so did the dead set:

| line | negation | why it was called dead |
|---|---|---|
| 13 | `aii_server/**/lib/` | no `lib/` subtree tracked |
| 14 | `inperson_agent/**/lib/` | no `inperson_agent/` |
| 73, 74 | two `aii_pipeline/data/**/.gitkeep` | no tracked files |
| 125, 127 | `/image-gen/<private-dir>-…` | no root `image-gen/` |
| 176 | `.env.example` | names ROOT; tracked one is `aii_public/`'s |
| 331 | `.claude/projects/*/memory/` | `:329` re-includes parent |

(The last two rows are wrong — both negations are live, so this was 6, not
8; IMPLEMENTED below reconciles the count.)

A measurement trap worth stating, since it cost a wrong count first: a negation
beginning with `/` is repo-root-relative to git's ignore syntax but is NOT a
valid pathspec — `git ls-files -- /lefthook.yml` exits with "outside
repository", which reads as zero matches. `/lefthook.yml` is live. Strip the
leading slash before checking, or the check invents dead lines.

The rule cannot be gated until the 8 are removed or the statement narrows; that
is an owner call, since a dead negation is inert rather than harmful and two of
them may be placeholders for directories meant to return.
## IMPLEMENTED (2026-08-26) — (a) is clean, and 4 of 6 dead negations are gone

`scripts/gitignore_truth.py` asks git both questions with git's own semantics.
Green: **11 negations, 2 dead and both recorded, 0 tracked-while-ignored.**

**Direction (a) is clean and this body's example is stale.** It names
`.claude/projects/…/memory/ui_design_sidebar_reference.md` as tracked while
ignored; `git ls-files -i -c --exclude-standard` returns 0. That file is tracked
and re-included by the two `.claude/projects/*` negations, both live.

**Direction (b) held at 6 of 15. Four were FIXED, because they provably
protected nothing:**

- the `/image-gen/` carve-out was four lines keeping one helper re-included.
  That script is tracked 0 times and the directory is absent from disk, while
  the comment claimed it "stays in git". Collapsed to a plain `/image-gen/`,
  with a note on how to restore the carve-out if the helper returns.
- two `.gitkeep` negations could never work — git cannot re-include a file under
  an excluded directory, which this same file documents. And
  `aii_pipeline/data/runs/` is ignored by a NESTED `aii_pipeline/.gitignore`
  anyway, so they were inert twice over.

The RE-MEASURED 8 was an overcount by two, which is why 6 is not a rejection
of it: `!.env.example` (then :176, now :179) carries no slash, so git matches
it at any depth and it re-includes the tracked `aii_public/.env.example`
(`git check-ignore -v` names that exact line); and
`!.claude/projects/*/memory/` (then :331, now :334) is load-bearing, not
shadowed — the parent negation (then :329, now :332) re-includes only the
DIRECTORY, the next line `.claude/projects/*/*` excludes its contents again,
and the memory negation is what re-includes the tracked design-reference
file. Both are live by `git ls-files`, so (b) was 6 of 15 then and is 2 of 11
now.

Verified behaviour-neutral: `git ls-files -i -c` stays 0, no file changes
tracked status, no new untracked files appear, and every real path under the
touched directories resolves to the same ignore decision as before.

The two remaining are recorded, not removed. `!aii_server/**/lib/` guards a
package with 109 tracked files — zero matches today only because no subtree has
a `lib/` yet, and removing it means the next one is silently ignored.
`!inperson_agent/**/lib/` is the same shape for a package that is gone, where
removal is cosmetics rather than a fix.

Both directions are probed: a live negation recorded as empty is reported, so
the list cannot outlive its reason.

## FIXED (2026-09-14) — the `_MIN_NEGATIONS` floor now means "shape moved"

`_MIN_NEGATIONS` was written against research-monorepo's own `.gitignore` (11
negations) to catch a truncated file, but a consumer whose `.gitignore`
legitimately carries zero negations — notes-repo, for one — hit the same bail on
every commit that touched `.gitignore`, permanently, even though direction (1)
still judged fine. The floor now bails only when the shape actually MOVED:
fewer than `_MIN_NEGATIONS` negations in the staged/working file AND the
committed one (`git show HEAD:.gitignore`, 0 if there is none) had
`_MIN_NEGATIONS` or more. Zero negations before and after is not a moved
shape — the script prints a one-line note and lets direction (1) decide alone.
