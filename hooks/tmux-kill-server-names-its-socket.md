<!-- hook: tmux-kill-server-names-its-socket -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# No tracked script runs `tmux kill-server` without naming a private socket (`-L name` / `-S path`) — the default server hosts every live Claude session

Measured 2026-08-29 and recorded in the global CLAUDE.md: one `tmux
kill-server` inside a test harness ended all 11 live `cc-*` Claude sessions
on the box, including the one running the harness. The default tmux server
is shared infrastructure here, not a scratch space. Inside a tmux pane
`$TMUX` is set, so a bare `tmux` — even with `TMUX_TMPDIR` — talks to that
default server; only an explicit `-L`/`-S` scopes the command to a private
one.

Two layers, deliberately: the PreToolUse guard (`.claude/hooks/
guard_destructive_git.py`) surfaces the INTERACTIVE spelling as an agent
types it, warn-only; this rule pins the TRACKED spelling so a harness or
script cannot carry the command into the tree. Stock today is zero
(`git grep -nE 'tmux +kill-server' -- '*.sh' '*.py' '*.js' '*.ts' '*.yml'
'*.yaml' ':!.claude/'` → no matches, 2026-09-03), which is why the rule runs
`--tree`: it blocks in both modes, and the first violation ever committed
surfaces as a block rather than an advisory.

Scope, and what is NOT banned: `tmux kill-session -t <own session name>`
against the default server is how the product ends its OWN run sessions
(`aii_server/dashboard/services/safety_net.py`, `aii_lib/src/aii_lib/utils/tmux.py`),
and it stays allowed — ending a named session you created is not ending the
server. The ERE requires `kill-server` to follow `tmux` directly, so
`tmux -L cc-test kill-server` and `tmux -S /tmp/x kill-server` do not
match. Files under `.claude/` are excluded because the directive's own
prose (the engine's rules, this rule's probes) has to spell the command out.

Probes, both ways (2026-09-03, via the engine's own `rules-grep --tree` in
a scratch repo where the probe files were tracked outside `.claude/`):
`probe/hit.sh` (bare `tmux kill-server`) → matched, exit 1;
`probe/miss.sh` (`-L`, `-S`, and a named `kill-session`) → no match, exit 0.

Nearest existing rules: `rule-no-pkill-by-pattern` (pending) bans
pattern-kills of processes, not tmux servers; `rule-launcher-teardown-reaps`
proves `pkill_orphans` spares the tmux daemon, which is the same value
guarded from the product side — this rule guards the scripts and harnesses
around it.

Delete-check: delete when Claude sessions stop living on the default tmux
socket (e.g. every `cc-*` launcher takes its own `-L`), at which point a
default-socket `kill-server` ends nothing that matters.

## Ported to dispatch.py (2026-09-14)

Relocated onto the one-pass AST dispatcher
(`general/hooks/tmux-kill-server-names-its-socket/dispatch.py`); the
standalone `amg-hooks-grep` line is removed from `general/lefthook.yml` in the
same commit — `dispatch.py` folders under a set that already wires
`general-ast-checks` are auto-discovered by `lib/amg_hooks/ast_dispatch.py`.

`_CANDIDATE` is the live ERE verbatim (`tmux +kill-server`, no POSIX class,
so no translation), and `PATHSPEC` is the same seven tokens the run line
carries (`*.sh` `*.py` `*.js` `*.ts` `*.yml` `*.yaml` `:!.claude/`). Four
readers, one per tracked shape:

- `.sh` via `lib/amg_hooks/shast.py` — drops a candidate inside a `#` comment
  only (strings are kept: an unscoped `tmux kill-server` built into a
  string and handed to a shell is still the hazard).
- `.py` via `tokenize`-derived comment spans — drops a candidate inside a
  `#` comment only, same reasoning.
- `.js`/`.ts` via `lib/amg_hooks/tsast.py` — comments are not representable in
  `tsast`'s `FileFacts` (no comment-span field: "comments cannot appear in
  any of these node kinds — they are trivia"), so the confirm step uses the
  precedent from `research-monorepo/hooks/color-tokens/dispatch.py`: a candidate
  line that falls OUTSIDE every recorded `strings` span is provably prose
  (there is no live JS/TS syntax shape for `tmux kill-server` outside a
  string or comment — no identifier can hold a space), so it is dropped;
  one inside a string span is kept. If no tracked frontend (`package.json`)
  exists anywhere in the checkout, `svc.tsast_frontend()` raises
  `tsast.CannotRunError` and every `.js`/`.ts` candidate is reported
  unfiltered rather than silently skipped or crashed on — see below.
- `.yml`/`.yaml`/anything else PATHSPEC selects: no reader exists for that
  grammar, so the regex verdict is kept as-is, unfiltered. This is the
  explicit instruction for this hook (documented here per that
  instruction): for yml and any other type, findings equal candidates.

**What the confirm step drops, and only this**: a `#`/`//`-comment mention
in sh, py, js or ts. Everything else the ERE candidates — real invocations
in any language, string-built invocations in py/js/ts, and every yml/yaml
hit — is kept.

FAIL CLOSED, not open: a checkout with no tracked `package.json` (this
hooks repo itself, `aii-hooks-portB`, is one such checkout — bare, no
frontend) still catches a real `tmux kill-server` written into a `.js`/
`.ts` file; it just cannot yet tell a live call from a `//` comment about
one for that language, so it reports both. This is strictly safer than
skipping js/ts checking outright when there is no frontend to parse it
with.

Stock is 0 (recorded above from the 2026-09-03 measurement), so the drop
is exercised only by `test_tmux_kill_server_names_its_socket_bites.py`'s
synthetic comment cases, not by any real consumer-tree specimen.

### Drop-set audit against the consumer (research-monorepo, 2026-09-14)

OLD is the live ERE via `git grep --cached` over the consumer INDEX under
the live pathspec; NEW is this port under `AMG_HOOKS_SWEEP=1`.

| population (`*.sh` `*.py` `*.js` `*.ts` `*.yml` `*.yaml` `:!.claude/`) | OLD | NEW | DROPS | ADDED |
|---|---|---|---|---|
| 1130 tracked files | 0 | 0 | 0 | 0 |

The population is non-empty (1130 files) and both sides agree on zero, so
ADDED is 0.

### COND-1

The live run line carries no `glob:` key — it fires through `amg-hooks-env` on
every commit — so the port reproduces that with a bare `GLOBS = ["*"]`
rather than narrowing to the six extensions `PATHSPEC` selects, the same
choice `state-file-replaced-atomically` and `tmux-launch-one-door` make for
the identical reason: a TREE-mode check judges the whole index once
triggered, so the trigger must admit everything `PATHSPEC` can select, not
just the paths one commit happens to touch.
