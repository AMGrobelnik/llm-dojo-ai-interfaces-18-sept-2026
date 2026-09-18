<!-- hook: detect-private-key -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# No tracked file contains a private key block

Uses the bare `detect-private-key` binary from the pre-commit-hooks
package (`uv tool install pre-commit-hooks==5.0.0` puts its console
scripts on PATH), skipping uvx's per-run package-resolve overhead.

Whole tree (owner directive, 2026-08-22): a credential-shaped file
anywhere in the stock blocks, not only newly staged ones — a key in
DEEP history remains gitleaks' job. The `[ -f ]` filter in the command
is load-bearing: the binary open()s each path, so a bare `git ls-files |
xargs` crashes on tracked-but-deleted paths mid-refactor. rule-rumdl and
rule-shfmt carry the same filter for the same reason. A one-time
full-tree sweep at adoption confirmed 0 private keys present then.

Self-scoping: an empty file list makes `xargs -r` a no-op (pass). The
trailing `rc` mapping turns xargs' 123 (some invocation found a key)
into the engine's block exit code and passes infra codes through.

Fix when blocked: keep the key OUT of the repo — reference it from a
gitignored path or a secret store. There is no legitimate reason to
commit a private key; do not allowlist one.

Delete-check: tool-enforced, cannot delete — a committed private key is
unrecoverable once pushed (history rewrite plus rotation), so the cheap
pre-commit gate is strictly better than the cleanup.
