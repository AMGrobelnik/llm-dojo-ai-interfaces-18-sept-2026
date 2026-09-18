<!-- hook: watcher-log-stamps-utc -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: condition was a content regex over the diff: the checker must return 0 fast when absent runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# Every timestamp a repo-owned shell script writes carries an explicit UTC marker — `date -u` with a `Z`/offset in the format, never a bare local `date '+%F %T'`

RAN `git grep -nE '\$\(date +[^-][^)]*%[^s)]' -- 'scripts/**/*.sh'
':!.claude/skills'` -> 8 hits, ALL local-time and zone-less: aii-builder-
keepalive.sh:78,126,154,238,258; aii-ci-watcher.sh:58 (`log() { echo "[$(date
'+%F %T')] $*" >>"$LOG"; }`); aii-image-watcher.sh:40 (same line);
stream_tmux.sh:221. RAN `git grep -nE '\$\(date -u' -- 'scripts/**/*.sh'` -> 6
hits (run_server.sh x4, run_pipeline.sh, dep_audit.sh) plus 2 bare `date -u
+%FT%TZ` in race_barrier.sh:79,92. The split is exactly by location:
everything under scripts/runpod/ (pod-side, read cross-host) is UTC-marked;
everything under scripts/local/watchers/ is unmarked local. RAN `echo "local:
$(date '+%F %T') utc: $(date -u '+%FT%TZ')"` on this box -> `local: 2026-08-24
12:25:23 utc: 2026-08-24T10:25:23Z` — a 2 h, silently-plausible gap. TWO
documented incidents ride on exactly this. (1) CLAUDE.md: "Docker Hub's
`last_updated` is UTC. This box is +02:00 (+2). Getting that wrong invents
writers that do not exist" — an agent read the keepalive log's unmarked 17:53
against a UTC API stamp and concluded another writer existed. (2) The
compensation is code: `.claude/skills/amg-hooks/rules/aii/unit-
tests/rule-watchers-installed-and-
current/test_keepalive_is_actually_running.py` carries a 42-line `local_tz()`
helper (measured: `awk '/^def local_tz/,/^ return timezone\(offset\)/' … | wc
-l` -> 42) whose docstring opens "The zone the keepalive's ``date '+%F %T'``
timestamps are written in", plus a dedicated regression test whose docstring
reads "The isolation defect this file shipped with … Django's settings loader
runs os.environ['TZ']='UTC'; time.tzset() for the whole process … a UTC
reading makes every success look younger than it is by the host's offset" — it
made a 37 h-old success read as fresh depending on xdist worker order. The
helper also documents a DST hazard it cannot fully fix ("Europe/Berlin is
+02:00 in August and +01:00 in January"). No comment anywhere declares the
local stamp deliberate; `date +%s` (epoch, zone-free) is untouched by the ERE
and correctly not flagged (dep_audit.sh:31 absent from the hits).

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: time-and-clocks)

Proposed command (implemented at approval):

    rules-grep --tree '\$\(date +[^-][^)]*%[^s)]' -- 'scripts/**/*.sh' ':!.claude/skills'   # verified today: prints exactly the 8 sites above; `date -u …` and `date +%s` do not match

Proposed condition: `git diff --cached -U0 -- '*.sh' | grep -q 'date '`

Delete-check: Yes — the dimension is deletable, and the deletion is the point. Switch the 8
sites to `date -u '+%FT%TZ'`, then DELETE `local_tz()` (42 lines), its
`/etc/localtime` symlink-reading fallback, the DST caveat, and
`test_the_local_zone_reading_survives_a_process_TZ_rewrite` — the log parser
becomes `datetime.strptime(..., '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=UTC)`.
The rule enforces that collapsed end-state; there is no second sanctioned
spelling left. The weaker alternative (`export TZ=UTC` at the top of each
watcher) is rejected: it makes the value UTC but leaves the line unlabeled, so
a human comparing it against a UTC API is still guessing.

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **holds**.
A different agent re-ran every measurement before this reached the owner.

