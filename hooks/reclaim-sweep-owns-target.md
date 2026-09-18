<!-- hook: reclaim-sweep-owns-target -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A reclaim sweep only ever matches resources this repo created

A reclaim sweep only ever matches resources this repo created: every
process-kill pattern in tracked source is anchored to a repo-owned token
(a package path, a run id, a session/pod name, an owned display), never a
bare third-party binary name.

The motivating violation, since fixed in `76d418a2a365`:

aii_lib/src/aii_lib/claude_oauth/autologin/_browser_login/_helpers.py:201-217
ran `subprocess.run(["pkill", "-f", proc_name])` for `proc_name in ("Xvfb",
"chrome", "chromium")`. Measured at proposal time: `pgrep -f chrome | wc -l` -> `27`,
and `pgrep -a chrome | head -4` shows they are the owner's snap browser, not
this repo's: `763435 /snap/chromium/3506/usr/lib/chromium-browser/chrome
--password-store=basic ... https://claude.ai/code/artifact/...` plus its
`chrome_crashpad_handler` and zygote children. So one relogin terminated the
owner's browser and every tab in it. It was on the live path, not a dead
branch: `_kill_stale_display_processes` has exactly one caller,
`_helpers.py:256` inside `ensure_display()`, which oauth_flow.py:92 calls from
`get_oauth_auth_code`, reached at oauth_flow.py:740 inside the very flow
CLAUDE.md documents the relogin endpoint as driving. The repo already states
this invariant in two places and honours it everywhere else:
aii_pipeline/.../prompts/components/work_solo_reminder.py:17 instructs its own
agents "NEVER kill processes by name (`killall`, `pkill -f`, `ps aux | grep
... | xargs kill`). This kills OTHER runs' processes.", and
aii_lib/utils/tmux.py:441 explains `pkill_orphans` exists because "a naive
``pkill -f <pattern>`` would match the daemon and kill it". Every other sweep
in the tree is anchored — `git grep -nE 'pkill'` gives `_teardown.py:239
pkill_orphans(r"aii_launcher( --local)?$")`, `:394 r"aii_launcher --runpod$"`,
`:395 r"aii_launcher --resume .*$"`, spawn.py:137
`f"aii_pipeline.cli.*-id={run_id_for_orphan}"`, run_server.sh:453 `pkill -KILL
-f '[a]ii_server\.py'`. The three bare names in `_helpers.py` were the only
unanchored patterns in the tree.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: resource-lifecycle-pairing)

Command (BUILT — `scripts/check_sweep_anchored.py`), no condition, whole-tree:

    python3 $RULE_DIR/scripts/check_sweep_anchored.py

**The three hits are gone.** They were fixed in `76d418a2a365` before this gate
was written: the Xvfb sweep is anchored to `Xvfb :99` and the chrome/chromium
name sweeps are deleted. The gate holds that end-state rather than reporting a
backlog.

Two deviations from the command proposed above, both deliberate:

- It does **not** pipe `rules-grep`. That was a miscitation: `rules-grep` is an
  ENGINE script the runner puts on `PATH` (`rules.py:436`), not a rule-local
  file, so citing it under a rule's own `scripts/` directory names something
  that cannot exist, and the approval gate reads that as an unbuilt mechanism.
  (The path is described rather than written here on purpose — the gate scans
  PROSE for `$RULE_DIR`-rooted paths, so spelling the wrong one out, even to
  explain that it is wrong, re-blocks the rule. Found by doing exactly that.)
- It reads the AST rather than grep output. Grep cannot tell an invocation from
  prose, and this tree is full of legitimate prose about `pkill`: `tmux.py`
  explains why `pkill_orphans` exists, and the pipeline's own agent prompt says
  "NEVER kill processes by name". A line-based gate flags all of it and teaches
  everyone to ignore it.

Judged: `subprocess.run/Popen/call` whose argv starts with pkill/killall, any
`pkill_orphans(...)`, and any `orphan_pattern=` keyword — the last because the
anchoring literal is written at the CALL SITE, while `launch_in_tmux` only
forwards a parameter. A site with no readable string is skipped rather than
flagged, and that limit is stated in the script.

Verified to bite, three probes with byte-identical restores: restoring the
original bare-`chrome` sweep is caught at its line, an unanchored
`orphan_pattern="node"` is caught, and an unanchored shell `pkill -f 'python'`
is caught. Two of my own bugs were found this way and fixed — `[a]ii_server`
failed a substring test for "aii" until bracket classes were normalised, and a
prefilter keyed on "pkill" skipped `spawn.py` entirely, which never writes the
word.

Delete-check: Largely deletable rather than policed. The Xvfb sweep can target the display
the repo owns (`pkill -f 'Xvfb :99'`, or just the existing `/tmp/.X99-lock`
removal at _helpers.py:265-273), and the browser needs no name sweep at all —
`ensure_display` already returns its own `subprocess.Popen`, and both top-
level callers already terminate it in a `finally` (browser_login.py:196-200,
oauth_flow.py:143-149), so the only stale Chromium a sweep could target is one
the SIGKILL path stranded, which the same fix as tmux-session-name-reclaimable
handles. Deleting the two name sweeps takes the stock to zero; the rule then
holds the anchored end-state for the next sweep somebody writes. Distinct from
enforced rule-launcher-teardown-reaps (scoped to aii_launcher's teardown and
to pkill_orphans' internals — this call site is in aii_lib and bypasses
pkill_orphans entirely) and from rule-image-watcher-release-guards (watcher
shell only, though its comment at aii-image-watcher.sh:82 states the same
principle: "Only ever touches worktrees matching the exact shape build_sha
creates ... so it can never reclaim a worktree someone else owns").

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **holds**.
A different agent re-ran every measurement before this reached the owner.

What it found:
Unanchored patterns CONFIRMED —
aii_lib/src/aii_lib/claude_oauth/autologin/_browser_login/_helpers.py:208-215:
for proc_name in ("Xvfb", "chrome", "chromium"): subprocess.run(["pkill",
"-f", proc_name], check=False, ...) Docstring above it says only "Kill stale
Xvfb and Chrome/Chromium processes from previous runs" — no scoping to this
repo's own. What that pattern currently matches on this box: $ pgrep -f chrome
| wc -l -> 27 $ pgrep -a chrome | head -4 -> 763435
/snap/chromium/3506/usr/lib/chromium-browser/chrome --password-store=basic
--gtk-version=3 ... https://claude.ai/code/artifact/... ; plus
chrome_crashpad_handler x2 and a --type=zygote child. All the owner's
interactive snap browser, none of them this repo's. Live path CONFIRMED,
single caller chain: $ git grep -n '_kill_stale_display_processes' -- '*.py'
-> definition at _helpers.py:201, ONE call at _helpers.py:256 (inside
`ensure_display`) $ git grep -n 'ensure_display' -- '*.py' ->
browser_login.py:183 and oauth_flow.py:92 (`xvfb_proc, saved_env =
ensure_display()`), i.e. inside get_oauth_auth_code, the documented relogin
flow. Every other sweep in the tree IS anchored: $ git grep -nE 'pkill' --
'*.py' '*.sh' | grep -v '.claude/skills' _teardown.py:239
pkill_orphans(r"aii_launcher( --local)?$") _teardown.py:388
pkill_orphans(r"aii_launcher --runpod$") _teardown.py:389
pkill_orphans(r"aii_launcher --resume .*$") scripts/runpod/run_server.sh:453
pkill -KILL -f '[a]ii_server\.py' _helpers.py:210 ["pkill", "-f", proc_name]
<- the only unanchored one (aii_pipeline spawn.py's
`f"aii_pipeline.cli.*-id={run_id_for_orphan}"` reaches pkill via tmux.py:535
`pkill_orphans(orphan_pattern)`.) Both cited statements of the invariant
verified verbatim:
aii_pipeline/src/aii_pipeline/prompts/components/work_solo_reminder.py:17 "-
NEVER kill processes by name (`killall`, `pkill -f`, `ps aux | grep ... |
xargs kill`). This kills OTHER runs' processes." and
aii_lib/src/aii_lib/utils/tmux.py:438 "A naive ``pkill -f <pattern>`` would
match the daemon and kill it, taking down every tmux session ...". No pre-
existing guard: nothing in tests/ or the rules tree references
`_kill_stale_display_processes`. The nearest claimed rule (rule-launcher-
teardown-reaps) is condition-scoped to `aii_launcher/src/aii_launcher/` and
`aii_lib/src/aii_lib/utils/tmux*`, so it never sees this file.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Confirmed live at _helpers.py:210: `pkill -f` on bare
chrome/chromium/Xvfb on a box where the owner's own browser runs, while
work_solo_reminder.py:17 tells agents never to do exactly this. Anchor-to-a-
repo-owned-token is a cheap, well-motivated grep.
- KEEP: Small, exact ban-grep over pkill/pgrep pattern arguments requiring a
repo-owned anchor — probe-testable and cheap. The live `pkill -f chrome` /
`pkill -f Xvfb` sweep can terminate the developer's own processes; nothing
claimed governs what a reclaim sweep is allowed to match.
- KILL: Dedupe with ENFORCED rule-launcher-teardown-reaps, which already pins
that sweeps find what they claim and spare what they do not. The unanchored
`pkill -f Xvfb|chrome|chromium` in _browser_login/_helpers.py:208-215 is a
genuine defect worth fixing today (it would terminate a developer's own
browser), but the delete-check's fix — anchor to the display the repo owns, …
