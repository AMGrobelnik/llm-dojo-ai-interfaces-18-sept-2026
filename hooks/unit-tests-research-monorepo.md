<!-- hook: unit-tests-research-monorepo -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | — | active |

# The unit-test groups whose trigger paths are staged run in one pytest process

No dedicated `README.md` exists for this lane — it is documented here from its
`lefthook.yml` comment, since it is a plain run-script invocation rather than
a `dispatch.py`-owned check folder.

The groups live in the consumer's own `tests/unit` tree, not the hooks
submodule, so the run script's root argument carries no `{amg_hooks}` prefix:

    python3 {amg_hooks}/lib/amg_hooks/run_groups.py tests/unit {staged_files}

`run_groups.py` is the same shared group-runner the general set's own
unit-test lanes use — only the root it is pointed at differs. It inspects the
staged file list, resolves it against each test group's declared trigger
paths, and runs exactly the groups whose trigger paths are staged, in one
`pytest` process rather than one process per group.
