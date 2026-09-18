<!-- hook: presets-fixture-drift -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |
# Before a commit that touches the preset YAMLs, the run-config projection or the real-presets fixture, the fixture still equals the catalog the server would return

Was the `presets-fixture-drift` pre-push lefthook command from 2026-09-03
until amg-hooks dropped the pre-push stage entirely (owner decision:
amg-hooks is pre-commit only) and it moved to pre-commit.
`real-presets.fixture.json` is the REAL catalog that
`match-preset-key-real-catalog.test.ts` measures `matchPresetKey` against,
and a snapshot is only ground truth while it matches its source. It drifted
once already: max/ultra gained `image_model: pro` while the fixture had no
`image_model` key at all, so two of the four presets were tested against a
catalog no server would return — and the suite stayed green, which is
exactly why a test could not catch this and a gate has to. Same shape and
cost as `rule-openapi-drift`: dict equality, Django boot, ~4 s, well inside
the 5 s commit-hook target, and it fires only when the preset YAMLs, the
projection or the fixture itself are staged, same glob as before.

In all-mode it exits 0: ci.yml's python group runs
`scripts/lint/check_presets_fixture_drift.py` as an explicit step, the CI
witness this rule names.

Delete-check: delete when the test reads the catalog from the server's own
projection instead of a committed snapshot — then there is no fixture to
drift.
