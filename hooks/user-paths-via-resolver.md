<!-- hook: user-paths-via-resolver -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# Per-user data paths (USERS_DATA_DIR joins) are built only inside the canonical resolver helpers

Why it matters: run_owner_username's docstring (api/__init__.py, incident
paragraph in its body) records the incident this pins — three drifted copies
of owner resolution, two ending in bare `return request.user.username`, so a
staff viewer resolved runs to THEMSELVES: confident wrong output, since
collapsed to one resolver (runs_list_poll.py delegates). The raw joins are
the same drift class one step later: any layout change or a future
owner-resolution edit must find them all, and the class already shipped a
defect once.

## LANDED 2026-09-04

`aii_server/dashboard/paths.py` exists — five pure, username-keyed
functions, no I/O — and every hand-rolled join calls it. Whole-tree hit
count under the command above is **0**, which is what earns the `--tree`.

site / was / now:

- `api/__init__.py:180` `_user_runs_dir`
  was: `USERS_DATA_DIR / request.user.username / "runs"`
  now: `paths.user_runs_dir(...)`
- `api/__init__.py:227` `run_dir_for` own
  was: `… / request.user.username / "runs" / run_id`
  now: `paths.user_run_dir(...)`
- `api/__init__.py:236` `run_dir_for` owner
  was: `… / owner / "runs" / run_id`
  now: `paths.user_run_dir(...)`
- `api/__init__.py:330` `_user_config_dir`
  was: `… / request.user.username / "aii_config"`
  now: `paths.user_config_dir(...)`
- `api/__init__.py:538` run access gate
  was: `… / user.username / "runs" / run_id_or_name`
  now: `paths.user_run_dir(...)`
- `run_config/__init__.py:448` owner cfg
  was: `… / owner / "aii_config"`
  now: `paths.user_config_dir(...)`
- `run_config/__init__.py:450` no-owner cfg
  was: `… / ".no-owner" / "aii_config"`
  now: same call, `owner or ".no-owner"`
- `run_config/_snapshot.py:85` ancestor
  was: `… / owner / "runs" / rid`
  now: `paths.user_run_dir(...)`
- `services/runpod_provision.py:529`
  was: `… / aii_user / "aii_config"`
  now: `paths.user_config_dir(...)`
- `services/user_api_keys.py:201`
  was: `… / aii_user / "aii_config"`
  now: `paths.user_config_dir(...)`
- `services/user_api_keys.py:240`
  was: `… / aii_user / "aii_config"`
  now: `paths.user_config_dir(...)`
- `services/capacity_supervisor.py:350`
  was: `… / aii_user / "aii_config"`
  now: `paths.user_config_dir(...)`

Twelve joins, three shapes among them: `user_runs_dir` (1 site),
`user_run_dir` (4) and `user_config_dir` (7). The door's other two helpers,
`user_root` and `users_root`, are the building blocks those three compose
from; no site outside the door calls them today.

### The request-keyed helpers stayed, and that is the point

`_user_runs_dir(request)` / `_user_config_dir(request)` are NOT deleted.
What they add is the `is_authenticated` assertion — a gate, not a path — so
they keep it and delegate the join. Four of the twelve joins live inside
those two helpers; the other eight hand-rolled, and neither half of that
eight could have called them. Four hold a username and no `request` at all
(`capacity_supervisor.py:350`, `runpod_provision.py:529` and
`user_api_keys.py:202`/`:240` — a capacity probe, a pod launch, a BYO-key
load). The other four DO have a request in scope, but resolve the RUN'S
OWNER rather than the requester (`api/__init__.py:544`,
`run_config/__init__.py:448`+`:450`, `_snapshot.py:85`), which a
request-keyed helper cannot express either. Either way, a username-keyed
door is what they were missing.

### Byte-identity was measured, not asserted

Every migrated expression was proved to produce the same string as its
replacement over a fixed matrix — 3 roots (absolute, NFS-shaped, relative)
x 7 usernames (including one with a dot, one with a dash, one underscore,
and the `.no-owner` sentinel) x 4 run ids, all 14 sites, plus the
falsy/truthy sweep for the `owner or ".no-owner"` collapse:

| stage | comparisons | differences |
|---|---|---|
|before — old expressions vs the intended formula | 1203 | 0 |
|after — old expressions vs the real `dashboard.paths` | 1203 | 0 |

The "before" run matters as much as the "after": it was executed against
the old expressions copied verbatim, BEFORE any file was edited, so the
formula the door implements was fixed by measurement rather than chosen
after the fact.

The one call whose shape changed is `run_config/__init__.py`: an `if
owner: … else: … ".no-owner"` pair became `user_config_dir(owner or
".no-owner")`. `owner` is `str | None` from `_run_owner_username`, and both
falsy values (`None`, `""`) took the else branch before and take
`".no-owner"` now — swept explicitly in the table above, 0 differences.

### Two root uses are NAMED, not migrated

The survey below flagged that the one-line grep sees neither
`signals.py:74-76` (`users_root / username` inside `_safe_user_tree`) nor
`apps.py:80-84` (walking the root's children), and asked the allowlist to
decide about `_safe_user_tree` — "fold it into paths.py or name it". They
are NAMED, deliberately. Both take `USERS_DATA_DIR` as a ROOT rather than
re-encoding the `<user>/runs` / `<user>/aii_config` layout, and
`_safe_user_tree`'s substance is VALIDATION (shape gate + a
`tree.parent == users_root` invariant before an `rmtree`), which is
`rule-path-gate-one-door`'s territory. Folding validation in here would
pre-empt the merge decision the audit note below reserves for the owner.
`paths.users_root()` and `paths.user_root()` exist for them whenever that
call is made.

### Why the command excludes the door rather than counting to one

