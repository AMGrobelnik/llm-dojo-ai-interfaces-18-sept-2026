<!-- hook: merge-commit-runs-pre-commit -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-merge-commit | tree | — | active |

# Re-runs the whole pre-commit gate on a clean, non-conflicting merge commit

No dedicated `README.md` exists for this lane — it is documented here from
its `general/lefthook.yml` comment, since it is a plain re-invocation rather
than a `dispatch.py`-owned check folder.

git runs `pre-merge-commit`, never `pre-commit`, for a merge that resolves
without conflicts (`git merge`'s automatic path straight to a commit) — a
merge commit made that way skips the whole `pre-commit` suite unless this
stage exists to re-run it. `pre-commit`'s own `skip: [merge]` does not fire
here: that skip is a `MERGE_HEAD` check, and git never writes `MERGE_HEAD` to
disk on this clean/automatic path (only when it stops for conflicts, which
never reaches `pre-merge-commit`).

    run: lefthook run pre-commit

Re-running the group by name, rather than repeating its many commands a
second time, picks up the consumer's full merged config — root overrides
plus every extended set — exactly as an ordinary `git commit` would.
`{staged_files}` inside the nested run resolves against the merge's own
tentative index, which git writes before invoking this hook.
