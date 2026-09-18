<!-- hook: tmux-session-name-reclaimable -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every tmux session this repo launches carries a name a FRESH process can reclaim — a literal some boot or teardown path kills by name, or a swept prefix.

In full: the name is a literal some boot/teardown path kills by name, or it
carries one of the swept prefixes (`aii_local_orch_`, `aii_runpod_server_`,
`aii_runpod_orch_`). A `finally: kill_session(...)` is not release: the
session's owner is the tmux SERVER, not the launching process, so any SIGKILL
to the creator — the relogin timeout path does exactly that via `os.killpg`
— runs no finally, no atexit, no handler, and strands the session forever.
Only the NAME makes a session recoverable by whatever process comes next.

**State on 2026-08-28.** The one violating site is fixed (`c66890794`, "a
stranded login tmux session can now be reclaimed"): `oauth_flow.py:82` names
the login session `_LOGIN_SESSION = "claude_login"`, reclaimed before launch,
at server exit, and by the launcher's owned-set, and `tmux ls` on this box
lists zero `claude_login*` sessions where four had been resident for six days.
`scripts/check_tmux_names.py` is built, reads the reclaimable set from the
code that reclaims, and exits 0 over the tree. The gate holds that end-state.

## History (the finding, before the fix)

AST probe (scratchpad/probe/tmux_names.py) over every
`launch_in_tmux(session=...)` call site resolved 3 as unresolvable; reading
each, two are fine and one is not: -
aii_pipeline/src/aii_pipeline/spawn.py:141 -> `session_name` from
`pipeline_session_name(run_id)` (line 120) or `_FALLBACK_SESSION =
"aii_local_orch_pipeline"` (line 32) — both swept. -
aii_runpod/.../_deploy_flow.py:122 ->
`_mirror_session_name(RUNPOD_MIRROR_{SERVER,ORCH}_PREFIX, pod_id)` — swept
prefix. - aii_lib/src/aii_lib/claude_oauth/autologin/oauth_flow.py:576 ->
`session = f"claude_login_{uuid.uuid4().hex[:8]}"` — matches neither
`STATIC_AII_SESSIONS` (tmux.py:175-183, a closed frozenset) nor any prefix,
and `git grep -nE 'claude_login'` over .py/.sh returns that ONE line, so
nothing reclaims it. The release at oauth_flow.py:826 is `finally:
kill_session(session)`. It is structurally unreachable on the timeout path:
claude_cred_manager/src/claude_cred_manager/relogin.py:430-435
`_terminate_group` does `os.killpg(process.pid, signal.SIGKILL)` — SIGKILL
runs no finally, no atexit, no handler, and the tmux server is not in that
process group. Live proof on this box: `tmux ls` lists
`claude_login_28ddc4d7`, `claude_login_8d9449f2`, `claude_login_b0446b18`
(created Aug 18), and `ps -o pid,etime,rss,cmd` on their pane children gives
`627360 4-08:10:39 54464 claude`, `787558 4-07:17:37 44688 claude`, `810636
4-07:12:23 55264 claude` — three `claude` CLIs alive 4+ days, ~154 MB RSS. The
sibling session PROVES the fix works: `claude_usage_persistent` is a fixed
name and aii_server.py:61 kills it by name at boot.

## Mechanism

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: resource-lifecycle-pairing)

Command (BUILT — `scripts/check_tmux_names.py`), no condition, whole-tree:

    python3 $RULE_DIR/scripts/check_tmux_names.py

The reclaimable set is READ from the code that reclaims — `STATIC_AII_SESSIONS`
and the `*_PREFIX` constants in `aii_lib/src/aii_lib/utils/tmux.py`, the boot-kill tuple in
`aii_server/aii_server.py`, the launcher's `_LOCAL_OWNED_SESSIONS` — never
restated here, so the checker cannot drift from the sweepers. Resolution is one
hop: literal, module constant, local binding, a name-builder's arguments or
body, or, when the launcher takes the name as a parameter, whatever its callers
pass.

Verified to bite, two probes with byte-identical restores: restoring the random
suffix is caught as unresolvable at its line, and removing `claude_login` from
BOTH reclaim sites is caught by name. Removing it from only one correctly still
passes — two paths reclaim it, and that is what makes the second probe evidence
that the set is read rather than hardcoded.

Four of my own bugs surfaced while probing, each of which had reported a
correctly-named session as a violation: `STATIC_AII_SESSIONS` is an ANNOTATED
assignment and reading only `ast.Assign` returned an empty reclaimable set;
`RUNPOD_MIRROR_*_PREFIX` is imported, so a file-local constant view could not
resolve it; a builder's docstring was answered with instead of its arguments;
and the mirror launcher's parameters are KEYWORD-ONLY, so reading `fn.args.args`
missed them.

