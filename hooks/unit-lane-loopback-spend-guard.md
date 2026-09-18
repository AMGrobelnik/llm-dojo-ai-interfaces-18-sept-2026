<!-- hook: unit-lane-loopback-spend-guard -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_ENGINE_DIR, RULES_REPO, RULE_DIR
# The unit lane cannot spend money through a loopback daemon.

In full: the root conftest pins an env-level ability-client kill switch that
aii_lib's `call_server` honors, and because env crosses process boundaries it
also protects tests that drive skill CLIs as real subprocesses.

**Status 2026-08-28: an owner decision memo, not a rule yet.** None of that
mechanism exists — the root conftest pins `AII_WEB_APP_MODE` and
`CRED_MANAGER_ENABLED` and reads `AII_ALLOW_LIVE_DBOS_TESTS`, none of which
touches the ability client, and `call_server` reads no environment variable
— and the proposed checker is deliberately not written, because building it
means an env gate in production code plus a harness-wide default that needs
a designed opt-out for any lane that legitimately drives an ability server.
The gap is structural and latent: no current test can reach a paid call (the
re-measurement at the end of this body). The proportionate next step is the
owner's — decide whether the unit lane may ever reach loopback; then the
gate is a one-line env check plus a marked opt-out, and this becomes a rule.

## The incident and the proposal

The 2026-08-22 incident: concept-fig unit tests silently bought live images
whenever an ability server answered on this box — measured $0.0686 per hook
run, then hf 402 once free quota emptied (fixture docstring, rules/aii/unit-
tests/rule-skills-declare-what-exists/test_concept_fig_cli.py:33-37; waiver on
commit 7f3db571f). The fix so far is a module-local autouse monkeypatch of
ability_server.call_server (test_concept_fig_cli.py:28-45) — but the same
module drives the CLI via subprocess.run([sys.executable, str(CLI)...]) (lines
59-62), where an in-process monkeypatch cannot reach, and ability_client
targets loopback http://host:SERVER_PORT=8020
(aii_lib/src/aii_lib/server_url.py:23, ability_client.py:154) with no disable
knob. The root conftest already solves the identical problem for the OTHER
money-adjacent loopback daemon via CRED_MANAGER_ENABLED=0 (conftest.py:40) —
the ability server has no analog. Distinct from rule-tests-offline-guard —
KILLED in the 2026-08-28 audit (`rules-pending/KILLED-2026-08-28-audit.md:22`),
so it exists in neither `rules/` nor `rules-pending/` — which would have
refused NON-loopback socket connects and scrubbed keys: this spend rode a
LOOPBACK daemon holding its own keys, partly from subprocesses an in-process
socket guard never sees. With that proposal dropped there is no rule to fold
this into; this memo is the only record of the loopback hole.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: incident-derived)

Proposed command (implemented at approval):

    .venv/bin/python "$RULE_DIR/scripts/check_loopback_spend_guard.py"  # (a) root conftest sets the kill-switch env at import; (b) in-proc probe: with it set, ability_client.call_server raises the refusal before any socket is opened

Delete-check: The deletable thing would be the CLI's server-first path itself — it cannot
go: server-side execution is the production design (the server owns the skill
venvs and provider keys). The minimal closure is an env door the suite pins
shut; the rule enforces the door exists in aii_lib and stays pinned in
conftest.

Filter verdicts (3-lens adversarial, kept 2/3):
- KILL: Same dimension as pending rule-tests-offline-guard (the unit lane
spends nothing): the loopback kill switch closes exactly the hole that rule's
non-loopback-refusal + key-scrub leaves (tonight's incident: a loopback
ability server with its own keys). Fold the env-level kill switch into that
rule so one coherent spend-guard exists instead of two half-guards.
[merge->rule-tests-offline-guard]
- KEEP: Pins tonight's measured live-spend incident ($0.0686/hook-run) via a
mechanism pending tests-offline-guard structurally cannot provide: the socket
guard must allow loopback, and only an env kill switch crosses the subprocess
boundary to skill CLIs. Genuinely different mechanism; keep both.
- KEEP: Covers precisely the hole pending rule-tests-offline-guard leaves open
(loopback allowed → local ability server spends real money, tonight's
$0.0686/hook incident); env kill-switch crosses process boundaries so
subprocess-driven skill CLIs are covered too. Functional check (invoke
call_server path under the env, assert refusal) is non-vacuous.

The KILL verdict's merge target, rule-tests-offline-guard, was itself dropped
in the 2026-08-28 audit (pointer above), so the fold it proposes is no longer
available; the two KEEP verdicts stand on their own.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
Supporting facts hold. `git show 7f3db571f` message contains `Rules-Waive:
rule-skills-declare-what-exists - concept-fig live-API pair: upstream re-
encode drift + hf 402 quota depletion` (commit dated 2026-08-22). Read
test_concept_fig_cli.py in full: the autouse fixture `_no_live_ability_server`
is at lines 27-45 (not 28-45), and its docstring carries the measurement
verbatim at lines 35-36: `$0.0686 per hook run, then ``hf 402`` once the free
allocation emptied`.

