<!-- hook: config-overlay-one-door -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: condition not mapped: 'git diff --cached --name-only -z -- "*.py" "$RULE_DIR/allowlist.txt" | grep -zq .' runs through lib/amg_hooks/amg-hooks-env: RULES_REPO, RULE_DIR
# Tracked aii_config/**.yaml is read only via load_config_with_overrides (or load_yaml_cached where overlay-free is deliberate) — never raw yaml.safe_load, which drops the .private.yaml overlay

CURRENT STATE (re-measured 2026-09-05): the violation this rule was proposed
on is FIXED — `_runpod_provision/_compute.py` reads `roles/regular.yaml`
through `load_config_with_overrides` (now at _compute.py:199, with the path
built at :184 and a comment at :185 naming the hazard) — and the mechanism is
BUILT and enforcing: `scripts/check_overlay_reads.py` in the frontmatter above,
exit **0** over **55** candidate modules with **5** declared exceptions.
The fail-open blocker the proposal was parked on is answered by
`allowlist.txt`, a TRACKED declaration; the reasoning is under "Mechanism"
below, and the OWNER-GATED note near the end is kept as the record of what was
asked for and how it was met.

The hazard is documented as a past defect in-code:
aii_server/agent_abilities/_credentials/_bootstrap.py:39-41 ('a raw
yaml.safe_load of the public file silently discards the private sibling').
Seven private overlays exist (find aii_config -name '*.private.yaml' → 7
files incl. server.private.yaml, agent_backend.private.yaml — re-counted
2026-09-05, unchanged), and CLAUDE.md's worktree section shows the
missing-overlay failure reads like a config bug.
aii_lib/src/aii_lib/utils/config_overrides.py:102 defines load_yaml_cached
as the documented deliberate overlay-free door, and :131 the overlay door
itself, whose deep-merge of the private sibling is at :164-166 — so the
allowlist is principled.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: python-shared)

Proposed command (implemented at approval):

    python $RULE_DIR/scripts/check_overlay_reads.py  # AST-walk tracked *.py: flag yaml.safe_load/yaml.load calls in any module that builds a path containing 'aii_config', allowlisting utils/config_overrides.py and free_router/keys.py (reads the private file itself by design)

MEASURED 2026-08-25 — the named violation is FIXED, and the proposed
mechanism does not survive the measurement unchanged. **This section and the
two verification rounds after it are HISTORY.** Their line numbers resolve
against code that has since moved, and their closing verdict — "the mechanism
stays unbuilt" — was overtaken on 2026-09-03; the live state is at the top.

The latent violation this rule named is closed: `_runpod_provision/_compute.py`
now reads `roles/regular.yaml` through the door. Proven to matter against a
scratch copy — a private sibling declaring `0.25` is invisible to a raw read,
which applies the public `0.60` instead — and byte-identical on today's tree,
since no `regular.private.yaml` exists.

Running the proposed detection shape (a raw `safe_load` in a function that
also names the config tree) returns **7 candidates and 0 live defects**, which
is the number that matters for whether this can be a hard gate:

| site | verdict |
|---|---|
| `_credentials/_bootstrap.py` | uses the door — via its DOCSTRING |
| `_remote/_deploy_flow.py` | correct by design (below) |
| `api/__init__.py` | `user.yaml` — no overlay sibling |
| `run_config/_bootstrap.py` | presets — no overlay sibling |
| `runpod_provision.py` | hand-rolled merge, a different concern |
| `scripts/debug/dump_presets_fixture.py` | debug script |
| `tests/_config_tree.py` | test helper, out of scope |

`_deploy_flow.py` is the instructive one. It raw-loads `execute_env.yaml` —
which DOES have a private sibling — and is still right: it byte-edits `mode`
on the public file before tarring, and the tar loop ships
`execute_env.private.yaml` alongside for the pod to merge. Going through the
door there would bake private values into the public file being shipped. So
"raw load of a file that has an overlay" is not sufficient to convict.

