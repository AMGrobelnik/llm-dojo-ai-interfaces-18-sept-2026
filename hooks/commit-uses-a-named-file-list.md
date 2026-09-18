<!-- hook: commit-uses-a-named-file-list -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_MODE
# In this shared checkout a commit is made with an explicit pathspec — `git commit --only -- <files>` — because a plain commit carries whatever any concurrent agent has staged.

The incident is recorded in CLAUDE.md and the engine's trap list, measured
2026-08-28: another agent's untracked test module appeared as `A` in a
staged diff nobody here had added it to — one `.git` means ONE shared
index, and a plain `git commit` publishes whatever anyone has staged into
it during your hook window, under your subject. It was noticed only
because a rule fired on THEIR file. The reflex fix is also wrong:
`git reset -- <their file>` silently drops the file from the commit THEY
are about to make. `git commit --only -- <your files>` is the form that
works for everyone at once: it builds a temporary index from HEAD plus
exactly the named paths, leaves all other staging untouched, and the rule
engine hashes that temporary index, so the verdict sha is
`sha256(git diff HEAD -- <your files>)` — computable before committing.

Mechanism — at commit time the hook can TELL the two forms apart, verified
in a scratch repo this session (2026-08-28):

- plain `git commit`: hooks run with `GIT_INDEX_FILE=.git/index` —
  basename `index`;
- `git commit --only -- <files>`: hooks run with `GIT_INDEX_FILE=
  <repo>/.git/next-index-<pid>.lock` (measured literal:
  `next-index-2498585.lock`) — the temporary index.

The command cases on that basename: `index` blocks with the fix-forward
message; any `next-index-*.lock` passes. `${GIT_INDEX_FILE:-index}` treats
an unset variable as the plain form, so an environment that hides the
variable blocks rather than waves through. `[ "$RULES_MODE" = commit ] ||
exit 0` self-scopes the rule out of the all-mode sweep, where no commit
exists to classify.

Quoting is proven against the engine's own parser, not assumed: the
frontmatter value is YAML single-quoted (the one apostrophe doubled as
`everyone''s`), and `_parse_frontmatter` imported from `.claude/skills/amg-hooks/scripts/rules.py`
reproduces the intended command byte-for-byte (`MATCHES INTENDED: True`,
2026-08-28) — the 2026-08-22 incident class where a hand-rolled quoting
mismatch made four gates pass vacuously is the reason this probe exists.

Probes, both ways (2026-08-28, with the PARSED command text):

- env probes: `RULES_MODE=commit GIT_INDEX_FILE=/repo/.git/index` → prints
  the message, exit 1; `…/next-index-12345.lock` → exit 0;
  `RULES_MODE=all` → exit 0; `GIT_INDEX_FILE` unset → exit 1;
- live-hook probe, scratch repo with the exact command as `commit-msg`:
  `git commit -m plain` → BLOCKED, exit 1, message printed;
  `git commit --only -m named -- a.txt` → landed (`f6b1191`).

Read before approving — the cost, stated plainly: **this blocks EVERY
plain commit in this checkout**, including a solo agent's tidy one, and
any flow that commits the real index (`git commit -a`, `--amend` without
paths, merge/cherry-pick conclusions driven through a plain commit).
That is the point — the shared index is unsafe exactly when it FEELS safe,
because the other agent's `git add` lands mid-hook — but it makes
`--only -- <files>` the only committing form, with the `Rules-Waive`
trailer as the audited valve for a deliberate whole-index commit. That
trade is an owner call, which is why this rule is proposed rather than
enforced.

## Replaying a commit: `cherry-pick -n`, not `cherry-pick`

A conflicted replay is the one flow that cannot simply obey the rule, and
the sanctioned route is a one-word change. Measured in a scratch repo,
git 2.43.0:

| replay | state file | `git commit --only` |
|---|---|---|
| `git merge` | `MERGE_HEAD` | refused |
| `git cherry-pick` | `CHERRY_PICK_HEAD` | refused |
| `git cherry-pick -n` | none | allowed |
| `git rebase` | `REBASE_HEAD` | allowed, and a trap |

`git commit --only` during a merge or a cherry-pick dies on
`fatal: cannot do a partial commit during a <thing>`, so the hook and git
between them leave no legal way to finish. Use:

    git cherry-pick -n <sha>      # resolve the conflicts
    git cherry-pick --quit        # only a multi-commit pick leaves state
    git commit --only -- <every path that commit touched>

`-n` is what unblocks it: with no commit to make, git records no
`CHERRY_PICK_HEAD`, so nothing forbids a partial commit. `--quit` clears
`.git/sequencer`, which a multi-commit `-n` pick does create; after a
single-commit pick there is nothing to clear and it is a harmless no-op.
Verified end to end with a peer's unrelated file staged throughout: the
replay landed exactly the named paths and left the peer's `A peer.txt`
staged and uncommitted, which is the whole point of the rule.

**A rebase is the dangerous one precisely because it is allowed.** The
merge backend records `REBASE_HEAD`, not `CHERRY_PICK_HEAD`, so `--only`
runs — and it builds its temporary index from HEAD plus the named paths,
so every path you leave out is DROPPED from the replayed commit while
staying in the index, to be swept into the next one. Measured: a replay
of a two-file commit named one file, landed one file, and left the other
staged. So during a rebase, name every path the original commit touched,
or let `git rebase --continue` make the commit.

No `CHERRY_PICK_HEAD` exemption is added to the check, and that is
deliberate: a replay inside a rebase in this checkout carries other
agents' staged files exactly as a plain commit does, so an exemption
would open the hole the rule exists to close on the one flow where the
index is most likely to be dirty.

Proposed type: **cmd-check** (inline shell, no script file) · scope:
**commit lane only** (self-scopes out of all-mode) · value: **high**
(proposer: owner-tasked, 2026-08-28; incidents 2026-08-28 ×2 — the stray
`A` file and the COMMIT_EDITMSG subject swap it compounds)

Delete-check: the dimension cannot be deleted by tooling — the shared
index is git's design, and a concurrent `git add` cannot be prevented from
here. The structural deletion (a private index or worktree per agent) is
explicitly ruled out for this checkout by owner directive; until the day
agents stop sharing one `.git`, naming the files is the only commit form
whose contents are knowable in advance, and this gate is what keeps that
from being a memory exercise.
