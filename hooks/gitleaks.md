<!-- hook: gitleaks -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |
# Staged content carries no secrets (gitleaks, repo deny-list config)

`gitleaks protect --staged` scans what is being committed. A repo hands in
its own deny-list as `GITLEAKS_CONFIG` from its root `lefthook.yml`
(research-monorepo: `aii_public/gitleaks.toml`, which extends the default rules
with `aii-personal-emails` and the `aii-private-domain` rule that keeps the
deployed dashboard's literal domain out of tracked files); without the
variable the default rule set runs.

`check.sh` drops the variable when it names a file that is not there.
gitleaks treats a config it cannot open as fatal, and research-monorepo's deny-list
is tracked privately and kept out of the public export on purpose (the
allowlist does not carry it), so a clone without it would otherwise fail on
every commit, secret or not. Such a clone scans with the default rules,
exactly as a repo that names no config does. The tests plant a secret both
ways: the fallback is a scan, not a skip.

Self-scoping: `protect --staged` reads the git index directly; no staged
changes means nothing to scan and a clean exit. This gates what is being
COMMITTED — the whole of what a push can carry, since nothing reaches a
remote without first being staged and committed here; there is no separate
push-time scan (`gitleaks-outgoing`, which duplicated this over the outgoing
range, was deleted — amg-hooks is pre-commit only).

Fix when blocked: remove the secret from the staged change and keep the
value in the gitignored `.env` (the pointer belongs in git; the value
belongs in `.env`). Allowlisting a genuine credential to get it into a
repo with a public-export path is exactly the wrong trade; allowlist
entries in the config are for false positives only.

Delete-check: tool-enforced, cannot delete. A repo with a public-export
path is one sync away from publishing an unscanned credential.