**The population problem, which is the real blocker.** The obvious fix — scope
the gate to the seven public files that have `.private.yaml` siblings — cannot
be derived from the filesystem, because those siblings are gitignored. A
fresh clone or a CI worktree has none, so the gate would find an empty
population and pass everything: fail-open, the failure
`rule-discovery-never-fails-open` exists to catch. Making this a hard gate
needs a TRACKED declaration of which config files support an overlay
(`*.private.template.yaml` already exists for one of them, and could be the
carrier). That is a design decision, so the mechanism stays unbuilt rather
than built fail-open.

Proposed condition: `git diff --cached --name-only -z -- '*.py' | grep -zq . || [ "$RULES_MODE" = all ]`

Delete-check: The overlay convention cannot be deleted — it is the channel that keeps
secrets out of a repo with a public-export path. The deletable dimension is
'more than one way to read a config file', and it is already collapsed to two
named doors (overlay-aware + deliberately-plain); the rule enforces that
collapsed end-state. rule-lib-config-merge-paths pins the loader's own
behavior, not call-site discipline — no overlap.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Documented past defect (raw yaml.safe_load silently discards the
private sibling) on the channel that keeps credentials out of a repo with a
public-export path. The one-door dimension is the deletable part and this
enforces it.
- KEEP: Documented past defect (raw safe_load silently drops the private
overlay) on a credential-adjacent channel with seven live overlays. Grep for
yaml.safe_load against aii_config paths is cheap and low-FP.
- KEEP: Heuristic grep: yaml.safe_load co-occurring with aii_config path
literals outside the two canonical loaders. Won't catch path-via-variable
cases but fails loudly on the documented defect shape; incident-backed.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
aii_server/agent_abilities/_credentials/_bootstrap.py lines 27-31 carry the
quoted 'a raw ``yaml.safe_load`` of the public file silently discards the
private sibling' (claim said 26-31 — line 26 is blank). `find aii_config -name
'*.private.yaml' | wc -l` -> 7, including server.private.yaml and
pipeline/harness/agent_backend.private.yaml.
aii_server/dashboard/services/_runpod_provision/_compute.py:175 is exactly
`role_cfg = yaml.safe_load(role_path.read_text()) or {}` — exact cite — and
`find aii

