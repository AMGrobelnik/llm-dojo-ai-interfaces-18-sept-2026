<!-- hook: wire-timestamp-via-helper -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# Wire timestamps are minted by the aii_lib timestamp helper, never by inline datetime.now(UTC).isoformat() chains

## LANDED 2026-09-04

`aii_lib/src/aii_lib/timestamp.py` gained one export — `now_iso()` — and
every hand-spelled site in the five packages now calls it. The command's
whole-tree hit count went **14 -> 0**, which is what earns the `--tree`
form: the invariant holds over the entire codebase on every commit, not
only on added lines, so a pre-existing violation surfaces instead of riding
as an advisory.

`now_iso()` is literally `return Timestamp.now().iso`, so the module keeps
exactly ONE clock read (`datetime.now(UTC)`, inside `Timestamp.now`) and
`now_iso` is its string face. Returning `str` rather than the model is the
whole point: every migrated site immediately serialized the value, so
handing back a `Timestamp` would have put `.iso` — the expression being
deleted — straight back at the call site.

### Nothing changed behaviourally, and that was measured

A frozen-clock probe recovered each old expression from `git show HEAD:<f>`
(not retyped), evaluated it with `datetime.now` pinned to a fixed instant,
and compared it byte-for-byte against `now_iso()` pinned to the same
instant, in each migrated module's own namespace:

| quantity | value |
|---|---|
| sites compared | 14 |
| modules imported | 11 |
| instants per site | 8 |
| string comparisons | 112 |
| mismatches | **0** |

The eight instants cover every way `isoformat()` can render: 6-digit
microseconds, `500000`, `000001`, exactly `0` (the field is omitted),
midnight, end-of-year, a leap day and an EU DST-switch instant. The frozen
`now` also asserts its `tz` argument is `UTC`, so the timezone is pinned as
well as the format. Three negative controls — `Z` shorthand,
`timespec="seconds"`, a one-second skew — were all detected, so the
comparison can see a drift rather than being vacuously equal.

### The 14 sites, and why each was in scope

Every one serializes its string into JSON, a JSONL sink or an API
response body. None is a local-only clock read, so nothing was left behind
on scope grounds.

| site (post-migration) | field | sink |
|---|---|---|
| summary.py:80 | `"ts"` | summary raw dict -> OTel, FE |
| invention_loop.py:408 | `generated_at` | `InventionLoopOut` meta |
| _2_gen_viz.py:555 | `generated_at` | gen_viz_results.json |
| _3_gen_demo_art.py:558 | `generated_at` | prepared_artifacts.json |
| _4_gen_full_paper.py:392 | `generated_at` | `GenPaperRepoOut` meta |
| _5_deploy_gh.py:709 | `generated_at` | deploy results json |
| repo_info.py:268 | `generated_at` | repo_info json on disk |
| provisioner.py:169 | (body) | `<pod>.proceed` sentinel |
| runs_list_poll.py:166 | `ts` | `RunsListResponse` |
| runs_list_poll.py:261 | `first/last_at` | `RunListItem` rows |
| runs_list_poll.py:307 | `first/last_at` | provisional meta dict |
| auth_adapters.py:95 | `"ts"` | email-links JSONL |
| auth_adapters.py:113 | `"ts"` | email-links JSONL |
| monitor.py:128 | `"timestamp"` | usage-telemetry JSONL |

`provisioner.py:169` is the one that could be argued out: its own comment
says "Timestamp content is debug-only; existence is the protocol". It was
migrated anyway, because a rule that has to decide whether a written string
is read back is not a grep, and the value is identical either way.

### What the survey missed, and what the grep still cannot see

The stock recorded here was **12** for three surveys running. It was
**14**: `auth_adapters.py:95` and `:113` spell it `datetime.now(tz=UTC)`,
with the timezone passed by KEYWORD, and every survey's ERE pinned the
positional form `now\((UTC|timezone\.utc)\)`. The command now matches
`datetime\.now\([^)]*\)\.isoformat\(`, which covers the positional and
keyword spellings, `datetime.datetime.now(datetime.UTC)`, and any
`timespec=` argument — all four verified to exit 1 by planting one and
removing it.

