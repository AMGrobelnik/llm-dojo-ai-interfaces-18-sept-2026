<!-- hook: workflows-registered-eagerly -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every module defining a @DBOS.workflow is imported at module scope by run/workflows/__init__.py (pipeline.py excepted)

run/workflows/__init__.py:6-15 documents the invariant and its failure mode: a
workflow registered only on first lazy import can be enqueued before
registration and dequeue/crash-recovery raises DBOSWorkflowFunctionNotFound —
surfacing only at resume time, the worst moment. Decorator census (grep
'^@DBOS.workflow'): all 24 workflow definitions live in exactly the 7 modules
the __init__ imports (_phases.py, _invention_loop_modules.py,
_gen_paper_repo_modules.py, _hypo_loop_modules.py, _hypo_loop_iter.py,
_invention_loop_iter.py, _background/*) plus pipeline.py:309. The list is
complete today and maintained by hand; a new `_foo.py` workflow module that
skips the import breaks resumability of every run parked inside it, with zero
test failing.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: python-pipeline)

Proposed command (implemented at approval):

    python scripts/check_workflow_registration.py  # grep decorator modules, parse __init__ imports, diff

Proposed condition: `[ "$RULES_MODE" = all ] || git diff --cached --name-only -- aii_pipeline | grep -q .`


## IMPLEMENTED 2026-08-26 — `scripts/check_eager_registration.py`

    .venv/bin/python $RULE_DIR/scripts/check_eager_registration.py

Arrives green: 8 workflow modules in the package, every one reachable from the
7 names `__init__` imports.

**A PACKAGE IMPORT COVERS ITS MEMBERS, and missing that would report working
modules as broken.** `__init__` imports `_background` — the package — not
`_background.interim_summary` and `_background.per_msg_summary` individually.
Both define workflows; both are registered by that one name. A filename-against-
import-list comparison would flag two modules that are perfectly covered, which
is why the check resolves the top-level component of each module's path.

**Only MODULE-SCOPE imports count.** A `from . import _a` inside a function is
exactly the lazy registration this rule exists to prevent, so the walk reads
`tree.body` rather than `ast.walk`. Probed.

**The census is bigger than the body's, and the extra one is reported rather
than scoped away.** The body says the definitions live in the 7 imported
modules "plus pipeline.py:309". There is a tenth:
`aii_server/dashboard/services/safety_net.py`. It is not a defect — the server
process imports it eagerly from `dashboard/apps.py`, a different DBOS
registration path — but a checker that silently excluded everything outside the
package would also hide the next outsider that has no such path. It is recorded
by name with its registrar, and an UNRECORDED outsider fails. 2026-09-04 there is
a second one, `aii_server/dashboard/services/capacity_supervisor.py`, recorded the
same way — `dashboard/apps.py` calls its `install_capacity_sweep()` at boot,
before `DBOS.launch()`.

Probed six ways: a module missing from `__init__`, a function-local import, and
an unrecorded outsider all fire; a fully-imported package, a sub-package import
covering its members, and the recorded outsider do not.

Delete-check: Yes — the hand-maintained import list can be deleted in favor of a pkgutil
auto-import loop in __init__.py (nothing left to forget); the rule should
enforce that collapsed end-state, falling back to the diff check until the
refactor lands.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Workflow modules live across steps/, so a pkgutil auto-import of
run/workflows cannot fully delete the dimension; the decorator-census-vs-
import-list check is the honest closure of a resume-time-only failure
(DBOSWorkflowFunctionNotFound).
- KEEP: Failure mode surfaces only at resume time
(DBOSWorkflowFunctionNotFound) — the worst possible detection point. Decorator
census vs import list is a cheap deterministic check; the pkgutil auto-import
deletion is even better and the rule then pins that end-state.
- KEEP: Census @DBOS.workflow decorators vs import list (or assert the pkgutil
auto-import loop exists per its delete-check). Both forms deterministic; a
forgotten module fails loudly instead of at resume time.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **holds, counts stale**.

**The invariant is intact.** Every module defining a `@DBOS.workflow`
inside `aii_pipeline/.../run/workflows/` is imported at module scope —
including the two that are not named directly in the package
`__init__.py`. It imports `_background` as a subpackage (line 23), and
`_background/__init__.py:26-27` imports `interim_summary` and
`per_msg_summary`. The registration is transitive but eager, which is
what the rule requires.

**The counts have drifted since the proposal was written:**

| | claimed | today |
|---|---|---|
| `@DBOS.workflow` definitions | 24 | **27** |
| modules inside the package | 7 | **8** |

Two further modules define workflows outside the package —
`aii_pipeline/src/aii_pipeline/pipeline.py`, which this rule already excepts, and
`aii_server/dashboard/services/safety_net.py`, which belongs to a
different distribution and is registered by the server's own boot. An
implementation must scope itself to the workflows package or it will
report `safety_net.py` as unregistered forever.

**Method note, because the first pass got this wrong.** Checking whether
`__init__.py` mentions each module BY NAME reported `interim_summary` and
`per_msg_summary` as unimported, which would have been a live defect
report. They are reached through a subpackage. Any check written for this
rule has to resolve imports transitively — a text search of the top-level
`__init__.py` produces exactly this false positive, and the two modules
it would flag are the two that are hardest to argue are unregistered,
since the background summary workflows demonstrably run.

## THE HARD-CODED TABLE IS GONE — 2026-09-10

The section above records the two outsiders as "listed as out-of-scope with
their registrar named". That listing was an `ELSEWHERE` dict of literal paths,
and it is deleted. It had a defect the entries themselves hide: **the only way
to satisfy it was to edit this hook.** A third module registered EXACTLY the
way those two are — imported by `dashboard/apps.py` at boot — failed until a
human added its path, so the gate taught people that the way past a gate is to
edit the gate. The two entries were right about the tree and wrong about who
should be writing them down.

**The convention that replaced it.** An out-of-package workflow module is
covered iff an EAGER REGISTRATION ROOT imports it. That is the same
justification both entries already rested on, read off the code instead of
retyped: `apps.py:395` is `from .services import safety_net`, `apps.py:412` is
`from .services.capacity_supervisor import install_capacity_sweep`, and both
sit inside `DashboardConfig.ready()`.

**Why `aii_server/dashboard/apps.py` is the right root, and the only one.**
Django calls `AppConfig.ready()` once per process at boot, and this one calls
`init_dbos()` itself — the registration has to happen beside it, before
`DBOS.launch()`, which is precisely why the imports are there. `EAGER_ROOTS`
is a claim about WHEN code runs, the one thing a checker cannot read off a
tree, so it stays a short list where each entry earns itself. Everything
downstream of it is derived.

**What the walk is.** Module scope plus every `ready()` body, then everything
those reach BY NAME, transitively — not "every import in apps.py". A helper
nothing calls at boot runs at no particular time, and an import inside it is
the late registration this rule exists to catch. By NAME rather than by call
because `start_catalogue_refresh()` hands `_refresh_catalogues_loop` to a
`Thread` as a value: a call-following closure stops one hop short of its
imports. Both readings of a dotted prefix are resolved, since
`from .services import safety_net` names a MODULE while
`from .services.capacity_supervisor import x` names a symbol inside one.

Absolute imports are not resolved. This repo is src-layout, so `aii_lib.dbos_app`
is not a path, and resolving one would need the installed venv. That is the
conservative direction: an import the walk cannot read leaves its module
REPORTED, never silently passed.

**Re-measured 2026-09-10**, on the tree as it stands:

| where | n | covered by |
|---|---|---|
| in `run/workflows/` | 8 | the 7 names `__init__` imports |
| `pipeline.py` | 1 | `EXCEPTED` — an entry module |
| `safety_net.py` | 1 | `apps.py` `ready()`, :395 |
| `capacity_supervisor.py` | 1 | `apps.py` `ready()`, :412 |

11 modules define a `@DBOS.workflow`; the eager walk over `apps.py` resolves
to **18** dashboard modules, which is the population the last two are found
in. `EXCEPTED` survives the deletion and is now the only hand-written path:
`pipeline.py` is an entry module rather than a package member, and no import
graph can tell you that.

**The vacuity bails, all kept, one added.** A checker whose registrar
detection has broken must not become "everything is fine":

| bail | what it catches |
|---|---|
| `__init__` missing or unparsed | the registration point moved |
| eager root missing or unparsed | `apps.py` moved |
| under 8 modules from the walk | the walk broke |
| no `@DBOS.workflow` at all | an empty census |
| under 4 modules in the package | the tree moved |

The last two fire only on an otherwise CLEAN result — findings outrank them.
The eager-walk floor is the opposite and fires first: a walk that shrank
poisons the findings themselves, reporting innocent outsiders and burying any
real one among them.

**Probed by `test_eager_registration_bites.py`, 17 tests.** The first two are
the defect reproduced — a synthetic outsider in each import shape, which
failed against the dict with "is not recorded as having its own registrar" and
passes against the convention. The rest hold the line the dict held: an
outsider no root reaches is reported, an import in an uncalled helper is not
eager, a helper reached by value is, the in-package half still bites (missing
name, function-local import), a sub-package import still covers its members,
and each bail fires. Nothing in the test file names a real module path.
