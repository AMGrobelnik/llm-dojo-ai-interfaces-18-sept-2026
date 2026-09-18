<!-- hook: fe-unit-tests-research-monorepo -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | — | active |

# The FE vitest groups whose trigger paths are staged run in one vitest process

No dedicated `README.md` exists for this lane — it is documented here from its
`lefthook.yml` comment, since it is a plain run-script invocation rather than
a `dispatch.py`-owned check folder.

The groups come from this repo's own `aii_frontend/tests/unit` tree:

    python3 {amg_hooks}/lib/amg_hooks/run_groups_fe.py aii_frontend/tests/unit {staged_files}

`run_groups_fe.py` is the vitest counterpart of `run_groups.py`: it inspects
the staged file list, resolves it against each FE test group's declared
trigger paths, and runs exactly the groups whose trigger paths are staged, in
one `vitest` process rather than one process per group.
