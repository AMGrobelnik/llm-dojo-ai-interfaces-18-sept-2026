<!-- hook: actionlint -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_STAGED
# Workflow files under .github/workflows/ pass actionlint

Static checker for `.github/workflows/*`. `check-yaml` only proves the
file parses as YAML; actionlint validates it against the real Actions
schema (job/step keys, `needs:` refs, matrix expansion, `${{ }}`
expression syntax, deprecated `set-output`) AND runs shellcheck on every
`run:` block — embedded shell that the `.sh`/`.bash`-only shellcheck
rule never sees. ~20 ms; scoped so it only fires when a workflow file is
in the checked list (at commit: only when a workflow changed; in
all-mode the tracked tree always contains them, so it always runs).
Install once: download the static binary from
https://github.com/rhysd/actionlint/releases onto PATH.

Fix when blocked: actionlint names file, line and the schema or
shellcheck finding — fix the workflow there. Note this repo's workflows
are replayed by local watchers, not dispatched on GitHub, but the
definitions must still be valid.

Delete-check: tool-enforced, cannot delete — a workflow file is config
whose only other validator is a live Actions run, which this repo
deliberately never performs.
