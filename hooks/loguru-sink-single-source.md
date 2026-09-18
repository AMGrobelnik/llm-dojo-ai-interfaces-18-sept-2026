<!-- hook: loguru-sink-single-source -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# Loguru sink configuration (logger.add/logger.remove) lives only in one shared aii_lib helper — one format everywhere, not four looks

Reading two interleaved services' logs meant re-learning the column layout per
line: three process entrypoints each hand-rolled `logger.remove()` +
`logger.add(sys.stderr, ...)` with its own format, and a per-sink kwarg like
`diagnose=False` had to be remembered three times — which is how it came to be
forgotten twice (`rule-loguru-diagnose-off` records that repair).

## LANDED 2026-09-04

`aii_lib/src/aii_lib/logging_setup.py` is the door. It exposes one function,
`configure_logging(*, level, fmt, colorize, backtrace, jsonl_file)`, plus the
two console format constants; all three entrypoints call it and none of them
touches loguru's sink API any more. Whole-tree hit count under the command
above is **0**, which is what earns the `--tree`.

The differences between the entrypoints were real, so they became PARAMETERS
of the one function rather than a reason for three doors:

- `level` — the pipeline reads it from `io/sinks.yaml`, the accounts report
  flips it on `--notify`, the server pins `INFO`.
- `fmt` — the accounts report keeps the operator-pinned GREEN/CYAN line; the
  two services want the `name:line` machinery line.
- `colorize` — the services force colour, the accounts report leaves loguru's
  tty auto-detect alone so `aii_accounts > file` stays free of escape codes.
- `backtrace` — the accounts report suppresses the extended frames.
- `jsonl_file` — only the real server process wants the durable second sink.

`diagnose=False` is deliberately NOT a parameter. It is a property of this
workspace (frames hold decrypted user keys, credential blobs and SMTP
credentials), not of a caller, so the door states it once and no call site can
forget it.

### The two console formats now derive from each other

`_cli/setup.py` claimed its format was "the same shape as the server's stderr
sink". It was not quite: the server's line carries a clock and the pipeline's
does not, and the two literals agreed only by inspection. The door defines the
tail once and prefixes the clock for `CONSOLE_FORMAT`, so
`CONSOLE_FORMAT_NO_TIME` is that line by construction. Both strings are
byte-identical to what shipped before.

### Equivalence was measured, not asserted

A probe patched `loguru._logger.Logger.add`/`.remove` on the class, drove each
entrypoint's configuration, and recorded every call — normalized through
`inspect.signature(add).bind(...).apply_defaults()` so an argument a caller
OMITS and one it passes at loguru's own default compare equal. Captured before
the change and again after, per entrypoint, the records are byte-identical:

- `aii_accounts --notify` (level `INFO`) — identical
- `aii_accounts` plain (level `WARNING`) — identical
- the pipeline subprocess (level from `io/sinks.yaml`) — identical
- Django boot with `AII_SERVER_PROCESS=1` (both sinks) — identical

The fifth shape, a Django boot that is not the server process, was checked
after the change and is what it was before: one `remove()`, one stderr sink,
no file sink. That branch is now a `jsonl_file=None` argument instead of an
`if` around a second `logger.add`.

### Scope, and what is deliberately outside it

`scripts/volume_migration_backup.py` also configures a sink and is NOT in the
pathspec — it is a standalone operator script, not package source, and the
five package roots are the boundary every sibling one-door rule uses.
`claude_cred_manager` is exempt by construction rather than by allowlist: a
separate deploy unit with no `aii_lib` dependency (pyproject deps are
pyyaml/httpx/pydantic/fastapi/uvicorn only), so it cannot reach the door — and
it configures no sink today. `:!**/tests/**` excludes the one tests directory
inside the roots; the rule-engine test modules that install capture sinks live
outside them already.

### The door's arrival moved a sibling's floor

`rule-loguru-diagnose-off`'s checker refuses to report a clean tree below
`_MIN_SINKS` sinks, on the reasoning that a suddenly-small count means the
parse broke rather than the tree shrinking. Collapsing four sink calls into
two made the tree genuinely shrink, so that floor moved from 3 to 2 in the
same change. Left alone it would have failed with "only 2 loguru sinks
found" — a guard tripping on the exact cleanup it exists to protect.

## Why the command excludes the door rather than counting to one

Same argument `rule-deep-merge-single-source` makes: a count-to-one check
passes only while the answer is exactly one string, so it also fails when the
canonical file MOVES. Naming the one legal home as a pathspec exclusion and
banning every other match says the same thing and degrades correctly — a new
sink anywhere under the five package roots is a hit, wherever it is put.

### The pathspec is spelled `aii_lib/*.py`, not `aii_lib/**/*.py`

