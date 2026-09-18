<!-- hook: openapi-drift -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |
# Before a commit that touches backend source or the committed OpenAPI snapshot, the snapshot still equals what the server generates

Was the `openapi-drift` pre-push lefthook command from 2026-09-03 until
amg-hooks dropped the pre-push stage entirely (owner decision: amg-hooks is
pre-commit only) and it moved to pre-commit. It regenerates the BE schema from
working-tree source (offline, light boot — no DBOS, workers or daemons) and
fails when the committed `aii_frontend/lib/api/openapi.json` no longer
matches: someone changed an API shape and forgot codegen, leaving the FE's
generated client typechecking against a stale contract. Dict-equality
comparison, so formatting and key order cannot false-positive. ~4 s
(a Django boot plus ability discovery for the full route set), well inside
the 5 s commit-hook target, and it fires only when BE-schema-relevant files
are staged, same glob as before.

In all-mode it exits 0: ci.yml's python group runs
`scripts/lint/check_openapi_drift.py` as an explicit step, which is the CI
witness this rule names (`rule-ci-coverage-parity` checks that step still
exists). `rule-openapi-snapshot-integrity` is the commit-time companion:
byte-identity of the snapshot and a refresh that can never shrink it.

Delete-check: delete when codegen runs unconditionally at every commit
(the snapshot regenerated rather than diffed), at which point a commit
cannot carry drift by construction.
