<!-- hook: no-pkill-by-pattern -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# No shipped script or Python source kills processes by command-line pattern: no `pkill -f`, no `pgrep -f` piped straight into kill — kill by pid after ownership filtering.

Two measured costs, both from 2026-08-28. First, `pkill -f <pattern>`
matches the shell running it: the `bash -c` executing the command carries
the whole command text, pattern included, so the caller terminates itself —
exit 144 with nothing else run, twice in one night (engine SKILL.md traps).
Second, in shared contexts a pattern sweep terminates processes belonging
to OTHER runs and agents: the pipeline's own work-solo reminder
(`aii_pipeline/src/aii_pipeline/prompts/components/work_solo_reminder.py:17`)
bans exactly this for agents sharing a machine. The sanctioned door exists
and is pid-filtered: `aii_lib/src/aii_lib/utils/tmux.py` `pkill_orphans()`
runs `pgrep -f`, then filters each candidate pid through /proc ownership
checks, then signals by PID — and `_teardown.py` already routes every
launcher sweep through it.

Pattern anatomy (why today's legitimate mentions do not match):

- the leading ``(^|[^`])`` group: a backtick before `pkill` excludes the
  hit — every prose mention in shipped source backticks the command (house
  style), so docstrings and comments that WARN against the pattern stay
  invisible;
- `( -[A-Z0-9]+)? -f` — catches `pkill -f` and the signal-flag form
  `pkill -KILL -f` / `pkill -9 -f`;
- `., ?.-f` — catches the subprocess list form `["pkill", "-f", ...]` /
  `['pkill', '-f', ...]`, which a shell-shaped grep would miss;
- `pgrep -f[^|]*[|][^|]*kill` — `pgrep -f` piped into a kill on the same
  line, the "no pid filtering" shape. The literal pipe is spelled `[|]`,
  not `\|`, ON PURPOSE: the escape-free ERE means a YAML-naive reader of
  this frontmatter (ready.py's, for one) and the engine's unquoting parser
  hand the shell the SAME bytes — with `\|`, a reader that skips the
  double-quote unescape turns the branch into `[^|]*kill`, which matches
  any line containing "kill" and inverts the verdict;
- `pkill_orphans(...)` never matches (the character after `pkill` must be
  a space or list punctuation, not `_`).

Verification of the premise "the current mentions are all warnings"
(measured 2026-08-28 over `*.py` `*.sh` outside `.claude/`): there are MORE
mentions than the three expected, and the pattern classifies every one
correctly. Seven prose/comment mentions, none matched: `_helpers.py:20`,
`_helpers.py:246`, `tmux.py:441`, `tmux.py:531`,
`work_solo_reminder.py:17` (all backticked warnings), `run_server.sh:422`,
`:427` (comments, no `-f` adjacency). Two EXECUTABLE pattern-kills exist
and are excluded by name as deliberate supervisor-context uses, each
explained beside its own code:

- `scripts/runpod/run_server.sh:453` — `pkill -KILL -f '[a]ii_server\.py'`
  at pod shutdown: the pod's sole supervisor terminating its own server
  workers; the `[a]` bracket keeps it from matching its own argv (comment
  block at 422-427 carries the reasoning);
- `aii_lib/.../autologin/_browser_login/_helpers.py:257` —
  `["pkill", "-f", "Xvfb :99"]`: the login flow terminating the X display
  it reserved on :99; the docstring at :246 records why it deliberately
  sweeps no wider.

Outside the pathspec, measured and recorded rather than silently skipped:
`aii_frontend/package.json:19` (`clean:force` runs `pkill -f 'next dev'` —
a dev-machine convenience, not shipped `*.py`/`*.sh`) and
`claude_cred_manager/deploy/CUTOVER_RUNBOOK.md:273/275` (runbook prose).
`.claude/` is excluded because rule bodies and unit-test docstrings quote
the banned form when warning against it — the task's out-of-scope carve.

Probes, both ways (2026-08-28, via the engine's own `rules-grep --tree`):

- RED, scratch git repo with planted violations: all four forms matched —
  `bad.sh:1` `pkill -f 'aii_local'`, `bad.sh:2` `pkill -KILL -f
  'server.py'`, `bad.sh:3` `pgrep -f myjob | xargs -r kill`, `bad.py:2`
  `subprocess.run(["pkill", "-f", "Xvfb :99"])` — exit 1; the planted
  backticked docstring warning and backticked comment warning in `warn.py`
  / `warn.sh` did NOT match;
- GREEN, real tree with the rule's exact command: 0 hits, exit 0.
  Measured stock is 0, which is what qualifies the rule for `--tree`
  (blocks in both lanes) per the engine's own flip criterion.

Known limitations, recorded: a future comment that names `pkill -f`
WITHOUT backticks will false-positive — backtick it, as every current
warning already does; and a multi-line sweep (pids captured to a variable,
then killed without ownership filtering) is beyond a line grep — that
shape is what `pkill_orphans()` exists for, and an AST-level check is the
promotion path if it ever appears.

Proposed type: **cmd-check** · scope: **whole-tree (`--tree`, blocks both
lanes)** · value: **high** (proposer: owner-tasked, 2026-08-28; incident
2026-08-28 x2)

Delete-check: the dimension is already half-deleted — `pkill_orphans()` is
the one door and every launcher sweep goes through it. Full deletion means
porting the two named supervisor-context sites onto it (feasible for the
Xvfb teardown, which is Python; the pod shutdown script would need a
`python -c` shim), after which the excludes shrink to nothing and the rule
tightens to "the string appears nowhere executable". Until then the ban
pins the boundary so the excludes cannot grow silently.
