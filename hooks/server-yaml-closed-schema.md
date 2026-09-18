<!-- hook: server-yaml-closed-schema -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULE_DIR
# No raw `.get`-chain or `yaml.safe_load` read of server.yaml, roles/*.yaml or user.yaml exists outside a typed closed-schema loader — a loader a refactor must first build

This is two things, and the split matters for approval. The typed loader —
server.yaml, roles/*.yaml and user.yaml loaded once through a pydantic model
with `extra='forbid'`, so a mistyped key fails loud at load instead of silently
running the default — does NOT exist today; building it is a refactor for the
owner to schedule, not something a rule can assert into being. The RULE is the
greppable residue once it exists: no raw `load_config_with_overrides(...)
.get(...)` chain and no bare `yaml.safe_load` of those three files outside the
loader — the same one-door shape as `rule-config-overlay-one-door`. The
one-door scan can be written today; its allowlist names a loader module that
does not exist yet, so it lands red on every current reader (five modules,
table below) until the refactor moves them behind the door. That is the
adoption cost the filter verdicts name, and it is why the script is not
written ahead of the owner's decision.

State on 2026-08-28, re-verified against the tree. The structural gap is real
and correctly located: `aii_server/config/settings.py:30` loads server.yaml
into a bare dict and :32-39 read it through eight `.get` chains (62 lines in
the file carry a `.get(`); `aii_server/dashboard/api/__init__.py:370-420`
(`limits_for_config_dir`) reads user.yaml (:403) and the role file (:417) with
raw `yaml.safe_load`, guarding the role VALUE at :411 ('a typo in user.yaml
must not grant superuser') but no KEY. Nothing in the rule engine or the lint
config covers the key names.

Those two are where the gap was located; the one-door population is wider.
Every module that builds a path naming one of the three files and reads it
(`git grep -nE 'server\.yaml|"roles"|user\.yaml' -- 'aii_server/**/*.py'
'aii_lib/src/**/*.py'`, comments and docstrings excluded), measured
2026-08-28:

| reader | file | shape |
|---|---|---|
| `config/settings.py:30` | server.yaml | `.get` x8 :32-39 |
| `aii_lib/.../server_url.py:21` | server.yaml | `.get` :23-24 |
| `aii_lib/.../utils/paths.py:36` | server.yaml | `.get` :37 |
| `api/__init__.py:403,:417` | user, roles | `yaml.safe_load` |
| `_runpod_provision/_compute.py:189` | roles/regular | `.get` :190 |

Five modules, all outside any typed loader, so the grep below returns five
hits today and zero only after the refactor.

What is NOT true is that a mistyped key is a live silent defect today — both
worked examples the proposal was minted on are retired by verification:

| example | why it is not silent |
|---|---|
| `auth.num_proxies` | server.yaml:64 ships the code default |
| `compute.max_usd_hr` | `_compute.py:155`, `:198` log at ERROR |

`scripts/lint/mutate_and_restore.py:37-43` already documents the
`num_proxies` shadowing (settings.py:378 falls back to the same `1` that
server.yaml:64 declares), and a lost role ceiling announces itself from
`aii_server/dashboard/services/_runpod_provision/_compute.py` — every
no-ceiling exit logs at ERROR (:155-159 on the ordinary path, :191-198 on the
fallback). The pipeline-side precedent is also softer than "extra='forbid'
everywhere": unknown keys there are pruned with a warning
(`aii_pipeline/src/aii_pipeline/utils/pipeline_config.py:341`, :356-370,
`_validate_pruning_unknown`), not rejected. The rule is prevention for a
failure class the repo already treats as real; its "why" needs an example
that is actually silent before it goes to the owner.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: config-yaml)

Proposed command (implemented at approval — BLOCKED today:
`scripts/check_server_yaml_one_door.py` is not in this directory, and its
allowlist names a loader module the refactor has not created):

    python $RULE_DIR/scripts/check_server_yaml_one_door.py  # AST-walk tracked *.py under aii_server/ and aii_lib/: flag every yaml.safe_load / load_config_with_overrides call in a module that builds a path naming server.yaml, roles/*.yaml or user.yaml, allowlisting only the typed loader module; exit 1 on any hit — five today (table above), zero once the refactor lands

This is the code-side check the H1 states, not a data-side one: it fails on
a raw read whether or not the yaml files happen to validate. Validating the
FILES against `extra='forbid'` models is the refactor's end-state and lives
in the delete-check below — as the rule's command it would pass with every
one of the five raw reads still in place, which is the opposite of what the
statement claims. (Until 2026-08-28 the command line here WAS that data-side
validator, `validate_server_config_schemas.py`; the split moved it.)

Delete-check: The right deletion is making settings.py itself the validator (load once
through a typed model at boot), removing the unvalidated-dict-read dimension
entirely; the rule then shrinks to 'the tracked yamls pass the model the
server actually boots with', i.e.

    a `validate_server_config_schemas.py` data-side validator (not written yet)
    that checks tracked server.yaml + roles/*.yaml + user.yaml, and server.private.yaml when present on disk, against the aii_server-owned pydantic models with extra='forbid'

— a check that only means something once the model exists and every reader
goes through it. Proposing the one-door grep drives building that model — a
parallel schema living only in the rule dir would be the wrong home.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: The server side has none of the pipeline's schema protection — a
mistyped auth key silently runs the default, which is an access-relevant
misconfiguration. The deletion (typed model at boot) is the fix; the rule
enforces no raw .get-chain reads remain.
- KEEP: The server side lacks every protection the pipeline side has; a typo'd
auth key silently running defaults is an access-control-adjacent silent
failure. The typed-model refactor is the fix; the rule enforces loads go
through it. Worth the adoption cost.
- KEEP: After the typed-model refactor, one-door grep bans raw
yaml.safe_load/.get-chain reads of server.yaml/roles/user.yaml outside the
typed loader — same enforcement shape as config-overlay-one-door.
Implementable; refactor is the adoption cost.

## History

Original proposal (2026-08-22), kept for the record; its citations have moved
(`api/__init__.py:359-376` is now :370-420 with the value guard at :411, and
the `_compute.py:175-186` fallback is now :191-198 and logs at ERROR):

> The server side has none of the pipeline side's protections: settings.py:30-38
> reads server.yaml via bare .get chains, api/__init__.py:359-376 reads
> user.yaml/roles raw. Key-level typos silently no-op into defaults — e.g. a
> mistyped auth.num_proxies leaves the throttle identity on its default, a
> mistyped compute.max_usd_hr leaves a role without its spend ceiling (the quiet
> no-ceiling path is documented at _runpod_provision/_compute.py:175-186). The
> repo already treats this failure class as real on the pipeline side
> (extra='forbid' everywhere + <REQUIRED> sentinels); api/__init__.py:370 guards
> the role VALUE ('a typo in user.yaml must not grant superuser') but no gate
> covers the KEYS. Validating the on-disk private overlay too closes a gap CI
> structurally cannot see.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
Every file:line citation checks out. aii_server/config/settings.py:30 `_cfg:
dict = load_config_with_overrides(_SERVER_CONFIG_PATH)` followed by the bare
`.get` chain at 32-39 (`_server`, `_cors_cfg`, `_db_cfg`, `_email_cfg`,
`_security_cfg`, `_auth_cfg`, `_pod_cfg`, `_logging_cfg` — the proposal's
30-38 stops one line short of `_logging_cfg`). `grep -c` for the `.get` reads
in that file returns 43. aii_server/dashboard/api/__init__.py:359-376 is
exactly the raw `yaml.safe_load` of user.yaml + roles/<role>.yaml (those lines
have since moved to :403 and :417).

Corrected statement of fact:
The structural gap is real and correctly located — settings.py and
limits_for_config_dir read these yamls with no key schema, and nothing in the
rule engine or lint config covers the key names. But neither worked example is
a live silent defect: `auth.num_proxies` is a no-op today because
server.yaml:64 ships the same value as the code default
(mutate_and_restore.py:37-43 already documents this exact shadowing), and a
lost `compute.max_usd_hr` announces itself at ERROR from _compute.py:154-158.
The pipeline-side precedent is also softer than 'extra=forbid everywhere'
implies: unknown keys there are pruned with a warning
(pipeline_config.py:376-388), not rejected. The rule is still worth having as
prevention; the 'key-level typos silently no-op' framing needs an example that
is actually silent.

## Mechanism (built 2026-09-03)

`scripts/check_server_yaml_one_door.py` is the command above. It AST-walks
tracked `*.py` (`git ls-files`) under `aii_server/` and `aii_lib/src/`, skipping
any path with a `tests/` segment. A module is IN SCOPE when a string literal
that is **not** a docstring names `server.yaml`, `user.yaml`, or a `roles` path
segment — AST rather than grep, so prose about these files does not drag a
module in (`runpod_provision.py:30` and `:517` are docstrings; only the error
string at `:224` is data). In an in-scope module every `yaml.safe_load` /
`yaml.load` / `yaml.full_load` — resolved through `import yaml as _yaml` and
`from yaml import safe_load` bindings, not matched textually — and every
`load_config_with_overrides` call is a raw dict read.

**It is a RATCHET, not a gate, until the typed loader lands.** `debt.txt` holds
today's raw readers. A raw read in an in-scope module that is NOT listed fails
(exit 1). A listed path that no longer raw-reads also fails — `stale debt entry
— delete the line` — so the list can only shrink, and it empties exactly when
the refactor lands. `TYPED_LOADERS` is the allowlist the loader's own module
joins then; it is empty today rather than naming a path that does not exist.
Discovery never fails open: zero in-scope modules is `raise SystemExit(2)`, not
a pass.

Scope is per MODULE, not per call, because which file a call reads is built
from variables (`item` from an `rglob`, `candidate` from a tuple) that an AST
walk cannot follow. Three debt entries are in scope for that reason and also
read other yaml; `debt.txt` records which, so retiring an entry has a legible
definition of done.

**The 2026-08-28 table of five is superseded — measured today the population is
SEVEN, all seven raw-reading.** Three corrections, each verified against the
tree:

- **`aii_server/aii_server.py:678`** — correction: missed; builds the
  path and reads it
- **`dashboard/services/runpod_provision.py`** — correction: reaches
  all three via a config-dir walk
- **`dashboard/api/__init__.py:405,:422`** — correction: no longer raw
  `yaml.safe_load`

The last is a real improvement since the table was written: both reads now go
through `load_config_with_overrides`, which is the OVERLAY door and picks up a
`.private.yaml` sibling. It is still an untyped dict, so it is still listed.

Probe (2026-09-03), both directions, on the real tree:

- **clean tree, own `debt.txt`** — result: **exit 0** — `7 raw
  reader(s), all on the debt list`
- **`config/settings.py` line deleted from the list** — result: **exit
  1** — `settings.py:30: load_config_with_overrides() reads a server
  config file as an untyped dict`
- **`staff_bootstrap.py` (no raw read) added to the list** — result:
  **exit 1** — `stale debt entry … delete the line`

`test_server_yaml_raw_reads_stay_on_a_shrinking_debt_list.py` pins all of it —
seven tests (re-counted 2026-09-14): the live tree is clean; an unlisted raw
reader in a tmp tree
is exit 1; a stale entry is exit 1; an empty population is exit 2; a module
whose only mention is a docstring plus a comment stays out of scope; and an
aliased or from-imported `yaml.safe_load` is still caught.
