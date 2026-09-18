<!-- hook: release-tag-guard -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-push | tree | 5s | active |

# A push that creates or updates a refs/tags/v* ref is refused unless AII_RELEASE=1 — every pushed v* tag is a production release to the image watcher

The one hook in amg-hooks that runs at pre-push rather than pre-commit, because
it structurally cannot run at commit: a tag push carries no commit of its own
for a pre-commit hook to intercept, and the local `aii-image-watcher` (a
systemd user service polling `origin/main` and `v*` tags) treats every pushed
`v*` tag as a production release — it builds all three images and moves the
Docker `:latest` pointer. `check.sh` is this hook's authoritative copy;
lefthook's own `scripts:` mechanism resolves the executed file at
`.lefthook/pre-push/release-tag-guard.sh` in the consumer regardless of which
`lefthook.yml` (root or extended) declares the entry, so the consumer keeps
that path in sync with this file rather than duplicating the logic.

Git hands pre-push the refs being pushed on stdin, one
`<local-ref> <local-sha> <remote-ref> <remote-sha>` line per ref
(githooks(5)); the `scripts:` entry below is registered with `use_stdin:
true` so lefthook forwards that stdin to the script. Deletions (all-zero
local sha) pass without the override, so a bad tag can always be removed;
branches and non-v tags (`archive/*`) are untouched.

The one intentional path, the release-tag push inside `aii_launcher
--redeploy` (`deploy.py redeploy()`), sets `AII_RELEASE=1` for exactly its
own `git push`; `scripts/local/redeploy_detached.sh` wraps that launcher.

Why this must be a lefthook SCRIPT, not a command: lefthook skips every
pre-push COMMAND when the push-files diff (`git diff --name-only HEAD
@{push}`) is empty — a bare tag push of an already-pushed commit is exactly
that case, measured landing a real `git push origin refs/tags/v9.9.9` with a
command-based guard silently skipped. Scripts are exempt from that skip
(verified against lefthook 2.1.9).

This is the release safety net, not a place to add more checks: amg-hooks
otherwise has no pre-push stage (owner decision) precisely because "slightly
better at push" is not a reason to leave pre-commit — this hook exists only
because a tag push has no commit to gate.

Delete-check: delete when the image watcher stops treating `v*` tags as
releases (e.g. releases move to an explicit dispatch), at which point a
stray tag ships nothing.
