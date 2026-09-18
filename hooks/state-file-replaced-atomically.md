<!-- hook: state-file-replaced-atomically -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# A state file another process polls is replaced by rename — written to `<path>.tmp`, then `mv -f` into place — never truncated and rewritten where a reader can catch it half-written

The hazard is recorded in `scripts/local/watchers/README.md` ("A reader
that caught a partial write would parse a missing counter as `0` — reading
'healthy' exactly while the job is failing") and restated in
`scripts/local/redeploy_detached.sh`, written after the 2026-08-26 redeploy
that died mid-swap. Both say the same thing: `>` truncates first and fills
second, and a reader landing between the two sees an empty or partial file
and believes it.

Re-measured 2026-09-05 over every `$STATE` / `$STATUS` writer under
`scripts/local/**` (5 files, read by hand as well as by the ERE). It was
three of six until that day, when `aii-site-watcher.sh` — a truncating
writer — was deleted along with its poll loop, publishing the rules page
having moved into `aii-ci-watcher.sh`:

| writer | form |
|---|---|
| `aii-ci-watcher.sh` | truncate in place |
| `aii-image-watcher.sh` | truncate in place |
| `redeploy_detached.sh` | tmp + `mv -f` |
| `aii-builder-keepalive.sh` | tmp + `mv -f` |
| `aii-redeploy-watchdog.sh` | tmp + `mv -f` |

Those two truncating files were read by live guards —
`test_ci_watcher_is_keeping_up.py` and
`test_image_watcher_is_keeping_up.py` both `STATE.read_text().strip()` —
so a read inside the truncate window yielded an empty sha, and the guard
built to say "the watcher is behind" said nothing instead. Both guards
still poll. What is gone is the window: see the 2026-09-14 re-measure
below.

Mechanism: the engine's `rules-grep` in added-lines form matches a
redirection whose target is `$STATE`/`$STATUS`, bare or quoted, followed by
whitespace or end of line — so a trailing `# comment` (the ci-watcher's
form) still matches, while `$STATE.tmp` does not. The pathspec
`scripts/*.sh` is git's default matching, where `*` spans `/`, so nested
watcher scripts and top-level ones are both in scope. Stock (0) as of
2026-09-14, so all-mode has nothing left to advise on: every match the ERE
reports is a NEW truncating write, and those block.

Re-measured 2026-09-14 over the consumer INDEX: **stock 0**. Both
grandfathered writers carry the rename form now —

| writer | form today |
|---|---|
| `aii-ci-watcher.sh:786` | tmp + `mv -f` |
| `aii-image-watcher.sh:502` | tmp + `mv -f` |

each of them `echo "$sha" >"$STATE.tmp" && mv -f "$STATE.tmp" "$STATE"`,
which the ERE correctly does not match. `git grep --cached
--no-recurse-submodules -nE` with the live pattern over `scripts/*.sh`
returns no output, and the search population is demonstrably non-empty:
the loose `$STATE` / `$STATUS` form still hits five files. So the zero is
a clean stock, not an empty search.

That retires the reason this hook was wired commit-lane. The old
rationale — the two truncators could only be converted by reinstalling
the INSTALLED watcher scripts (`~/.local/bin`,
`rule-watchers-installed-and-current` fails on drift), so it was a
reinstall on the build host rather than a text edit and was left to the
owner — is spent, because that conversion has landed. `--tree` is the
right form and the stock no longer argues against it.

The lane WIRED today is still commit: `general/lefthook.yml:237` carries
no `--tree`. That file has one writer, so the flip is queued for the merge
owner's next `lefthook.yml` rewrite; until it lands, this hook reads added
lines.

Probes, both ways (2026-09-03, `rules-grep` in a scratch repo with the
probes staged as added lines): `probe/hit.sh` (`> "$STATE"`) → matched,
exit 1; `probe/miss.sh` (`> "$STATE.tmp" && mv -f`) → no match, exit 0.

Nearest existing rules: `rule-cred-writes-via-store` (pending) mandates
atomic writes inside `claude_cred_manager` only; `rule-watchers-installed-
and-current` checks install parity and keep-up, not write atomicity;
`rule-durable-writes-are-one-way` is about shipped state changing by
addition.

Delete-check: delete when no guard polls a watcher's state file; today two
do.

## Ported to dispatch.py (2026-09-14)

Relocated onto the one-pass AST dispatcher (`general/hooks/state-file-
replaced-atomically/dispatch.py`); the standalone `amg-hooks-grep` line and this
hook's `glob:`-less entry are removed from `general/lefthook.yml` in the same
commit, since a `dispatch.py` folder under a set that already wires
`general-ast-checks` is auto-discovered by `lib/amg_hooks/ast_dispatch.py`.

`_CANDIDATE` is the live ERE verbatim (POSIX `[[:space:]]` -> Python's ASCII
whitespace class, `(STATE|STATUS)` -> non-capturing — the only two
translations, both identity on what they match), and `PATHSPEC` is the same
two `--` tokens the run line carries. **What the confirm step drops, and only
this**: a candidate `>` whose target sits inside a `#` comment or a quoted
string/heredoc body — text no shell executes as a redirection — read from
`lib/amg_hooks/shast.py`'s `FileFacts.in_comment_or_string`. **What it keeps**: a
bare `> $STATE` / `>"$STATUS"` outside any comment or string, which is a real
redirection in bash grammar with no other construct spelling the same
characters; the rename form (`>$STATE.tmp && mv -f`) was never a candidate
either way, since `.tmp` follows immediately and the ERE requires a
quote/space/EOL there.

Stock is 0 (recorded above), so the drop is exercised only by
`test_state_file_replaced_atomically_bites.py`'s synthetic comment/string
cases, not by any real consumer-tree specimen.

**Vacuity floor (2026-09-14):** no tracked `scripts/*.sh` file at all — the
real state of a consumer with no `scripts/` tree (notes-repo) — used to raise
`CannotRunError` (rc 2) under the whole-tree sweep, turning a vacuous scope
into a permanent red hook. It is now a clean skip (rc 0, a `notes`
advisory) instead, the same fix `failover-walk-budget` (commit 97cb0262)
applied for the identical "domain absent, not broken" shape.

### Drop-set audit against the consumer (research-monorepo, 2026-09-14)

OLD is the live ERE via `git grep --cached` over the consumer INDEX under the
live pathspec; NEW is this port under `AMG_HOOKS_SWEEP=1`.

| population (`scripts/*.sh` `:!.claude/`) | OLD | NEW | DROPS | ADDED |
|---|---|---|---|---|
| 21 tracked files | 0 | 0 | 0 | 0 |

The population is non-empty (21 files) and both sides agree on zero, so
ADDED is 0 and the port introduces no new verdict on the tree it was proven
against.

### COND-1

The live run line carries no `glob:` key — it fires through `amg-hooks-env` on
every commit — so the port reproduces that with a bare `GLOBS = ["*"]`
rather than narrowing to `scripts/*.sh`, the same choice
`tmux-launch-one-door` makes for the identical reason: a TREE-mode check
judges the whole index once triggered, so the trigger must admit everything
`PATHSPEC` can select, not just the paths one commit happens to touch. No
`lefthook.yml` glob was carried forward to narrow it.