Two things it still cannot see, stated so nobody reads a green run as more
than it is. A stamp split over two statements (`now = datetime.now(UTC)`
… `now.isoformat()`) is invisible to a single-line grep, and so is a clock
read that reaches the wire through `str()` or `strftime`. Closing either
needs an AST walk over the five packages — the promotion path if a
two-statement copy ever appears. ruff's DTZ rules (selected,
pyproject.toml) already guarantee the tz-awareness half independently, so
what escapes this grep is a single-sourcing miss, never a naive clock.

### The pathspec is spelled `aii_lib/*.py`, not `aii_lib/**/*.py`

Same correction `rule-loguru-sink-single-source` records, for the same
reason. A git pathspec without `:(glob)` magic matches with fnmatch and NO
`FNM_PATHNAME`, so a plain `*` already crosses `/` and reaches every depth,
while `**/*.py` demands a literal directory between the root and the file
and silently drops every TOP-LEVEL module. Measured on this tree,
`aii_server/**/*.py` lists 105 files where `aii_server/*.py` lists 108 —
the three missing are `aii_server.py`, `aii_server_cli.py` and `manage.py`,
every one a process entrypoint, and every one a place a wire stamp could
plausibly be written.

This was caught by planting, not by reading: under the `**` spelling all
four planted spellings sat at `aii_server/_wt_plant.py` and NONE of them
tripped the command. A `--tree` gate blind to three entrypoints reads as
green while checking nothing there, which is worse than no gate. Under the
single-`*` spelling the whole-tree count is still 0, so the widening costs
nothing today and closes the hole before it matters.

Scope note: `claude_cred_manager` is deliberately absent from the pathspec.
The import-linter contract "claude_cred_manager is reached only across a
process boundary" forbids it from importing `aii_lib` at all, so the helper
is not reachable there and a ban would have no fix.

Delete-check: Two honest endpoints, both deletions: (a) add a module-level now_iso() beside
Timestamp and migrate the inline sites (pure mechanical), or (b) decide the
frozen-Pydantic Timestamp is over-built for minting strings, keep it for
parsing/validation, and still route minting through one function. (a) is what
landed above — fourteen copies collapsed to one function, the dimension itself
deleted rather than policed. What the rule still buys after that deletion is
narrow and worth stating: it stops the fifteenth copy being typed, which is
exactly how the first fourteen arrived.

## History — the survey as proposed and as verified (2026-08-22)

As proposed, adoption was reported as 2 importer files vs 10 inline sites,
five of them the `"generated_at":` stamp. Every one of those figures was
corrected twice: an independent agent re-measured 12 inline sites (not 10)
and 6 `"generated_at"` stamps (not 5) on 2026-08-22, and the migration above
found the true figure was 14, the last two hidden behind a keyword-argument
spelling no survey's ERE matched.

Filter verdicts (3-lens adversarial, kept 2/3; the verdicts quote the
proposal-time survey — 10 sites, 5 stamps, 2 adopters — corrected to
14 / 6 / 1 by the work above, which changes none of their arguments):
- KEEP: Canonical constructor exists with 2 adopters vs 10 inline sites, five
byte-identical — the collapse (migrate to now_iso()) is mechanical and the
rule keeps the eleventh inline mint from appearing.
- KILL: All 10 inline sites already produce correct UTC ISO stamps — the
variation is benign uniformity, no incident, low drift risk. Migrate
opportunistically when touching those files; a standing gate polices style,
not a defect class.
- KEEP: Migrate the 10 inline datetime.now(UTC).isoformat() sites (5 are byte-
identical copies), then grep bans the chain outside timestamp.py. Applying it
uniformly (not just 'wire') keeps the grep decidable. Implementable, loud.

The KILL verdict aged best of the three and is worth answering rather than
outvoting: it was right that nothing was broken, and the migration confirms
it — 104 frozen-clock comparisons, zero mismatches. Its "migrate
opportunistically" remedy is the part the outcome refutes. Opportunistic
migration is what ran from 2026-08-22 to 2026-09-04 and moved the count from
12 to 12 while two more sites sat unseen in a spelling nobody had grepped for.