Corrected statement of fact:
Corrected statement: the in-process leak that measured $0.0686 is already
closed by the module-local autouse fixture at test_concept_fig_cli.py:27-45,
and it reaches main() correctly because main() imports call_server from the
module at call time (concept_fig_gen.py:1032). The residual gap is structural,
not live: (a) the guard is module-local, so a new money-adjacent test module
inherits nothing, and (b) subprocess-driven tests are outside any in-process
patch, with no repo-wide off switch for the loopback ability server
(aii_lib/src/aii_lib/abilities/ability_server/ contains zero os.environ/getenv
reads) — unlike CRED_MANAGER_ENABLED=0 at conftest.py:40. Today all four
subprocess sites terminate at argparse or at core validation
(concept_fig_gen.py:731 and :778) before any request, so no current test can
spend. A rule here is preventive, not a fix for a live leak.

## RE-MEASURED 2026-08-26 — the gap is STRUCTURAL and latent, not live

Everything the body says about the MISSING protection is true. There is no
env-level ability-client kill switch:

| where a switch could live | present |
|---|---|
| root `conftest.py` | no — the env it touches is listed below |
| `call_server` | no — reads no environment variable |
| the one test module | yes — a local autouse monkeypatch |

What it does touch: it pins `AII_WEB_APP_MODE` and `CRED_MANAGER_ENABLED`
(`conftest.py:39-40`, both `setdefault`) and only READS
`AII_ALLOW_LIVE_DBOS_TESTS` (`conftest.py:103`, the opt-in that stands the
live-DBOS guard down — a read, not a pin); none of the three touches the
ability client.

And a service DOES answer on loopback 8020 on this machine right now, so the
target of that spend is reachable.

**But no current test can reach a paid call, and that is worth stating before
anyone changes production code.** The rule's central point — an in-process
monkeypatch cannot reach a `subprocess.run` — is structurally correct. Checked
against what those subprocess cases actually do: every one is an error path
(unusable argument combinations, `--help`, a missing `--edit` file, an empty
prompt), and each exits before the payload is built, let alone before
`call_server` at `concept_fig_gen.py:1034`. The helper's own docstring says so
— "Nothing below reaches a request, so the value is never sent anywhere" — and
that claim survives reading the parametrised cases.

So this is the same shape as `rule-group-run-proves-something`: a real hole that
nothing currently falls through.

**Why no mechanism is written here, and it is not effort.** The fix the rule
asks for is an env gate inside `aii_lib`'s `call_server` plus a pin in the root
conftest. That is production code plus a harness-wide default, and the blast
radius runs the wrong way: a conftest that refuses ability-server calls for the
whole suite also refuses them for any lane that legitimately drives one, so it
needs an opt-out designed alongside it. Nor is there a cheap static substitute —
"does this subprocess reach a paid call" is not decidable by reading the test.

The proportionate step is the owner's: decide whether the unit lane may ever
reach loopback, then the gate is a one-line env check plus a marked opt-out. The
measurement above is what that decision needs, and the incident cost
($0.0686 per hook run, then HTTP 402 once free quota emptied) is what makes it
worth making rather than leaving latent.


## Mechanism (built 2026-09-03)

The owner's decision landed: the unit lane may NOT reach the loopback ability
server by default, and a lane that legitimately needs one opts out for itself.
Everything the body above calls missing now exists.

**The door.** `AII_ABILITY_CLIENT_ENABLED` is read by `_refuse_if_disabled`
(`aii_lib/src/aii_lib/abilities/ability_server/ability_client.py`), called as
the FIRST statement of both `call_server` and `async_call_server` — before the
URL, the auth headers and the retry wrapper are built, so a refusal opens no
socket. Only the exact value `"0"` closes it, so production, which sets
nothing, is untouched. The async path is gated too: it POSTs to the same
daemon, and gating only the sync half would leave the identical spend path
open — the "half-guard" the filter verdicts above warn about.

Why an environment variable rather than a monkeypatch is the whole point of
this rule, and the body already argues it: an in-process patch cannot reach
`subprocess.run([sys.executable, CLI, ...])`, because a child interpreter
inherits none of the parent's patches. Environment crosses that boundary, so
one line covers in-process callers and subprocess-driven skill CLIs alike.

**The pin.** `conftest.py` adds
`os.environ.setdefault("AII_ABILITY_CLIENT_ENABLED", "0")` beside the existing
`CRED_MANAGER_ENABLED` pin, with the reasoning in the module docstring.
`setdefault`, not assignment: an explicit value already in the environment
still wins, which is how a whole run opts out. The repo-root conftest is
imported before any test module or per-directory conftest, in every xdist
worker, so the pin is process-global by the time collection starts.

