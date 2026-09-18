<!-- hook: get-running-loop -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# Package source obtains the event loop via asyncio.get_running_loop(), never asyncio.get_event_loop() — in sync context the old form silently binds a non-running loop instead of failing loud.

(Inside a coroutine the two forms are equivalent, so sixteen of the swaps are
behavior-identical; only the sync-context site changes behavior — for the
better, per its own docstring's contract.)

17 references across 7 files, all in package source (re-measured 2026-08-28:
count and files unchanged; the five _redeploy.py sites below :53 moved from
the 490-491/653/656/669 the 2026-08-22 verification cites to
527-528/690/693/706): _pod_probes.py:72/192, redeploy_resume.py:363/365,
dbos_overlay.py:95, runpod_orchestrator.py:281-282,
_provision/_ability.py:91-92,
_redeploy.py:52-53/527-528/690/693/706, cancellation_noise.py:97. Sixteen sit
inside coroutines (deadline arithmetic via loop.time()) where the swap is
mechanical; the seventeenth, cancellation_noise.py:97, is a SYNC install
function whose docstring demands 'call once from the async entry point, on the
running loop' — get_event_loop there would attach the noise filter to a dead
or wrong loop with zero error if a caller ever violates that, exactly the
silent loop-binding class the repo already paid a red CI for (documented at
run_jobs.py:38-61). Deprecated since 3.10 with behavior changes landing
through 3.14; ruff ships no rule for it, so nothing in the current toolchain
(rule-ruff enforced) catches a new use. Same shape as killed
rule-no-os-getenv (KILLED-2026-08-28-audit.md): one blessed spelling,
greppable zero.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: concurrency-async)

Proposed command (implemented at approval):

    ! git grep -nE 'asyncio\.get_event_loop\(' -- 'aii_server' 'aii_pipeline/src' 'aii_lib/src' 'aii_runpod/src' 'aii_launcher/src' 'claude_cred_manager/src'

Proposed condition: `git diff --cached --name-only | grep -qE '\.py$'`

OWNER-GATED: green requires the 17-site swap first (re-measured 2026-08-28: 17
live `asyncio.get_event_loop(` hits across 7 package-source files, so the
proposed grep is red on arrival). Sixteen are mechanical coroutine swaps; the
seventeenth, cancellation_noise.py:97, additionally converts silent misuse
into a loud RuntimeError.