What it found:
`git grep -nE '\$\(date +[^-][^)]*%[^s)]' -- 'scripts/**/*.sh'
':!.claude/skills'` -> 8 hits, identical to the proposal's list and line
numbers: aii-builder-keepalive.sh:78,126,154,238,258; aii-ci-watcher.sh:58;
aii-image-watcher.sh:40; stream_tmux.sh:221. Re-ran tree-wide (`-- '*.sh'
':!.claude/**'`) -> same 8, no others outside scripts/. `git grep -nE 'date
-u' -- 'scripts/**/*.sh'` -> 6 command-substitution hits
(run_server.sh:69,75,400,451; run_pipeline.sh:53; dep_audit.sh:47) plus
race_barrier.sh:79,92 bare — all under scripts/runpod/ except dep_audit. Split
by location confirmed. `date '+%F %T'` vs `date -u '+%FT%TZ'` on this box ->
`local: 2026-08-24 12:42:09 utc: 2026-08-24T10:42:09Z` (2 h). `git grep -nE
'date \+%s'` -> dep_audit.sh:31, runpod_docker_emulate.sh:176 — correctly NOT
matched by the ERE. `awk '/^def local_tz/,/^ return timezone\(offset\)/'
.../rule-watchers-installed-and-current/test_keepalive_is_actually_running.py
wc -l` -> 42; read it: docstring opens "The zone the keepalive's ``date '+%F
%T'`` timestamps are written in", documents the Django
`os.environ['TZ']='UTC'; time.tzset()` isolation defect and the
Europe/Berlin +02:00/+01:00 DST hazard, exactly as described. `grep -n -B3`
around each watcher `date '+%F %T'` and keepalive:148-158 -> no comment
anywhere declares the local stamp deliberate. Dedupe: `grep -inE
'watcher|shell|\.sh|log' claimed_r3.txt` -> 20 rows (shellcheck, shfmt, shell-
strict-mode, watcher-net-calls-bounded, watchers-installed-and-current,
watcher-logs-bounded, ci-watcher-honesty/parity, shell-exit-capture-adjacent,
...); none touches timestamp zone.

Corrected statement of fact:
Two scoping notes, neither fatal. (1) One of the 8 hits, stream_tmux.sh:221
`warn "Stream disconnected — reconnecting in 5s... ($(date '+%H:%M:%S'))"`, is
an interactive human-facing message on the operator's own terminal, where
local time is defensible — the rule should scope to timestamps written to a
LOG FILE, or accept that hit as an exception. (2) Adopting the rule is a
coupled change: `.../rule-watchers-installed-and-
current/test_keepalive_is_actually_running.py` parses these stamps (`_OK =
re.compile(r'^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] keepalive OK')` +
`local_tz()`) and must be updated in the same commit. I checked the other
consumers — `git grep -ln 'aii-*-watcher.log|aii-builder-keepalive.log'` finds
5 test files, but test_ci_watcher_is_keeping_up.py and
test_image_watcher_is_keeping_up.py derive time from `git show -s
--format=%cI` (already offset-bearing), not from log lines, so only the one
helper is coupled. That coupling is the payoff, not an obstacle: the 42-line
helper is deletable once the stamps carry Z.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Agents read these watcher logs to reason about build/deploy timing,
and CLAUDE.md records a real wrong conclusion drawn from a UTC-vs-+02:00
misread. 8 confirmed sites, one-line fix each, trivial grep; unclaimed by the
shell rules (strict-mode/shellcheck/shfmt).
- KEEP: Eight located sites in three scripts, ban-grep on bare `$(date`
without -u — trivially implementable and probe-verifiable. The CLAUDE.md UTC-
vs-+02:00 misreading incident is the documented cost, and no claimed shell rule
(strict-mode, shellcheck, shfmt) covers timestamp semantics.
- KEEP: The incident is recorded in this repo's own CLAUDE.md: reading Docker
Hub's UTC `last_updated` against a +02:00 box invented a buildcache writer that
did not exist, and cost a wrong diagnosis. Confirmed live — `git grep -nE
'\$\(date +[^-]' -- '*.sh'` shows aii-builder-keepalive.sh:78,126,154,238,258,
aii-ci-watcher.sh:58, aii-image-watcher.sh:40 all writing bare local …


