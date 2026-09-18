<!-- hook: tmux-launch-one-door -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# tmux sessions are started only via aii_lib.utils.tmux.launch_in_tmux — no raw 'tmux new-session' subprocess anywhere else in package source

The door is `launch_in_tmux` in `aii_lib/src/aii_lib/utils/tmux.py`, and that
module's own docstring (:3-6) has stated the convention since it was written:
"Every 'start a tmux session' in this repo routes through
:func:`launch_in_tmux` here. Don't add another tmux launch site elsewhere —
extend this module instead."

Why a door at all: `tmux new-session` DROPS the inherited environment and
forwards only what explicit `-e` flags carry — the `env=` handed to
`subprocess.run` reaches the tmux client, never the inner command. Every
per-session variable therefore has to be composed into argv, which is what
`new_session_env_flags` exists to do, and a bypass site composes it again by
hand. `tmux.py:48-56` records the incident that made this concrete: the
images bake `IS_SANDBOX=1`, tmux drops it, and every pipeline agent then
hangs on the interactive "Bypass Permissions" prompt on a host that does not
already export it. The redirect-not-tee argument at `:566-583` is the second
thing the door encodes, from a 2026-08-20 hang of the local aii_server.

**The one Python bypass is gone (2026-09-04.)** It was
`aii_lib/src/aii_lib/claude_oauth/autologin/_autologin/_verify.py`, the
autologin identity probe, and its raw argv is now a `launch_in_tmux` call.
Routing it needed three keyword-only knobs on the door, each defaulted so
every other caller emits byte-identical argv:

| knob | why this one caller needs it |
|---|---|
| `env_defaults=False` | its `-e` block must hold exactly one var |
| `capture_output=True` | the probe reports a launch failure itself |
| `timeout=5` | one budget across every tmux call it makes |

`env_defaults` is the load-bearing one, and the reason this was not a
find-and-replace. The probe deletes claude's sticky `oauthAccount` cache and
reads back whatever the CLI rebuilds from the live token; the caller
QUARANTINES accounts on that verdict, so the inner `claude` must see one
pinned `CLAUDE_CONFIG_DIR` and nothing else. The door's defaults would in
fact have reached the right answer — they append `extra_env` last and tmux
keeps the last `-e` for a given key — but "wins a tie-break" is a weaker
guarantee than "is the only one there".

Equivalence was measured, not argued: a probe patching `subprocess.run` and
recording argv plus kwargs for the whole call sequence, run before and after
the change. Holding the session name constant, the `new-session` call is
byte-identical — same argv, same
`{capture_output: True, check: False, timeout: 5}`, same `(True, email)`
verdict, sha256 `5225930c9e77…` on both sides.

**Routing it also exposed a second, pre-existing defect, which is the whole
argument for the door.** `rule-tmux-session-name-reclaimable` reads every
`launch_in_tmux(session=…)` call site; while this one was a raw
`subprocess.run` it was INVISIBLE to that checker, which sat green over a
session named `aii-identity-verify-<uuid4 hex[:8]>` — a name no fresh
process can write down, the exact shape that stranded four `claude_login_*`
sessions for six days. Going through the door made it visible and red on
the first run. The name is now the fixed `claude_identity_probe`, carried
in the server's cleanup tuple and the launcher's `_LOCAL_OWNED_SESSIONS`
beside its siblings `claude_login` and `claude_usage_persistent`. Concurrency
was checked before fixing the name, not assumed: `activate_account` copies
the account's credentials over the ONE shared
`aii_claude_dir()/.credentials.json` and the probe then deletes a key from
the ONE shared `.claude.json` and polls it, so two probes in a config dir
already corrupt each other's verdict — the random suffix bought no
concurrency and cost reclaimability, exactly as it had for `claude_login`.

So the call sequence gains one entry: `tmux kill-session -t
claude_identity_probe` before the launch, which the door does on its own
account. With a fixed name that is not a no-op — it reclaims a session a
SIGKILLed predecessor stranded, and `oauth_flow.py:626` does the same thing
by hand before its own `launch_in_tmux`.

One fact from the 2026-08-22 independent verification is worth keeping,
because the original proposal had it backwards: routing this site through
the door would NOT have supplied `IS_SANDBOX`. That comes from
`aii_tmux_env()`, which every pipeline/server caller passes explicitly, not
from `new_session_env_flags`. What the raw call actually omitted was
`-e CLAUDECODE=` and `-e PYTHONUNBUFFERED=1`, and it set
`CLAUDE_CONFIG_DIR` itself, correctly and deliberately.

