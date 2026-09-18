<!-- hook: spend-env-is-per-conversation -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# The two environment variables that steer money — `AII_COST_LEDGER` and `AII_FREE_TOOLS` — are delivered in the agent subprocess's own env mapping, never by mutating `os.environ`

Full statement: the two environment variables that steer money —
`AII_COST_LEDGER` (where spend is booked) and `AII_FREE_TOOLS` (whether
spending is allowed) — are delivered in the agent subprocess's own env mapping,
never by mutating `os.environ`, because the executor deliberately co-locates
several agent conversations in one process.

Ran `git grep -nE "os\.environ\[LEDGER_ENV\]|os\.environ\[FREE_TOOLS_ENV\]" --
aii_lib aii_pipeline aii_server` -> two hits, both in the OpenHands backend:
`_agent/_helpers.py:115` (`os.environ[LEDGER_ENV] = str(ledger)`, immediately
followed by `ledger.unlink(missing_ok=True)` at :116) and
`_agent/_turn.py:200` (`os.environ[FREE_TOOLS_ENV] = "1" if
self._cfg.free_pool else "0"`). Ran `git grep -n 'LEDGER_ENV:
str(cost_ledger_path|FREE_TOOLS_ENV: "0"' -- aii_lib` ->
`terminal_claude_agent/repl_driver.py:283` and `:291`, i.e. the sibling
backend already does the safe thing by passing both inside the
`pexpect.spawn(env={...})` mapping. The premise the process-global writes rest
on is stated at `_turn.py:189-191` ('Process-global, which is safe under the
one-agent-per-executor-process model') and at `_helpers.py:109` ('Attempts are
sequential, so this never clears an in-progress ledger out from under a live
attempt') — reasoning about sequential ATTEMPTS, not about concurrent TASKS.
That premise is contradicted by design:
`aii_lib/src/aii_lib/execute_env/local.py:35` is documented 'Run agents
directly in the current process', `ExecuteEnvConfig.mode` DEFAULTS to `"local"`
(`aii_pipeline/src/aii_pipeline/utils/config_models/infra.py:374`) so
co-location is the ORDINARY case rather than a free-tier special case, and
`aii_pipeline/src/aii_pipeline/utils/pipeline_config.py:579-612`
(`apply_free_tier_execution`) additionally pins `mode = "local"` and clamps
every block to `FREE_LOCAL_MAX_CONCURRENT_AGENTS = 4` (line 542) — four
`sdk_openhands_free` conversations in one process, each pointing the shared
`AII_COST_LEDGER` at its own workspace and unlinking it. The fan-out is real
in the paid path too: `_3_invention_loop/_2_gen_plan.py:148` reads
`max_parallel = claude_cfg.max_concurrent_agents` (default 5) and :249/:346
are the `asyncio.Semaphore` + `gather_with_message_replay` that actually run
them concurrently. Money consequence: a skill subprocess inherits whichever
sibling wrote last, so external tool spend is booked against the wrong task or
unlinked mid-flight; `billed_usd_for_run` sums exactly that `tool_cost`, so the
ceiling under-enforces by whatever was lost.

## The command is `--tree`, because the stock is gone

**Stock: 0, measured 2026-09-10.** The whole-index grep for
`os\.environ\[(LEDGER_ENV|FREE_TOOLS_ENV)\] *=` over `aii_lib`,
`aii_pipeline` and `aii_server` returns nothing, so the rule runs `--tree` and
blocks on the SHAPE anywhere in the tree rather than only on lines a commit
adds. The two survivors this section used to count — `_agent/_helpers.py:115`
and `_agent/_turn.py:200` — were deleted by the source change described under
*The fix, landed* below.

The two spawn-env sites need no pathspec exclusion: `repl_driver.py:277,297`
spell the names as dict keys in `pexpect.spawn(env={...})`
(`LEDGER_ENV: str(cost_ledger_path(self.cwd))`), which the
`os\.environ\[…\] *=` pattern cannot match. The ban therefore describes the
wrong SHAPE, not a list of wrong FILES, and a new backend that copies the
correct idiom is silent by construction — which is also what makes `--tree`
safe here: nothing correct is a near-miss.

## MEASURED 2026-09-04 — the fix is gated on a dependency bump; owner decision

Both writes were traced end to end before touching them. Nothing was changed:
the per-conversation channel the rule asks for exists upstream, but NOT in the
version this repo locks. The measurement is recorded here so the next agent
does not re-derive it.

**Data flow.** The only reader of either value is a SKILL SUBPROCESS — every
consumer is an `os.environ.get("AII_COST_LEDGER" | "AII_FREE_TOOLS")` inside a
`.claude/skills/aii-*/scripts/*.py` that the agent runs as a child process
(`aii_or_call_llms.py:83,94`, `aii_fast_web_search.py:133,461`,
`concept_fig_gen.py:144,500`). The in-process read-back is already
per-conversation and touches no env: `_agent/_result.py:102` derives the path
as `cost_ledger_path(self._cfg.workspace)`. So the values need to reach ONE
spawned child, exactly as `repl_driver.py` delivers them.

**In `openhands-tools` 1.28.1, which this repo locked until 2026-09-05,
there was no channel to that child.**
The child's environment is built internally as `dict(os.environ)` and is a
parameter of nothing on the construction path: `TerminalTool.create`,
`TerminalExecutor.__init__`, `create_terminal_session`, `TmuxPanePool` and
`SubprocessTerminal` all call the zero-argument `sanitized_env()`
(`sdk/utils/command.py:36-37` -> `dict(os.environ)`). `TerminalAction` carries
`command / is_input / timeout / reset` and no env field, and a `pre_tool_use`
hook can only ALLOW or DENY (`sdk/hooks/types.py:36-40`) — it cannot rewrite a
command to prefix an assignment. The one public per-conversation env channel,
`Conversation(secrets=…)` / `update_secrets`, is unusable for these two by
construction: `SecretRegistry.get_secrets_as_env_vars` exports a secret only
when its KEY NAME appears in the command text (`find_secrets_in_text`:
`key.lower() in text.lower()`), and a skill invocation never names
`AII_COST_LEDGER`; every value it does export is then registered for
`mask_secrets_in_output`, so `AII_FREE_TOOLS`'s literal `"0"` / `"1"` would be
redacted out of all agent output.

**`openhands-tools` 1.30.0 added exactly the missing parameter.** Bisected
over the published wheels (1.29.3 absent, 1.30.0 present, unchanged through
1.44.1): `TerminalTool.create(…, *, env: Mapping[str, str] | None = None)`,
threaded to `TerminalExecutor(env=…)` -> `TmuxPanePool(env=…)` /
`create_terminal_session(env=…)` -> `build_terminal_env(extra_env)` in the new
`tools/terminal/env.py`, which is `sanitized_env()` plus the caller's
overrides. `resolve_tool` forwards a spec's params as kwargs
(`sdk/tool/registry.py:158 resolver(tool_spec.params, conv_state)`), and
`_build.py:167-169` builds a FRESH `Tool` list per conversation, so

```python
env = {
    LEDGER_ENV: str(cost_ledger_path(cfg.workspace)),
    FREE_TOOLS_ENV: "1" if cfg.free_pool else "0",
}
Tool(name=TerminalTool.name, params={"env": env})
```

is per-conversation delivery in the same shape as `repl_driver.py:283,291`,
and both `os.environ[…] =` lines then delete.

**THE BUMP IS TAKEN (2026-09-05) — this section used to say why it was
not.** The owner approved it, and `aii_lib/pyproject.toml:165-166,202-203`
now floor **both** halves at `>=1.30.0`, in both the `agent-runtime` and
`ability-server` extras (identical strings, which
`rule-shared-dep-floors-agree` requires). `uv.lock` moved as the old
dry-run predicted:

| package | before | after |
|---|---|---|
| openhands-sdk | 1.28.1 | 1.44.1 |
| openhands-tools | 1.28.1 | 1.44.1 |
| litellm | 1.87.0 | 1.99.0 |
| lmnr | 0.7.52 | 0.7.60 |
| lmnr-claude-code-proxy | 0.1.21 | 0.1.24 |

plus new `blake3`, `boto3`, `botocore`, `jmespath`, `s3transfer`; 416 ->
421 packages, and nothing else in the tree resolved differently.

**Bumping only the tools half is a trap, and it looks like the careful
choice.** `openhands-tools` declares its sibling as a bare `openhands-sdk`
with NO version constraint, so floors of `tools>=1.30.0` with the old
`sdk>=1.28.1` resolve tools 1.44.1 against sdk 1.28.1 — a five-line lock
diff with zero transitive movement, which reads as the minimal, safest
possible bump. It is a dead backend: that pair raises `ImportError: cannot
import name 'default_condenser' from 'openhands.sdk.context.condenser'`
from `openhands/tools/preset/default.py:7` on any `from openhands.tools
import ...`. Measured directly. Raise both floors or neither.

**The lmnr cliff was re-checked rather than assumed.** The old
`>=1.28.1` floor existed because lmnr 0.7.53 dropped the
`rollout_entrypoint` kwarg the sdk passed to `observe()`, killing every
agent step on a runpod orch pod on 2026-06-12 — and this bump takes lmnr
to 0.7.60, well past it. Verified on the installed 1.44.1: the string
`rollout_entrypoint` occurs nowhere in the `openhands/` tree, and the sdk
now declares `lmnr<0.8.0,>=0.7.60` itself, so upstream owns that
constraint. `lmnr.observe()` indeed no longer accepts the kwarg and has no
`**kwargs`, which is why the check mattered.

**What was verified, and what was not.** Verified: the pair imports; all
10 `openhands` symbols the repo imports still resolve;
`TerminalTool.create` carries `env: Mapping[str, str] | None = None` and
`tools/terminal/env.py:build_terminal_env(extra_env)` exists, i.e. the
channel this rule needs is really there; `Tool(name=..., params=...)`
still takes the shape the snippet above uses; and the full suite is green.
NOT verified: a real agent run against the moved model-calling layer
(litellm 1.87 -> 1.99). That remains the one thing only production can
answer.

**The fix, landed 2026-09-10.** `_build.py` grew two module-level
functions. `spend_env(cfg)` returns `{FREE_TOOLS_ENV: "1"|"0"}` plus
`{LEDGER_ENV: str(cost_ledger_path(cfg.workspace))}` when there is a
workspace; `tool_specs(cfg)` builds the per-conversation `Tool` list and
passes that mapping as the terminal tool's `params={"env": ...}`, exactly the
snippet above. `_helpers.py`'s `_point_and_reset_ledger` is now
`_reset_ledger` — a single `unlink(missing_ok=True)`, no env write — and
`_turn.py`'s `os.environ[FREE_TOOLS_ENV] = ...` block is gone along with both
modules' now-unused `import os`.

Proved in both directions by `unit-tests/cost-accounting/test_cost_ledger_reset.py`
(the path reaches the spec's env mapping while a sibling's `os.environ` value
survives untouched; the flag is set on both branches; `TerminalTool.create`
still accepts `env`) and by the two rewritten assertions in
`unit-tests/free-first-external-services/test_free_image_gen.py`. Six of the
seven cost-accounting tests and both free-first tests fail against the
pre-change source; the seventh is the upstream-channel check, which is
supposed to pass either way.

**Also worth knowing: the ordering the current code implicitly relies on does
not exist.** The comment at `_turn.py:183-191` reasons that the env is set
"BEFORE the conversation (and its bash/skill subprocesses) start". It is not —
tool construction is LAZY. `LocalConversation.__init__` defers it (":338 Agent
initialization is deferred to _ensure_agent_ready() for lazy loading"), and
`_ensure_agent_ready` — which runs `agent.init_state` -> `resolve_tool` ->
`TerminalTool.create` -> the `sanitized_env()` snapshot — is called from
`run()`/`arun()` (:985, :1053, :1226 `await
asyncio.to_thread(self._ensure_agent_ready)`). This backend enters it through
`_turn.py:513 asyncio.to_thread(conversation.run)`, i.e. on a WORKER THREAD,
several `await` points after the two writes. Sibling conversations interleave
freely across those awaits, so which task's ledger path a given conversation's
terminal captures is unordered — and the snapshot is taken ONCE per pool, so a
later sibling write cannot even be corrected. Serialising the writes would
therefore not fix it either; only per-conversation delivery does.

That analysis is why per-conversation delivery was the only fix available:
serialising the two writes would not have helped, because the snapshot is
taken once per pool on a worker thread, several `await` points after them.

Delete-check: The end-state IS a deletion — no `os.environ[…] =` for these two names anywhere,
because the terminal backend already demonstrates the alternative in-repo. So
the rule enforces a removal rather than policing a configuration: a two-name
grep over package source that must return nothing. No registry, no per-file
exemption table, and it stays closed-world because the names are defined once
in `aii_lib/src/aii_lib/run_cost.py:42,53` and imported.