## Switched 2026-09-03

The ban-grep is now clean tree-wide, so the rule ships as `--tree` (blocking in
both lanes) rather than added-lines. **NINE** sites, not eight: the proposal's
eight, plus `aii-site-watcher.sh:47`, which landed between round 3 and today
and carries the same `log()` shape as its two siblings. Line numbers below are
post-switch.

Every one was `date '+%F %T'` -> `date -u '+%FT%TZ'`, bar the last.

| site | lines |
|---|---|
| `aii-builder-keepalive.sh` | 83, 138, 166, 300, 349 |
| `aii-ci-watcher.sh` | 58 |
| `aii-image-watcher.sh` | 54 |
| `aii-site-watcher.sh` | 47 |
| `stream_tmux.sh` | 221 — `'+%H:%M:%S'` -> `-u '+%TZ'` |

`stream_tmux.sh:221` is the interactive reconnect notice round 3 flagged as a
defensible exception. It is switched rather than excepted: `18:44:59Z` is no
longer to read than `18:44:59` and costs the rule its one carve-out, so the
statement has no second sanctioned spelling to explain.

DELETED, in `rule-watchers-installed-and-current/test_keepalive_is_actually_running.py`:

- `local_tz()` — 42 lines, the whole helper;
- its `/etc/localtime` symlink read and the `datetime.now(UTC).astimezone()`
  fallback for hosts that copy that file instead of linking it;
- the `Europe/Berlin` +02:00/+01:00 DST caveat, which the helper documented
  as a hazard it could not fully fix;
- `test_the_zone_survives_django_rewriting_the_process_timezone` — the
  regression test for the `os.environ['TZ']='UTC'; time.tzset()` isolation
  defect, together with its `time` and `zoneinfo` imports.

The forward parser is the one-liner the Delete-check promised:
`datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)`.

THE CUT-OVER IS THE PART THAT NEEDED CARE, and it is not deletable. The live
`~/.local/share/aii-builder-keepalive.log` is 7 MB of PRE-switch lines, and
every `keepalive OK` in it is zone-less. A parser that knows only `...Z` reads
that file as "contains no 'keepalive OK' line at all" — the monitor's loudest
assertion, fired about the format on a host that is fine, and it would stay
fired indefinitely if the job were also broken. So `_OK` accepts both
spellings, and a zone-less stamp is read through `_PRE_CUTOVER_TZ =
timezone(timedelta(hours=14))`: the easternmost zone, i.e. the OLDEST instant
the stamp can denote. That direction is the point — an over-estimated age can
only alarm early, while the under-estimate is exactly how this file failed
before (a local clock read as UTC made a 43 h-old success look fresh). It is
free in practice: the cron fires twice daily, so a healthy host's newest
success reads at most ~26.5 h against the 42 h window. Measured on the live log
the moment of the switch — true age 3.1 h, read as 15.1 h, `is_stale` False.
Two new tests pin both halves (`test_a_pre_cutover_stamp_still_counts_as_a_success`,
`test_a_zoneless_stamp_is_never_read_as_younger_than_it_is`) plus one for a log
that holds both (`test_both_spellings_can_share_one_log`). No fixed offset can
be rewritten by a process `TZ`, so the deleted Django regression test guards
nothing that can still happen.

One more reader, missed by round 3 because it is shell rather than Python:
`aii-builder-keepalive.sh:135` seeds `last_success` from the log on the status
file's first write, and its `sed` spelled the old stamp out
(`[0-9-]* [0-9:]*`). It now captures `[^]]*` — everything up to the closing
bracket — so it reads either spelling. `test_last_success_is_seeded_from_the_log_when_there_is_no_status_file`
drives that path with pre-cut-over lines and still passes.

