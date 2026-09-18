<!-- hook: worktree-fresh -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 1s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: no RULES_* vars read
# A worktree whose base is more than WORKTREE_FRESH_MAX_S behind the upstream tip fails the commit, naming the fix, instead of surfacing as a merge conflict later.

## Why

Working from more than one worktree of the same repo, this repo's own README
already says, is safe by default for the SHARED lock lefthook takes across
them. It says nothing about each worktree's own base going stale: a worktree
branched days ago and never fetched drifts further from `origin` every
commit that lands there, and the first sign is a merge conflict when it
finally does catch up — after the diff has grown, with no line pointing back
at "you were behind the whole time." Surfacing the gap at commit time, before
the conflict, is strictly cheaper to act on: `git fetch origin && git merge
origin/<branch>` while the drift is a day is a fast-forward or a small merge;
the same command a week later is a real conflict.

## Mechanism

`check.sh` resolves the worktree's upstream the same way git itself would —
`@{upstream}` if the branch tracks one, else `origin/HEAD` (the remote's
default branch symref), else whichever of `origin/main` / `origin/master`
this remote actually carries — and compares two COMMITTER dates: the
`git merge-base HEAD <upstream>`, and the upstream tip itself. Committer
date rather than author date, and rather than a fetch/receive timestamp: it
is the one date recorded on the commit itself that says when the base
entered mainline history, immune to a rebase or a slow local commit backdating
it, and it needs no network call — the periodic `amg-hooks-fetch` timer this
repo already runs keeps `refs/remotes/origin/*` current, so a whole-tree
`git merge-base` and two `git show -s --format=%ct` calls are all this check
ever does.

`WORKTREE_FRESH_MAX_S` (default 86400, one day) is the gap the two dates may
differ by. Past it, the message names the base (short sha), the upstream tip
(ref and short sha), the age in hours, and the fix:

    worktree base <base> is <N>h behind upstream tip <upstream> (<tip>): git fetch origin && git merge origin/<branch>

## Skip conditions

Four cases exit 0 with no message, each because the alternative would refuse
the exact commit that fixes the problem, or because there is nothing to
compare:

- **no remote** (`git remote` prints nothing) — nothing to be stale against.
- **no upstream ref** — no `@{upstream}`, no `origin/HEAD`, no `origin/main`,
  no `origin/master`; same reasoning.
- **an in-progress merge** (`git rev-parse --git-path MERGE_HEAD` names a
  file that exists) — the commit that lands the merge IS the fetch-and-merge
  this rule would otherwise demand; nothing to warn about before it lands.
- **`GIT_REFLOG_ACTION` starts with `merge `** — git's own tell for an
  automatic merge-to-commit path (measured against git 2.1.9 by
  `commit-uses-a-named-file-list`, this repo's other consumer of the same
  variable: unset for a plain commit or `--only`, `merge <name>` only here).
  Kept as a second, independent door alongside the `MERGE_HEAD` check because
  the two cover different moments — `MERGE_HEAD` exists only while conflicts
  are unresolved and is gone by the time the merge commit itself runs
  pre-commit, which is exactly when `GIT_REFLOG_ACTION` fires.

No network call is made anywhere in the check: a stale local clone of
`refs/remotes/origin/*` cannot be told apart from a genuinely stale worktree
by design, which is what keeps the fetch timer's 2-minute cadence, not this
hook, responsible for freshness of the remote-tracking refs themselves.

## Fragility

| change | effect | guard |
|---|---|---|
| no remote configured at all | skip | intended: nothing to compare |
| detached HEAD with no upstream and no origin/main or origin/master | skip | intended |
| `merge-base` fails (unrelated histories, shallow clone missing the tip) | skip (exit 0 rather than exit 2) | a worktree the check cannot reason about is not one it should block |
| a very long-lived feature branch, legitimately behind for good reason | still fires | raise `WORKTREE_FRESH_MAX_S` or set `skip: true` in `.amg-hooks-exclude`-style root override for that command |