Pattern anatomy — why today's prose mentions do not match:

- `tmux[^A-Za-z0-9`]+new-session` wants the two argv tokens ADJACENT, so it
  catches the double-quoted list, the single-quoted list, a
  `subprocess.Popen` tuple and an f-string shell command, while ignoring
  prose that names only one of them ("the new-session cmdline",
  "`new-session -d` is silent");
- the separator class excludes a backtick, so the `tmux` + backticked-token
  spelling at `tmux.py:51` does not match;
- the leading ``(^|[^`])`` excludes a backtick before `tmux`, which is how
  every prose mention in shipped source spells it — house style, and the
  same guard `rule-no-pkill-by-pattern` uses.

Measured against the door itself, which holds ten mentions of the string:
the pattern selects exactly ONE, `tmux.py:597`, the real argv line. The
other nine (`:51 :145 :147 :449 :450 :451 :491 :554 :559`) are prose and are
all correctly ignored.

Two excludes, both by path:

- `aii_lib/src/aii_lib/utils/tmux.py` — the door, the one file that is
  SUPPOSED to compose that argv;
- `.claude/` — rule bodies (this one) and unit-test stubs quote the banned
  form on purpose. Three stubs in
  `research-monorepo/unit-tests/claude-creds-lifecycle/test_autologin_identity_probe.py`
  branch on `cmd[:2] == ["tmux", "new-session"]`, and
  `rule-core-primitives/test_tmux.py:77` asserts the door's argv prefix.
  Same carve as `rule-no-pkill-by-pattern`.

Out of scope, recorded rather than silently skipped: three raw shell
launches exist — `scripts/runpod/run_server.sh:520` and `:561`, and
`scripts/volume_migration_supervise.sh:161`. The H1 says PACKAGE SOURCE and
those are not it; no Python door is reachable from a pod-boot script or a
standalone supervisor. The PATHSPEC is what scopes this, not the pattern:
the same ERE matches a planted `.sh` launch once `*.sh` is added, so
widening later is a one-word change rather than a rewrite.