SCOPE, stated rather than implied. The command's pathspec is `scripts/*.sh`
(git wildmatch, so `*` crosses `/`): 20 tracked files, which is where every
log-writing script in this repo lives. Measured today, the ERE is clean across
all 89 tracked `.sh` files except two in `.claude/skills/amg-dropbox/scripts/`
that stamp a FILENAME rather than a log line — out of scope twice over (the
pathspec, and the `:!.claude/skills` exclude). Widening to
`'*.sh' ':!.claude/skills'` is therefore a one-word change if the owner
prefers the broader reading of the H1.

RESIDUAL, and the command does not catch it: `aii-redeploy-watchdog.sh:93,96`
and `volume_migration_supervise.sh:117` write `date -u '+%F %T'` — the VALUE is
UTC but the rendered line carries no `Z`, so the H1's "with a `Z`/offset in the
format" is stricter than the ban-grep, which only bans a bare local `date`.
Left alone deliberately: they are not among the sites the grep names, and
touching the watchdog would force a fourth reinstall plus a timer restart for a
marker character. Tightening the command to require the marker on `date -u`
lines too is a follow-up, and an owner call.

## Ported to dispatch.py (2026-09-14)

Relocated onto the one-pass AST dispatcher
(`general/hooks/watcher-log-stamps-utc/dispatch.py`); the standalone
`amg-hooks-grep` line and the `glob: '*.sh'` key are removed from
`general/lefthook.yml` in the same commit — `dispatch.py` folders under a
set that already wires `general-ast-checks` are auto-discovered by
`lib/amg_hooks/ast_dispatch.py`.

`_CANDIDATE` is the live ERE verbatim — it carries no POSIX class, so it
needs no translation into Python `re` at all — and `PATHSPEC` is the same
two tokens (`scripts/*.sh`, `:!.claude/skills`) the run line carries.
**What the confirm step drops, and only this**: a candidate `$(date ...)`
sitting inside a `#` comment, via `lib/amg_hooks/shast.py`'s
`FileFacts.in_comment_or_string` intersected with `FileFacts.comments`
alone. **What it deliberately does NOT drop**: a candidate inside a quoted
STRING — bash still expands `$(...)` inside double quotes, and that is the
commonest real shape recorded above (`log() { echo "[$(date '+%F %T')]"
>>"$LOG"; }`), so treating "inside a string" as a false positive here would
silently stop catching the pattern's most common real instance. This is the
opposite asymmetry from `state-file-replaced-atomically`, which drops
matches in both comments AND strings because its own hazard (a real
redirection) cannot fire from inside either.

### Drop-set audit against the consumer (research-monorepo, 2026-09-14)

OLD is the live ERE via `git grep --cached` over the consumer INDEX under
the live pathspec; NEW is this port under `AMG_HOOKS_SWEEP=1`.

| population (`scripts/*.sh` `:!.claude/skills`) | OLD | NEW | DROPS | ADDED |
|---|---|---|---|---|
| 21 tracked files | 0 | 0 | 0 | 0 |

The population is non-empty and both sides agree on zero, so ADDED is 0.
The RESIDUAL sites this README already documents (`aii-redeploy-watchdog.sh`,
`volume_migration_supervise.sh`) use `date -u` and so never match the ERE
either way — unaffected by this port, exactly as before it.

### COND-1

The live run line carries `glob: '*.sh'`, narrower in form than the
`PATHSPEC`'s `scripts/*.sh` but not narrower in reach — every path the
pathspec can select already ends in `.sh` — so `GLOBS = ["*.sh"]` admits
everything `PATHSPEC` can select and the TREE-mode judge is never triggered
short of its full population.

### Vacuity floor (2026-09-14)

No tracked `scripts/*.sh` file at all — the real state of a consumer with
no `scripts/` tree (notes-repo) — used to raise `CannotRunError` (rc 2) under
the whole-tree sweep, turning a vacuous scope into a permanent red hook. It
is now a clean skip (rc 0, a `notes` advisory) instead, the same fix
`failover-walk-budget` (commit 97cb0262) applied for the identical "domain
absent, not broken" shape.