Delete-check: Deleted at the one violating site (`c66890794`): the `uuid.uuid4().hex[:8]`
suffix is gone, the session is named `claude_login` exactly like its sibling
`claude_usage_persistent`, and it is reclaimed like everything else. Logins
are already serialized on a machine (they contend for display :99 — see
`_kill_stale_display_processes`), so the random suffix bought no concurrency
and cost reclaimability. The rule enforces
that deleted end-state: no session name may contain a component a fresh
process cannot predict. Distinct from pending rule-tmux-launch-one-door (that
pins the single ACQUIRE door — which is what makes this checkable) and from
enforced rule-launcher-teardown-reaps (that pins that the launcher's sweep
works correctly on the sessions it targets; this session is targeted by no
sweep at all).

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **holds**.
A different agent re-ran every measurement before this reached the owner.

What it found:
$ git grep -nE 'claude_login' -- '*.py' '*.sh'
aii_lib/src/aii_lib/claude_oauth/autologin/oauth_flow.py:576: session =
f"claude_login_{uuid.uuid4().hex[:8]}" (one hit in the whole tree — nothing
reclaims that name.) Swept-name sets are closed and exclude it —
aii_lib/src/aii_lib/utils/tmux.py:175-183 `STATIC_AII_SESSIONS:
frozenset[str]` = {aii_local_orch_pipeline, aii_local_server,
aii_local_frontend_dev, aii_local_frontend_prod, aii_local_storybook,
aii_local_db_backup}; prefixes at :187 LOCAL_RUN_PREFIX='aii_local_orch_',
:198-199 RUNPOD_MIRROR_{SERVER,ORCH}_PREFIX. `claude_login_` matches none.
Release is a finally — oauth_flow.py:825-826 `finally: kill_session(session)`.
Unreachable on the timeout path:
claude_cred_manager/src/claude_cred_manager/relogin.py:430-435
`_terminate_group` = `os.killpg(process.pid, signal.SIGKILL)` (docstring:
"SIGKILL the child's whole process group"). Live residue on this box: $ tmux
ls | grep claude_login claude_login_28ddc4d7 (created Tue Aug 18 22:08:56
2026) claude_login_8d9449f2 (Aug 18 23:01:59) claude_login_b0446b18 (Aug 18
23:07:13) claude_login_f3665e76 (Aug 18 22:54:23) $ tmux list-panes -t <each>
-F '#{session_name} #{pane_pid}' -> 627352 / 787551 / 810631 / 760183 — all
four still resident, 6 days after creation. Sibling fixed-name proof
CONFIRMED: `git grep -n 'claude_usage_persistent'` ->
aii_launcher/.../_local.py:40 `_LOCAL_OWNED_SESSIONS = STATIC_AII_SESSIONS |
{"claude_usage_persistent"}` (swept at _local.py:287),
aii_server/aii_server.py:61 kill_session, aii_lib/.../accounts.py:351
kill_session. No pre-existing guard: `git grep -rn 'claude_login' --
.claude/skills/amg-hooks/rules tests` -> no hits.

Corrected statement of fact:
Two small factual slips, both immaterial and both in the proposal's favour:
(a) there are FOUR stranded sessions, not three — it missed
`claude_login_f3665e76` (created Aug 18 22:54:23, pane pid 760183); (b)
aii_server.py:61 is inside `_cleanup()` (`"""Kill all child sessions and
processes. Safe to call multiple times."""`, guarded by `_cleaned_up`), i.e.
an EXIT path, not "at boot". The boot-side reclaim of that fixed name is
aii_launcher `_local.py:287` iterating `_LOCAL_OWNED_SESSIONS` in
stop_previous_local — which is a stronger example, since it is a genuinely
fresh process reclaiming by name.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: One confirmed unreclaimable name (claude_login_<uuid8> at
oauth_flow.py:576) in a flow that runs repeatedly and unattended, so each
stalled relogin strands a session forever. Neither rule-tmux-launch-one-door
(how sessions start) nor rule-launcher-teardown-reaps (launcher-owned
sessions) covers naming.
- KEEP: Enumerable and loud: every session-name literal must match a swept
prefix or a killed literal, with the launch-site count as the floor. The one
violator (claude_login_<uuid8>) is unreachable by any teardown, which rule-
launcher-teardown-reaps cannot catch because teardown never claims that name.
- KILL: One violating site tree-wide (oauth_flow.py:576's uuid-suffixed
`claude_login_<hex>`), fixed by deleting the suffix. Dedupe with PENDING rule-
tmux-launch-one-door: if every session is started via
aii_lib.utils.tmux.launch_in_tmux, that door owns naming, and ENFORCED rule-
launcher-teardown-reaps already owns the sweep side.