Probes, both ways (2026-09-04, via the engine's own `rules-grep --tree`):

- GREEN, real tree, the shipped command: 0 hits, exit 0, 29 ms.
- RED, real tree, one raw launch appended to a TRACKED file: exit 1,
  reported at `_verify.py:442`. The file was restored inside the same shell
  command and re-verified by sha256 (`60381afc5477…` before and after), and
  the command went back to exit 0.
- RED, scratch git repo, four launch shapes: double-quoted list,
  single-quoted list, `subprocess.Popen` tuple and f-string shell form all
  matched (exit 1); a file holding only backticked prose warnings did not
  (exit 0).

Type: **cmd-check** · scope: **whole-tree (`--tree`, blocks both lanes)** ·
value: **medium**. The `condition:` key is gone rather than updated: the
grep costs 29 ms, and the old condition named four package roots, so a raw
launch added under `aii_runpod/` would have skipped the rule outright.

Known limitation, recorded: a future comment naming the two tokens together
WITHOUT a leading backtick, in a `.py` file outside the door, will
false-positive. Backtick it, as all nine current mentions already do. The
port below removes exactly that class; while the `run:` line is still the
bare grep, the limitation stands.

## The grep + AST-confirm port (`dispatch.py`, wired later)

The folder now carries a `dispatch.py` for the one-pass AST dispatcher
(`lib/amg_hooks/ast_dispatch.py`), plus a `scripts/run_static_check.py` shim that
runs that one check on its own. Both ship **INERT**: the `run:` line above
is still the bare `amg-hooks-grep`, and the merge owner performs the swap. The
cutover line, written rather than applied, is

    tmux-launch-one-door:
      run: '{amg_hooks}/lib/amg_hooks/amg-hooks-env {amg_hooks}/general/hooks/tmux-launch-one-door commit -- python3 {amg_hooks}/general/hooks/tmux-launch-one-door/scripts/run_static_check.py'

`--tree` maps to the dispatcher's TREE-mode, so the swap keeps both lanes
judging the whole index and nothing about the verdict's shape moves.

### What the confirm step does

The ERE stays the SOLE candidate source — translated to Python `re` one
construct at a time, backtick exclusions included — and the confirm pass
only ever REMOVES from its hits. So the port can be quieter than today's
command and never louder: findings are a subset of candidates, and the
audit's ADDED column is 0 by construction rather than by luck.

A candidate line is DROPPED when EVERY hit on it lies inside a `#` comment
or inside a docstring (`tokenize` for the first, `ast` for the second).
Everything else is KEPT, and that asymmetry is the point: the step names
the two things it removes rather than the shapes it accepts, so a launch
spelled in some way nobody anticipated still blocks. The three shapes the
rule exists for are all kept:

| shape | what the confirm step sees |
|---|---|
| `"tmux new-session -d"` | one string constant |
| `["tmux", "new-session"]` | two elements, one line |
| `f"tmux new-session {s}"` | an f-string being built |

The middle row is why the rule is written as a drop and not as a
confirm-inside-one-string. The argv form splits the two tokens across two
SEPARATE string constants — the regex still matches the line because the
`", "` between them satisfies `[^A-Za-z0-9`]+` — so the obvious predicate
would have dropped the commonest real launch shape.

A file that will not `ast.parse`, or whose `tokenize` stream cannot be
finished, FAILS CLOSED: every candidate line in it is reported and the
regex verdict stands. A syntax error must not become a hole in the ban.

### The false-positive class this removes, measured

It is exactly the limitation recorded above — a comment or a docstring
naming the two tokens together without a leading backtick.

Measured on the door itself, `aii_lib/src/aii_lib/utils/tmux.py`. That file
is pathspec-excluded live, so it is an FP CORPUS, not a population: what it
measures is what the confirm step would do to that prose anywhere else. It
holds ten `new-session` mentions — nine prose (`:51 :145 :147 :449 :450
:451 :491 :554 :559`) and one real argv (`:597`).

| corpus | candidates | findings |
|---|---|---|
| verbatim, as the door spells it | 1 | 1 |
| every backtick stripped | 7 | 1 |

Verbatim, the backtick exclusions already do the whole job and the port
changes nothing — which is why they are preserved character for character.
Strip that armour and the regex alone goes from 1 hit to 7; the confirm
step drops the six prose lines and keeps the one argv. The other three of
the nine (`:450 :491 :554`) never name the two tokens adjacently, so the
pattern rejects them on its own account either way.

That 7 -> 1 is what the port buys. The nine mentions no longer have to be
backtick-armoured for this rule to stay green, so a future comment written
the natural way stops being a false positive somebody has to chase.

### Drop-set audit against the consumer (research-monorepo, 2026-09-14)

OLD is the live ERE over the consumer's INDEX under the live pathspec; NEW
is `scripts/run_static_check.py` under `AMG_HOOKS_SWEEP=1`.

| population | OLD | NEW | DROPS | ADDED |
|---|---|---|---|---|
| live pathspec | 0 | 0 | 0 | 0 |
| door exclusion lifted | 1 | 1 | 0 | 0 |

The first row is 0/0 because the stock is genuinely zero (see the
delete-check below), so the live audit can only show that the port adds
nothing — which is the column that has to be 0. The second row lifts the
`:!` on the door to put the one real launch in scope: both sides report
`tmux.py:597`, and neither reports any of the nine prose mentions beside
it. `test_tmux_launch_one_door_bites.py` carries the rest — 21 tests,
including the subset assertion, both fail-closed halves, the corpus
measurement above, and COND-1.

### COND-1

The live command carries no `glob:` key at all — it runs through `amg-hooks-env`
on every commit — so the trigger the port introduces is its own
`GLOBS = ['*.py']`, which has to admit everything `PATHSPEC` selects. It
does, with no depth gap: under lefthook 2.1.9's gobwas globs a `*` crosses
`/`, so `*.py` reaches a root file and a deeply nested one alike. The gap
worth knowing is a DIFFERENT spelling — `X/**/*.py` needs a literal slash
after `X/` and so skips X's own direct children, where `X/**.py` and `X/**`
do not — and nothing here is spelled that way. No `lefthook.yml` was
touched to keep it so.

## Delete-check

The dimension is now fully deleted on the Python side — no raw
`new-session` argv survives in package source, so this rule pins an
end-state instead of guarding a backlog. Neither exclude can shrink: the
door has to compose the argv, and `.claude/` has to be able to stub it in
tests. What remains is the three shell sites — porting them onto the door
needs a `python -c` shim in `run_server.sh` and a rewrite of
`volume_migration_supervise.sh`, after which the pathspec grows `*.sh` and
the H1's "package source" can widen to "anywhere".
