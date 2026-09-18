<!-- hook: check-added-large-files -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# No tracked file exceeds 100 MB, anywhere in the index

`check.sh` sweeps the WHOLE index: `amg-hooks-ls-files -z` piped through
`stat -c '%s %n'` and an awk threshold of 104857600 bytes. It no longer
shells out to the `check-added-large-files` binary from the pre-commit-hooks
package — the slug is inherited from that tool, not a description of what
runs.

It is no longer staged-only either, and the flip is recorded in the script's
own header comment (2026-08-22, "from added-only"): `git ls-files` already
includes staged-new files, so the pre-commit case is covered by the same
sweep, and the sweep additionally catches a blob that reached the index some
other way. The old `--diff-filter=A` intersection is gone with the binary.

Self-scoping: an empty listing makes `xargs -r` a no-op, so a repo with no
tracked file passes rather than erroring. `stat` failures on a path tracked
but absent on disk are discarded — absence cannot be oversize — and awk's
own exit status is what blocks.

Fix when blocked: do not commit the file — large artifacts go to object
storage / releases / LFS, with a pointer or download step in the repo. If
a file genuinely must be tracked at this size, that is an owner decision,
not a limit bump in passing.

Delete-check: tool-enforced, cannot delete — a >100 MB blob is
un-pushable to GitHub and permanent in history once committed, so the
gate must sit before the commit.
