<!-- hook: lefthook-validate -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |
# A changed lefthook.yml validates against lefthook's real schema

check-yaml only proves the file parses as YAML; a typo'd key
(`glob:` → `gob:`) silently disables the hook it configures.
`lefthook validate` checks the config against lefthook's real schema.
~12 ms, staged-only (this file changes rarely).

Self-scoping: the grep gate (NUL-aware, exact path match) reproduces the
hook's `glob: "lefthook.yml"` — the validator runs only when lefthook.yml
is in the staged list. In all-mode the tracked list contains it, so the
sweep always validates the config.

Fix when blocked: the validator names the offending key/structure — fix
lefthook.yml itself; do not commit around it, since a misconfigured hook
fails open (it silently stops running).

Delete-check: tool-enforced schema validity, cannot delete — the failure
mode of a bad config is a hook that quietly never fires.

**"which no other check observes" was too strong, corrected 2026-08-25.**
`test_ci_covers_every_pre_push_hook`, a consumer-side CI-coverage test, does
`yaml.safe_load(LEFTHOOK.read_text())["pre-push"]`, so a config that would
not parse also breaks that test. **Narrowed 2026-09-15**: amg-hooks is
pre-commit only except for `release-tag-guard` (owner decision — the one
check that cannot run at commit at all), so the generated `lefthook.yml`
still carries a `pre-push` key but with a single entry (`release-tag-guard`)
where it used to carry four; the consumer test's own coverage expectations
for the four that left pre-push (`gitleaks-outgoing` deleted,
`openapi-drift`, `presets-fixture-drift` and `vitest-fe-full` all moved to
pre-commit) need their own update once this pointer bumps (out of scope
here: the consumer repo is not edited from amg-hooks). Three cases, and only
the middle one is this rule's alone:

| a config that... | caught by |
|---|---|
| will not parse | both |
| parses but is schema-invalid | **this rule only** |
| is schema-valid but wrong | neither |

The delete-check still holds, and now for a reason that survives checking:
`lefthook validate` is the only thing that reads the SCHEMA. The third row is
the honest gap — a hook whose glob matches nothing is valid YAML, valid
schema, and silently useless.
