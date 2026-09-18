<!-- hook: snapshot-cleanup -->

| stage | scope | budget | status |
|---|---|---|---|
| post-commit | tree | — | active |
| post-merge | tree | — | active |

# Cleans up the point-in-time index snapshot the pre-commit commands shared

No dedicated `README.md` exists for this lane — it is documented here from
its `general/lefthook.yml` comment, since it is a plain cleanup invocation
rather than a `dispatch.py`-owned check folder.

The index snapshot the `pre-commit` commands read from is reference-counted
per process and reaped when the last user lets go. `snapshot-cleanup` and
`amg-hooks-advance` are the ordinary end of a gate; a run that dies before
them leaves a snapshot the next `build()` reaps once it has been idle, so
nothing here is load-bearing for correctness — it only keeps the disk from
carrying a snapshot until the next commit.

    run: python3 {amg_hooks}/lib/amg_hooks/snapshot.py cleanup

Runs identically at `post-commit` and `post-merge`, the two points a gate can
end.