**The opt-out** is one line in the test or fixture that needs it:
`monkeypatch.setenv("AII_ABILITY_CLIENT_ENABLED", "1")`. **No lane in the tree
needs it today, so no opt-out was added anywhere.** Every match of
`git grep -n 'call_server\|ability_client\|ability_server' -- research-monorepo/unit-tests tests`
was inspected in context — **25 modules**, re-counted 2026-09-14 (it was 17
when this was written; the population grew, the verdict did not) — and each
turns out to stub the module
in `sys.modules`, monkeypatch `httpx`, override `_call` on a client instance,
or read source text only; none reaches `call_server` itself. The reading is
not the evidence, though — the 17 modules of the original population were RUN
against the gate in
place: 337 tests, 0 failures, `rc=0`. `AII_ALLOW_LIVE_DBOS_TESTS`
is a database lane and touches nothing here, and `tests/preflight/ability.py`
is a `python -m` script, not a collected module — it calls raw `httpx` rather
than `call_server` in any case. The module-local autouse fixture at
`research-monorepo/unit-tests/skills-declare-what-exists/test_concept_fig_cli.py:27-45`
stays exactly where it is: it is a second, independent layer, and removing it
because a broader guard exists would trade a proven guard for an unproven one.

**What the checker asserts** (`scripts/check_loopback_spend_guard.py`, ~0.2 s):

- **(a) source scan** — assertion: the root conftest still
  `setdefault`s the variable to `"0"`
- **(b) probe, `"0"`** — assertion: `call_server` raises
  `RuntimeError` naming the variable, and the socket patch never fired
- **(c) probe, `"1"`** — assertion: the SAME call reaches the socket

(c) is what keeps (b) non-vacuous. A `call_server` that refused
unconditionally would satisfy (b) and protect nothing, so the checker proves
the variable is what decides. The scan in (a) is a source read rather than an
`os.environ` check because the pin has to be at MODULE scope — reading the
process environment would also pass on a value the shell happened to export.

**Probe result.** Run exactly as the engine runs it (`RULES_MODE=all`,
`RULES_REPO` at the checkout root): **exit 0**, no output, 0.21 s wall. It
also passes under the pending-mechanism sweep
(`rules/general/rule-engine/rule-rules-md-current/
test_every_pending_mechanism_still_passes.py`), which runs every pending
command with only `RULE_DIR`, `RULES_ENGINE_DIR` and `PATH` set — hence
`_repo_root()` falls back to walking up to `pytest.ini` rather than to the
working directory, which would have made the verdict depend on where the
checker was invoked from. That sweep also fixes the frontmatter shape: its
enumerator matches `command:` only when DOUBLE-quoted, so a single-quoted
command is invisible to it and its mechanism would never be exercised before
approval day. Same reason the condition's pathspecs are single-quoted —
`test_every_condition_pathspec_matches_something.py` skips any token starting
with a double quote, so a double-quoted pathspec is silently unchecked.

Both failure directions were measured against deliberately broken copies
rather than assumed:

- **conftest without the pin** — checker output: `conftest.py: no
  os.environ.setdefault(...)` — exit 1
- **no repo-root conftest** — checker output: `conftest.py: repo-root
  conftest.py is missing` — exit 1
- **`_refuse_if_disabled` neutered** — checker output: raised
  `TypeError` not `RuntimeError`; opened a socket before refusing —
  exit 1
- **refusal made unconditional** — checker output: with `=1` it still
  never reached a socket — exit 1

The cannot-run path was measured too: with the `aii_lib.abilities` import made
to raise, the checker prints the reason to stderr and exits **2**, not 1. The
guard there is deliberately broader than `ImportError` — that module reads
config at import, so it can fail for reasons that are "the checker cannot run"
rather than "the rule is violated", and an unhandled traceback would exit 1 and
have the engine report the wrong verdict.

**The gate is pinned by tests too.**
`test_the_unit_lane_cannot_reach_the_loopback_ability_server.py` (4 tests, all
green) covers the sync door, the async door, the enabled control, and the
conftest pin. Proved to bite: with `_refuse_if_disabled` replaced by a no-op
through a throwaway pytest plugin, both "disabled" tests fail while the
enabled control still passes — which is the correct signature, since the
control exists to show the socket patch is what stops the call.

Two mechanics worth keeping if these tests are edited. The async case is
driven with a single `coro.send(None)` rather than `asyncio.run`, because
building an event loop itself opens a `socket.socketpair` and the forbidden-
socket fixture would then fail on the loop rather than on the client. And the
enabled control expects `TypeError`, not the `AssertionError` it raises:
`_classify_and_raise` wraps an unrecognised transport exception, and tenacity
retries only `AbilityTransientError`, so it surfaces immediately with no
backoff.

The rule directory still sits under `rules-pending/`, so its test module is
outside `pytest.ini`'s `testpaths` and is not collected by the default suite
until the rule is promoted into `rules/`. The test finds the checkout root by
walking up to `pytest.ini` rather than counting `parents[N]`, so the move to a
different depth does not silently repoint it.