Same argument as `rule-deep-merge-single-source`: a count-to-one check
passes only while the answer is exactly one string, so it also fails when
the canonical file MOVES. Naming the one legal home as a pathspec exclusion
and banning every other match says the same thing and degrades correctly —
a new hand-rolled join anywhere under `aii_server/` is a hit, wherever it is
put. The exclusion is load-bearing today: `paths.py`'s header spells the
four joins it owns literally, so without `:!aii_server/dashboard/paths.py`
the command is RED on the door's own documentation.

Tests need no exclusion. They live under
`.claude/skills/amg-hooks/rules/`, outside the `aii_server/**.py`
pathspec, so the several that build `settings.USERS_DATA_DIR / <user> /
"runs"` to seed a tmp tree are structurally out of scope rather than
allowlisted — and they SHOULD keep spelling the layout by hand, since a
guard that resolved paths through the door could not catch the door
resolving them wrongly.

### One door hid a module from another door's POPULATION

`rule-config-overlay-one-door`'s checker takes as its population every
tracked module whose SOURCE names `aii_config` at all. `run_config/__init__.py`
named it exactly once — in the join this migration replaced — so routing that
join through `paths.user_config_dir()` dropped the module out of that
checker's candidate set and turned its
`rule-config-overlay-one-door/allowlist.txt` entry stale, which failed that
rule for every commit in the checkout until the line was deleted. It IS
deleted, as part of this change, and that rule's command exits 0 again.

Deleting it costs no enforcement: that allowlist excuses a whole MODULE, not
a site, so the module's `flock` read-modify-write of the user's pipeline.yaml
was already unexamined with the entry present. The general lesson is the one
worth carrying: a marker-string population is coupled to the spelling of the
call sites, so collapsing joins into a door can silently shrink an unrelated
rule's scope. `services/runpod_provision.py` survived only because its
docstrings still say `aii_config/`.

### The condition carries the `all`-mode escape

`[ "$RULES_MODE" = all ] || …`, as in `rule-fe-time-format-single-source`.
Without it a whole-tree rule is skipped during the sweep, since nothing is
staged there: the drift audit the `--tree` exists for would never run, and
the rule would be green while checking nothing.

AUDIT NOTE (2026-08-28): the corpus audit reads this rule,
rule-path-gate-one-door and rule-run-dir-reserved-names-one-door as three
slices of one capability — server-side path construction: validation,
root-join, leaf-name — each spending prose deconflicting itself from the
other two, and proposes merging them into a single "server paths have one
door" rule with three clauses. That merge is an owner call at approval; the
same note sits in rule-path-gate-one-door so the overlap is visible from
either side. (As of the landing above, two of the three now have a built
mechanism: this one and rule-path-gate-one-door.)

Delete-check: Deletion is the fix: add the two username-keyed helpers beside the existing
request-keyed ones (the services call sites hold a username but no request —
that is why they hand-roll), migrate the six raw joins, then the rule
enforces zero raw joins. The layout itself cannot be deleted; two run-dir
schemes coexist by design (run_dir_for docstring, api/__init__.py). Landed as
described above: five helpers, twelve joins migrated, zero left.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Incident-backed (staff viewer resolved runs to themselves via a
drifted copy); adding the username-keyed helpers is the deletion, the rule
enforces the collapsed end-state on an access-relevant path.
- KEEP: Incident-backed (staff viewer resolved runs to themselves — confident
wrong output). Path-construction single-sourcing is grep-cheap once the two
username-keyed helpers exist. Access-control-adjacent, worth the slot.
- KEEP: Grep for USERS_DATA_DIR joins outside the resolver helpers after
adding the two username-keyed variants. Incident-backed (staff-viewer mis-
resolution), mechanically clean.

## History — the survey as proposed and as verified (2026-08-22)

Stock as re-measured 2026-08-28, before the landing: 10 joins, four inside
the canonical request-keyed helpers in dashboard/api/__init__.py and six
re-encoding the layout by hand. Re-measured again 2026-09-04 at landing
time: **12** joins. Two are new since that count: run_config/__init__.py's
`.no-owner` branch, which the 2026-08-28 pass folded into its sibling, and
services/capacity_supervisor.py:350, which landed in `363e16152` while this
door sat parked — a genuinely new site, not a miscount.

As proposed, the raw joins were run_config/_snapshot.py:85,
run_config/__init__.py:397-399, services/user_api_keys.py:183 and
services/runpod_provision.py:529, against helpers then at
api/__init__.py:143-154 and :283-304 and an incident docstring at :231-238.
Those api/__init__.py numbers have since moved; the four service/run_config
sites had not, and are in the migration table above.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
Every cited line landed exactly at the time. `api/__init__.py:216 def
run_owner_username`, and its incident paragraph occupied 231-238 verbatim
("This used to be three separate functions ... which is why the copies are
now one function."). Canonical helpers: `_user_runs_dir` def 143 -> `return
settings.USERS_DATA_DIR / request.user.username / "runs"` at 154;
`_user_config_dir` def 283 -> return at 304. Delegation in
`runs_list_poll.py` is `def _resolve_run_owner_username` at 238 with
`return run_owner_username(request, run_id)` at 248.

Corrected statement of fact:
The owner-resolution drift is genuinely collapsed and the four cited joins
are real at those lines, but there are at least three more raw joins the
survey missed (api/__init__.py:503, signals.py:74, apps.py:80-82), and three
of the four cited sites have no `request` to hand, so any consolidation needs
a username-taking helper rather than the existing request-scoped ones. (Read
again 2026-08-28: api/__init__.py:503 is :533 now and is a layout join; the
signals.py and apps.py sites are root uses, as described above.) All three
corrections held and drove the landing: the api/__init__.py site is migrated,
the two root uses are named, and the door is username-keyed.
