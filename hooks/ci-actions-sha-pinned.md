<!-- hook: ci-actions-sha-pinned -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |
# Every `uses:` in a tracked GitHub workflow names a 40-hex commit sha, with the version in a trailing comment

A tag is a mutable pointer. `actions/checkout@v4` is whatever the `v4` tag
points at when a runner resolves it, so whoever takes the action repository —
or just re-points its tag — moves every consumer at once. The
`tj-actions/changed-files` compromise of March 2025 retagged roughly 23000
repositories' `@v35` onto a secret-dumping commit without a single one of them
changing a line. A sha cannot be moved that way: the only path is a diff
someone has to write and review.

The readable version is not lost, it moves into a trailing comment —
`uses: actions/checkout@11d5960…  # v4.4.0` — and this check REQUIRES it. A
bare sha is unreadable and nothing would ever bump it; both Dependabot and
Renovate read and rewrite exactly that shape.

Two `uses:` forms are exempt, because neither resolves a tag: a local action
(`./…`, which ships inside this very commit) and a digest-pinned container
(`docker://…@sha256:…`).

Scope is the tracked tree rather than the staged files because the population
is tiny — one file in research-monorepo — and a pin that regressed through any path
should block the next commit, not wait for that file to be touched.

## Timing

Measured on 2026-09-16 against research-monorepo (one workflow, 12 `uses:` lines):
**0.09 s cold, 0.05 s warm.** There is no cache: the whole population is one
`amg-hooks-ls-files` call and one pass per file.

Fix when blocked: resolve the tag once and pin it.

```bash
gh api repos/<owner>/<repo>/commits/<tag> --jq .sha
```

then write `uses: <owner>/<repo>@<sha>  # <tag>`.

Delete-check: tool-enforced, cannot delete. research-monorepo's workflow is
`workflow_dispatch`-only with a read-only `GITHUB_TOKEN` and consumes no
repository secret, so the blast radius is small TODAY — and that is exactly
the property a later `pull_request` trigger or a first `secrets.` reference
silently removes, with no diff anywhere near this line.