Delete-check: A pure delete rule: swap all 17 references in one commit (get_running_loop in
the 16 coroutine sites; in cancellation_noise.py it also converts silent
misuse into a loud RuntimeError, matching the docstring's contract), then the
rule enforces the deleted end-state with a one-line grep.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Pure delete rule: swap 17 references in one commit, then a trivial
ban-grep holds it at zero. No ruff stable rule bans get_event_loop, and the
sync-context silent-bind failure mode is real. Modest value but near-zero cost
and genuinely modernizing.
- KEEP: Delete-shaped: one 17-site swap then a trivial grep ban; the sync-
context silent wrong-loop bind is a real class ruff does not cover.
- KILL: Native mechanism exists in-tree: [tool.ruff.lint.flake8-tidy-imports]
is already configured, and a TID251 banned-api entry for
asyncio.get_event_loop enforces exactly this under the already-enforced rule-
ruff — fix the 17 sites and add the entry in one commit. No new rule dir for
what a one-line lint config does. [merge->rule-ruff]

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
`git grep -n get_event_loop -- '*.py'` returns exactly 17 hits in package
source, every cited line matching: cancellation_noise.py:97,
_provision.py:78/79, _redeploy.py:52/53/490/491/653/656/669,
_pod_probes.py:72/192, dbos_overlay.py:95, redeploy_resume.py:363/365,
runpod_orchestrator.py:281/282. Count of 17 CONFIRMED; 'across 6 files' is
WRONG — that is 7 files (the proposal's own enumeration li

Corrected statement of fact:
17 references across SEVEN files (not six), all in package source. Sixteen are
deadline arithmetic inside coroutines (AST-verified AsyncFunctionDef) where
get_running_loop is a behavior-identical mechanical swap. The seventeenth,
cancellation_noise.py:97, is the sync installer — but both of its production
callers (aii_pipeline/cli.py:63, _cli/runpod_pod_entry.py:350) are already
inside `async def`, so the wrong-loop binding is a latent contract risk, not a
live defect. A tree-wide grep gate must exclude
tests/preflight/ability.py:776.

## Swapped 2026-09-03

All 17 sites swapped to `asyncio.get_running_loop()`; the ban-grep is green.
Every enclosing function was AST-confirmed (`ast.AsyncFunctionDef` for the
innermost frame containing the line) rather than read by eye, and no site was
at module import or in a sync entry point that CREATES the loop — so no site
needed `asyncio.run` / `asyncio.new_event_loop` instead.

- **1** — site: `aii_lib/.../run/cancellation_noise.py:97`; enclosing
  function: `install_cancellation_noise_filter`; context: **sync**;
  behavior: **CHANGED** — see below
- **2** — site: `aii_runpod/.../_remote/_provision.py:78`; enclosing
  function: `_stop_pod_and_confirm`; context: async; behavior:
  identical
- **3** — site: `aii_runpod/.../_remote/_provision.py:79`; enclosing
  function: `_stop_pod_and_confirm`; context: async; behavior:
  identical
- **4** — site: `aii_runpod/.../_remote/_redeploy.py:52`; enclosing
  function: `_wait_postgres_ready`; context: async; behavior:
  identical
- **5** — site: `aii_runpod/.../_remote/_redeploy.py:53`; enclosing
  function: `_wait_postgres_ready`; context: async; behavior:
  identical
- **6** — site: `aii_runpod/.../_remote/_redeploy.py:527`; enclosing
  function: `redeploy_runpod`; context: async; behavior: identical
- **7** — site: `aii_runpod/.../_remote/_redeploy.py:528`; enclosing
  function: `redeploy_runpod`; context: async; behavior: identical
- **8** — site: `aii_runpod/.../_remote/_redeploy.py:694`; enclosing
  function: `redeploy_runpod`; context: async; behavior: identical
- **9** — site: `aii_runpod/.../_remote/_redeploy.py:697`; enclosing
  function: `redeploy_runpod`; context: async; behavior: identical
- **10** — site: `aii_runpod/.../_remote/_redeploy.py:710`; enclosing
  function: `redeploy_runpod`; context: async; behavior: identical
- **11** — site: `aii_server/.../_redeploy_resume/_pod_probes.py:72`;
  enclosing function: `_await_orch_scheduled`; context: async;
  behavior: identical
- **12** — site: `aii_server/.../_redeploy_resume/_pod_probes.py:192`;
  enclosing function: `_is_colocated_with_server`; context: async;
  behavior: identical
- **13** — site: `aii_server/.../services/dbos_overlay.py:95`;
  enclosing function: `_await_public_port_mapping`; context: async;
  behavior: identical
- **14** — site: `aii_server/.../services/redeploy_resume.py:363`;
  enclosing function: `_await_recovery_engaged`; context: async;
  behavior: identical
- **15** — site: `aii_server/.../services/redeploy_resume.py:365`;
  enclosing function: `_await_recovery_engaged`; context: async;
  behavior: identical
- **16** — site: `aii_server/.../services/runpod_orchestrator.py:281`;
  enclosing function: `wait_for_boot`; context: async; behavior:
  identical
- **17** — site: `aii_server/.../services/runpod_orchestrator.py:282`;
  enclosing function: `wait_for_boot`; context: async; behavior:
  identical

Sixteen are deadline arithmetic (`loop.time()`) inside a coroutine, where the
running loop IS the loop `get_event_loop` returns — mechanical, no behavior
change. The seventeenth is the sync installer, and its swap is the point of the
rule: `loop = loop or asyncio.get_running_loop()` now raises `RuntimeError`
where the old form would silently hand back a non-running loop and attach the
noise filter to it, suppressing nothing and reporting nothing. Both production
callers (`aii_pipeline/src/aii_pipeline/cli.py:63` in `async def main`,
`_cli/runpod_pod_entry.py:350` in `async def _async_main`) are already inside a
coroutine, so this converts a latent contract risk into a loud failure without
touching any live path. Its docstring already demanded 'call once from the
async entry point, on the running loop'; that sentence is now enforced rather
than merely documented, and the docstring says so.

**One monkeypatch had to be repointed, and the failure mode was the silent
one.** `rule-runpod-redeploy-safety/test_ability_replace_path.py`'s
`test_unconfirmed_stop_times_out_loudly` drives `_stop_pod_and_confirm` past its
deadline with a fake clock installed via
`monkeypatch.setattr(remote.asyncio, "get_event_loop", ...)`. After the swap the
patch matched nothing, and the test kept PASSING — on the real clock, in
**61.18 s** instead of under 0.005 s, i.e. asserting the wall-clock timeout
rather than the deadline arithmetic it exists to pin. Repointed to
`get_running_loop`; back to under 0.005 s, so the fake clock bites again. This is
the CLAUDE.md 'a patch that stops biting leaves the test passing while it
exercises the real function' trap, caught by timing rather than by a red test.

The gate is `rules-grep --tree`, so it blocks in BOTH commit and sweep mode
rather than only on added lines — appropriate because the stock is now zero.
The pathspecs are the six package-source roots; `tests/preflight/ability.py:776`
still carries the old form and is deliberately OUT of scope, as the 2026-08-22
verification note above requires.
