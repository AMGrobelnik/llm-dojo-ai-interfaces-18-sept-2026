<!-- hook: commit-subject-unrepeated -->

| stage | scope | budget | status |
|---|---|---|---|
| commit-msg | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_MSG_FILE
# A commit subject is not the subject of any of the last 200 commits — a repeat is the shared-COMMIT_EDITMSG swap, surfaced

The incident is recorded twice in CLAUDE.md ("Two agents committing at
once can SWAP commit messages", instances measured 2026-08-24 and
2026-08-25). `git commit -F` copies the message into the shared
`.git/COMMIT_EDITMSG`, the rule engine then runs for 15-20 s, and a
concurrent agent's attempt — successful OR blocked — overwrites the file
in that window. The other agent's commit lands under YOUR subject, with
THEIR content, and nothing tells either of you. The subject is wrong in the
one direction archaeology cannot recover from: it actively describes
different work.

What the swap leaves behind is a REPEATED subject. The victim lands first
carrying your subject; your own commit, minutes later, carries it again.
So the second landing is detectable at the moment it is made, by the
cheapest possible check: is this subject already in the recent log?

Measured 2026-09-03 over the last 800 commits (`git log -800
--format=%s | sort | uniq -d`):

| subject | landings | apart | shape |
|---|---|---|---|
| `docs(rules): narrow the className …` | 2 | 8 min | 9 files vs 1 |
| `docs(pipeline): the retry budget …` | 3 | 4 min | 2 files, 1, 1 |
| `chore(api): commit the client regen …` | 2 | 2 min | 1 vs 1 |
| `docs(runpod): section 7 on the new pod …` | 2 | 3 min | 1 vs 1 |

The first two are the documented instances. All four pairs landed within
minutes of each other and none was a deliberate repeat — 4 of 4 duplicates
in 800 commits are the swap. Zero legitimate repeats in the window, so the
false-positive rate the check would have had is 0 of 800.

What the check does NOT do: it cannot catch the FIRST landing (at that
moment the subject is new to the log). It catches the second, which is the
one the wronged author makes — so the person who can correct it forward is
exactly the one who is told. It complements `rule-commit-uses-a-named-file-
list`, which addresses the shared INDEX; this addresses the shared MESSAGE
file, which `--only` does not touch.

Mechanism: `check.sh` reads `RULES_MSG_FILE` (absent in all-mode → exit 0,
same self-scoping as `rule-commit-subject-length`), skips `Merge`/`Revert`/
`fixup!`/`squash!` subjects, and walks `git log -200 --format='%h%x09%s'`
for an exact match. On a hit it prints the earlier sha and the fix-forward
instruction, exit 1.

Probes, both ways (2026-09-03, scratch git repo with the exact script):

- subject equal to HEAD's → exit 1, names the sha;
- subject equal to a commit 150 back → exit 1;
- fresh subject → exit 0; `Revert "…"` of a repeated subject → exit 0;
- `RULES_MSG_FILE` unset (all-mode) → exit 0;
- a subject that is a PREFIX of an earlier one (`fix(x): a` vs
  `fix(x): a b`) → exit 0 — the comparison is whole-line, not substring.

Cost, stated plainly: one `git log -200` per commit (measured 9 ms). A
deliberate repeat — say a second "chore(deps): bump lockfile" — is blocked
and needs a distinguishing subject, which is the honest outcome: two
commits with one description are what the swap looks like, whoever made
them.

Nearest existing rules, and why they do not cover this:
`rule-commit-uses-a-named-file-list` (pending) isolates the index, not
COMMIT_EDITMSG; `rule-commit-subject-length` and `rule-conventional-commit`
judge the subject's shape, not its novelty; `rule-commit-one-concern` is an
agent rule about content.

Delete-check: delete when commits stop sharing `.git/COMMIT_EDITMSG` —
i.e. when this checkout is no longer shared by concurrent agents, or git
gains a per-process message path. Until then the swap is structural and
this is its only detector.