Corrected statement of fact (2026-08-22 coordinates; every line number below
is historical — the live ones are in the hit table under "Mechanism"):
The cites are accurate but the violation set is understated, and that changes
the rule's allowlist. Same-hazard siblings:
aii_server/dashboard/api/__init__.py:376 raw-loads the SAME roles/<role>.yaml
(and :364 raw-loads user.yaml), so the compute-cap path is not the only door
onto that file; _compute.py:38 and :71 raw-load
`overlay_dir/pipeline/pipeline.yaml`, and a per-user `pipeline.private.yaml`
demonstrably exists in the tree
(aii_data/users/admin/aii_config.bak/pipeline/pipeline.private.yaml). Two of
the sweep's hits must NOT be routed through the overlay loader:
run_config/__init__.py:541 parses the user's pipeline.yaml inside an flock
read-modify-WRITE (merging an overlay there would write merged private values
back to the public file), and run_config/_bootstrap.py:139 reads a frontend
preset, the category load_yaml_cached's own docstring names as overlay-free.
_compute.py:25-29 also documents a deliberate lightweight read there. So the
allowlist needs the write-back path and the preset catalogue, not just
load_yaml_cached. Nothing is silently discarded today (no
roles/*.private.yaml).

OWNER-GATED (2026-08-25, ANSWERED 2026-09-03 — kept as the record of what was asked): the overlay population is gitignored, so any gate built today passes an empty population — fail-open. Needs a TRACKED declaration of which config files support a .private.yaml sibling before a mechanism can mean anything.

## Mechanism (built 2026-09-03)

`scripts/check_overlay_reads.py`, plus a TRACKED `allowlist.txt` beside it.
Exit 0 clean, 1 violated, 2 cannot run.

**The population problem is answered by the allowlist, not by the filesystem.**
The blocker recorded above is real and unchanged: the `.private.yaml` siblings
are gitignored, so any population derived from "which files have a sibling" is
empty on a fresh clone and passes everything. So the checker never looks for a
sibling. Its population is every TRACKED `*.py` under `aii_server/`, `aii_lib/`,
`aii_pipeline/`, `aii_runpod/`, `aii_launcher/`, `aii_accounts/` (any path with
a `tests/` segment skipped), narrowed to the modules whose source names
`aii_config` at all. That set is 55 modules (re-counted 2026-09-05; 56 when
this was written) and exists identically on a
fresh clone. The deliberate exceptions are declared in `allowlist.txt` — a
committed file, which is exactly what the overlays are not.

Discovery cannot fail open. Zero tracked modules under the roots, or zero
modules naming `aii_config`, is `exit 2` with a message, never a pass — and a
missing or reason-less `allowlist.txt` is `exit 2` too, since the exception
declaration IS the population here.

**What it flags.** Every AST call to `yaml.safe_load` / `yaml.load` /
`yaml.full_load` / `yaml.unsafe_load` inside a candidate. Resolution is by
BINDING, never by text: `import yaml as _yaml` and `from yaml import safe_load`
both bind, and `import yaml as _yaml` is the form four of the real call sites
use — a checker matching the literal `yaml.` would have seen none of them.
Function-local imports count, because most of these sites import inside the
body.

**Entries must stay LIVE.** An allowlisted module holding no raw load is
reported as a stale entry and fails, so the exception list shrinks as call
sites are rerouted instead of outliving its reason. A reason comment is
mandatory on every line.

### The hit table, and what was done with each

**Coordinates re-measured 2026-09-05; the ones this table carried were the
pre-reroute lines and none of them resolved any more.** Every entry below now
names today's call site, and every entry that names none is out of the
checker's population on purpose.

Five sites were rerouted; five stayed raw and are the five lines
`allowlist.txt` holds today. (`_deploy_flow.py` left it on 2026-09-04 when its
raw load moved into the already-listed `_remote/_common.py`.) The MEASURED
section above said "0 live defects" against a looser detection shape; the AST
sweep finds five raw reads that a door should own, four of which the earlier
verification note had already named.

- **`dashboard/api/__init__.py`** — read: shipped + per-user
  `user.yaml`; action: → `load_config_with_overrides`, now at :411
  (import :386, comment :407)
- **`dashboard/api/__init__.py`** — read: `roles/<role>.yaml`;
  action: → `load_config_with_overrides`, now at :428
- **`api/run_config/_bootstrap.py`** — read:
  `frontend/presets/<p>.yaml`; action: → `load_yaml_cached`, now at :149
  (import :36, comment :144)
- **`_runpod_provision/_compute.py`** (compute floor) — read: overlay
  `pipeline/pipeline.yaml`; action: → `load_config_with_overrides`, now
  at :45
- **`_runpod_provision/_compute.py`** (compute tier) — read: overlay
  `pipeline/pipeline.yaml`; action: → `load_config_with_overrides`, now
  at :81
- **`utils/config_overrides.py`** — read: both doors' own parsing;
  action: allowlist — it IS the door
- **`free_router/keys.py`** — read: `free_router_keys.private.yaml`;
  action: allowlist — the private file is the store; no public sibling
  to merge onto
- **`claude_oauth/cred_manager_client.py`** — read:
  `~/.claude-remote/config.yaml`; action: allowlist — outside the
  `aii_config` tree and outside the convention
- **`_remote/_common.py:230,250,273`** — read: shipped config BYTES;
  action: allowlist — parse-mutate-serialize to pin template images
  and to carry the deploy's exec-mode override. The third call site
  arrived 2026-09-04, when `_deploy_flow.py`'s own raw load moved here
  as `_mutate_execute_env_mode`; that entry left the allowlist the same
  day, the checker having reported it stale.
- **`_remote/_deploy_flow.py`** — no longer a raw reader (2026-09-04).
  It byte-edited `execute_env.yaml`'s `mode` before tarring, which was
  the wrong LAYER as well as a second door: the tar ships
  `execute_env.private.yaml` too and the pod merges it on top, so the
  override was discarded. Both halves are fixed — the mutation targets
  the private sibling and goes through `_common`'s helper.
- **`api/run_config/__init__.py:603`** — read: user `pipeline.yaml`
  under `flock` (:602); action: NONE NEEDED — read-modify-WRITE, so a
  merged overlay would be written back into the public file, but the
  module never names `aii_config` and is therefore outside the
  checker's population entirely. It is NOT in `allowlist.txt`, and
  adding it would be reported as a stale entry.
- **`services/runpod_provision.py:152,153,166`** — read: canonical +
  sparse user overlay into the tar; action: allowlist — same shape as
  `_remote/_common.py`; the `.private.yaml` siblings ship separately
  and merge on the pod

The two `roles/` reads matter most. `_runpod_provision/_compute.py:199` already
reads `roles/regular.yaml` through the door and says so in a comment naming the
hazard; `dashboard/api/__init__.py` read the SAME family raw. Two readers of one
file disagreeing about whether the overlay applies is the drift the rule exists
to prevent, and that is now closed rather than argued about.

`_compute.py`'s two overlay reads are the second parity fix. `PipelineConfig.
from_yaml`, in `aii_pipeline/src/aii_pipeline/utils/pipeline_config.py` (:262,
with the `pipeline.yaml` layer loop at :318-323), reads that exact per-user
`pipeline/pipeline.yaml` through `load_config_with_overrides` at :322, so a
`pipeline.private.yaml` sibling is part of the layer the pod ends up running.
The compute-floor and compute-tier reads were resolving a different config from
the one in force. Their docstrings' stated reason — do not pay for the full
typed stack here — is untouched: the door is one extra `stat` and is memoized.

The preset read went to `load_yaml_cached`, not to the overlay door, on the
loader's own documented grounds: the preset catalogue is the category
`load_yaml_cached` exists for, `api/run_config/__init__.py:134` already reads
those same four files through it, and its cache is keyed on `(mtime_ns, size)`
so a preset edited in local dev is re-read on the next request. It hands back a
deep copy, so the `pop` of cosmetic keys beside it cannot reach the memo.

### Probe

`pytest .../rule-config-overlay-one-door -q` → **6 passed**
(`test_a_raw_config_read_cannot_slip_past_the_door.py`). It runs the checker on
the real tree (exit 0) and, in synthetic `tmp_path` checkouts: a raw
`yaml.safe_load` in a candidate → exit 1 at the right line; the `import yaml as
_yaml` alias form → exit 1; the same read through the door → exit 0; an
allowlisted module → exit 0 while a stale entry → exit 1; and a population with
no candidate → **exit 2**, which is the fail-open case this rule was parked on.

Engine invocation, `RULES_MODE=all`, on the live tree: **exit 0**, re-run
2026-09-05 over **55** candidate modules with **5** declared exceptions, and
the probe suite re-run the same day still reports **6 passed**.
`ruff check` / `ruff format` clean on every file touched; the four rerouted modules' unit-test groups
(`rule-server-account-bootstrap`, `rule-server-compute-tiers-caps`,
`rule-server-handler-async-offload`, `rule-server-run-access-gate`,
`rule-server-run-config-api`, `rule-server-start-admission`,
`rule-run-start-inputs/test_config_overrides_cache.py`) → **292 passed**.

The OWNER-GATED note above is answered on its own terms — the tracked
declaration it asked for exists, as `allowlist.txt` — and the promotion it
left to the owner has happened: this rule lives under `rules/` and enforces on
every commit that stages a `*.py` or the allowlist itself. The note is kept
because the fail-open argument is the reason the mechanism has the shape it
has, not because the gate is still pending.
