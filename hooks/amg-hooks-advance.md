<!-- hook: amg-hooks-advance -->

| stage | scope | budget | status |
|---|---|---|---|
| post-commit | tree | — | active |
| post-checkout | tree | — | active |
| post-merge | tree | — | active |

# Advances the vendored hooks submodule's working tree, now that the gate is over

No dedicated `README.md` exists for this lane — it is documented here from
its `general/lefthook.yml` comment, since it is a plain invocation rather
than a `dispatch.py`-owned check folder.

`amg-hooks-advance-stage` (`pre-commit`) pins the vendored hooks submodule at
the sha the commit is about to judge, without moving the working tree. Once
the gate is over, moving the submodule changes nothing about what the commit
already recorded — it is what lets the *next* commit pick up newer hooks. A
fresh clone, a branch switch or a pull is the other moment the submodule may
need to move, so the same advance also runs at `post-checkout`.

    run: '[ -f {amg_hooks}/tools/amg_hooks_advance.py ] && python3 {amg_hooks}/tools/amg_hooks_advance.py --checkout || true'

Never fails a commit, checkout or merge — a missing `amg_hooks_advance.py`
(an older submodule pin) is a silent no-op.