That looks like a typo and is the opposite. A git pathspec without `:(glob)`
magic matches with fnmatch and NO `FNM_PATHNAME`, so a plain `*` already
crosses `/` — `aii_server/*.py` reaches every depth. Spelling it `**/*.py`
instead requires a literal directory between the root and the file, and
silently drops every top-level module: measured on the tree this commit
carries, `aii_server/**/*.py` lists **104** files where `aii_server/*.py`
lists **107** — the three missing are `aii_server.py`, `aii_server_cli.py`
and `manage.py`, every one of them a process entrypoint. The census moves
as the package grows; the invariant is the gap, and it is exactly the set
of modules that sit at a package root.

That is not academic — it was caught by the probe, not by reading. The first
version of this command used `**/*.py`, and a planted `logger.add` at
`aii_server/_rule_probe_delete_me.py` did NOT trip it. A door rule with a
blind spot at the top level of every package root is worse than no rule,
because it reads as green. The sibling one-door rules already use the
single-`*` spelling; this one now matches them.

The condition carries the `[ "$RULES_MODE" = all ] || …` escape, copied from
`rule-fe-time-format-single-source`. Without it a whole-tree rule is skipped
during the sweep, since nothing is staged there: the drift audit the `--tree`
exists for would never run, and the rule would be green while checking
nothing.

## History

### Original measurement (2026-08-22) — line numbers since drifted

Measured four divergent console looks across the five aii_* packages:
aii_lib/src/aii_lib/claude_oauth/_accounts_health/_config.py:122 uses the
canonical user-pinned format (GREEN time|level|function),
aii_pipeline/src/aii_pipeline/_cli/setup.py:27 uses 'level|name:line' with NO
time, aii_server/config/settings.py:602-611 uses a third
'time|level|name:line', and aii_runpod (17 loguru files) plus aii_launcher
never call logger.add so they render loguru's stock default — a fourth look.
Exactly 3 files call logger.remove()/logger.add() (accounts_health.py:283,
settings.py:602+634, setup.py:48), each hand-rolling sink setup independently.
Reading two interleaved services' logs means re-learning the column layout per
line.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: cross-cutting)

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Four divergent console formats against the user-pinned standard, and
the inventory's own gaps list names logging conventions as unenforced.
Collapse to one configure() helper, then enforce no logger.add outside it.
- KEEP: Fills the inventory's named logging-conventions gap: four divergent
console formats against a user-pinned standard. Collapse to one aii_lib
configure() then grep for logger.add outside it — cheap post-collapse, and
log-format uniformity pays daily in ops greps.
- KEEP: After collapsing the bespoke sink blocks into one aii_lib configure():
grep bans logger.add/logger.remove outside the helper (agent-generated run
artifacts excluded by scope). Four measured divergent formats justify it;
literal-ban shape, loud.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
`grep -rn 'logger\.add(\|logger\.remove(' --include='*.py'` (venv/node_modules
excluded) returns exactly 3 non-test files: aii_pipeline/_cli/setup.py:47,51 /
aii_server/config/settings.py:600,602,641 /
aii_lib/claude_oauth/accounts_health.py:282,283 — so 'exactly 3 files' and the
accounts_health lines CONFIRM, but the settings.py second sink is at :641, NOT
the claimed :634, and the format block is 613-618, not '602-611'. `grep -n
'^LOG_FORMAT'` on _accounts_health/_config.py returns line 122 ex

Corrected statement of fact:
Three PROCESS entrypoints configure a loguru sink, with three different
formats — settings.py:602 (+641 file sink), setup.py:51,
accounts_health.py:283. A fourth 'stock loguru default' look does exist, but
from entrypoints the proposal never names: browser_login.py, autologin.py,
claude_oauth/usage.py, container_init.py, runpod_pod_entry.py, and the worker-
pod process (aii_lib/run/agent_worker_server.py:45 imports loguru, nothing
adds a sink). It does NOT come from aii_launcher (zero loguru imports) or from
aii_runpod (imported into the configured server process). Cited
settings.py:634 should be 641.

### The 2026-08-28 blocker, now cleared

This card stood WIP because the one door its H1 names did not exist: the
proposed command excluded a path nothing provided, so it would have arrived
RED on every live sink site and, under `--tree`, blocked every commit. That
was accurate when written. The door is built, the three sink blocks are
collapsed into it, and the command is green on the whole tree — so the
condition the card set for itself ("build the helper and collapse those three
sink blocks into it first; only then re-cite the real path") is met.

Delete-check: This IS a deletion play: collapse the three bespoke sink blocks into one
aii_lib.logging_setup.configure_logging(level=..., jsonl_file=None) and have all three
call sites use it (the Django AII_SERVER_PROCESS file-sink special case at
settings.py becomes a parameter). The rule then enforces the collapsed
end-state: logger.add appears only inside the helper. claude_cred_manager is
exempt — it deliberately has no aii_lib dependency (pyproject deps:
pyyaml/httpx/pydantic/fastapi/uvicorn only).
