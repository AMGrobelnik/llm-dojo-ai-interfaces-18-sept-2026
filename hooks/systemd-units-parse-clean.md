<!-- hook: systemd-units-parse-clean -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Versioned systemd units under scripts/local/watchers/ carry no directive `systemd-analyze verify` reports as unknown or unparseable

systemd IGNORES an unknown or misspelled directive with only a journal warning
nobody reads — a typo in `TimeoutStopSec=180` (aii-ci-watcher.service)
silently reverts to the 90 s default, recreating the 2026-08-04 incident that
value fixed ('State stop-sigterm timed out. Killing.' — postmaster and
checkout stranded mid-cleanup, per the unit's own comment). The existing
guards check semantic shape only: test_timer_units_survive_a_manager_restart
vets timer scheduling, match-installed vets byte parity — a unit that is
identically wrong in both places passes both.

**State on 2026-08-28.** SEVEN versioned units are tracked under
`scripts/local/watchers/` — `aii-accounts.service` + `.timer`,
`aii-ci-watcher.service`, `aii-image-watcher.service`,
`aii-redeploy-watchdog.service` + `.timer`, `aii-site-watcher.service`
(this body said four; the count was stale on arrival) — and `check.sh` exits
0 over all of them in about 60 ms, offline. SIX since 2026-09-05:
`aii-site-watcher.service` was deleted when publishing the rules page moved
into `aii-ci-watcher.sh`. `check.sh` enumerates the directory, so it needed
no edit — which is the property the enumeration was chosen for.

**The verdict is the parse diagnostics, never the tool's exit code and never
"any output".** Measured on systemd 255: a service whose `TimeoutStopSec`
key is misspelled and whose `Restart=` value is not a valid specifier
verifies with EXIT 0 — the tool mirrors systemd and merely warns — so an
exit-code check catches nothing. And the first draft's
`2>&1 | grep -q . && exit 1` would have been red on arrival for the opposite
reason: on this box the verify run prints
`aii-site-watcher.service: Command /home/…/aii-site-watcher.sh is not
executable: No such file or directory`, a fact about which watchers are
installed HERE, not about the unit file. The script therefore matches only
the shape a misparsed directive produces — `<path>:<line>: Unknown key name
'…' in section 'Service', ignoring.`, `<path>:<line>: Failed to parse
service restart specifier, ignoring: …`, `… Failed to parse calendar
specification …` — via `grep -E ': (Unknown|Failed|Invalid)'`. Proven to
bite on probe units carrying exactly those three defects (exit 1, each line
named) and to pass a correct probe; where `systemd-analyze` is absent it
exits 2 — infrastructure, loud, never blocks — rather than reporting a pass
it did not compute.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **low** (proposer: shell-watchers)

Command (BUILT 2026-08-28 — `check.sh`; units are enumerated with
`git ls-files`, so an untracked draft is not judged and zero units is exit 2,
not clean):

    bash $RULE_DIR/check.sh

Condition: `[ "$RULES_MODE" = all ] || git diff --cached --name-only -- "scripts/local/watchers/" | grep -qE "\.(service|timer)$"`

Delete-check: Cannot delete — the units are the deploy mechanism, and systemd offers no
strict-parse mode to opt into at load time; external verification is the only
closure.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: systemd ignores misspelled directives with only a journal warning, and
the 90s-default regression it would recreate is incident-backed. systemd-
analyze verify on the versioned copies is cheap and offline.
- KEEP: systemd silently ignores misspelled directives, and a typo in
TimeoutStopSec recreates a dated incident. systemd-analyze verify, condition-
gated on unit-file changes, is cheap and deterministic on this Ubuntu host.
- KEEP: systemd-analyze verify over versioned units; exit>=2 (infra) where the
tool or unit context is absent. Catches the ignored-misspelled-directive class
nothing else can. Implementable.
