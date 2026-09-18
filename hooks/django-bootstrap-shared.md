<!-- hook: django-bootstrap-shared -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Re-homed 2026-09-15: this hook now runs as a research-monorepo consumer check,
> discovered by `research-monorepo-ast-checks` (`dispatch.py`) over the consumer's own
> `tests/unit/<group>/test_*.py`, not this repo's own vendored (and
> since-deleted) copy of that tree. See "Re-homed to research-monorepo" below.
>
> Migration notes: condition had extra logic not mapped: 'engine-' runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# No test module hand-rolls Django bootstrap — django.setup()/sys.path surgery lives only in the shared tests/server/conftest.py, re-exported per group.

33 rule-tree test modules call django.setup() inline (measured), 32 via a
copy-pasted _configure_django that does mkdtemp + os.environ.setdefault +
sys.path.append + django.setup at import time (e.g. rule-server-orch-
provisioning/test_orch_template_resolution.py:25-38). The canonical bootstrap
already exists at tests/server/conftest.py:26-37, and 27 rule-dir conftests
already consume it as a one-line re-export (17 byte-identical copies of 'from
tests.server.conftest import *', 10 of a DBOS-prewarming variant —
md5-verified). The inline copies leak one un-cleaned mkdtemp dir per module
per run (37 mkdtemp/TemporaryDirectory sites measured) and repeat
sys.path.append 32 times against the user-level 'no sys.path.append' rule.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: tests-quality)

Proposed command (implemented at approval):

    rules-grep 'django\.setup\(\)|_configure_django' -- '.claude/skills/amg-hooks/research-monorepo/unit-tests/**/test_*.py'

Delete-check: YES — the rule enforces a deletion: the 32 _configure_django bodies are
removable today because the shared conftest re-export pattern already works in
27 sibling groups. Zero functionality loss; the mkdtemp leak and the import-
order fragility go with them.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: 32 copy-pasted import-time bootstrap bodies deletable today because
the shared conftest re-export already works in 27 siblings; delete then
enforce no inline django.setup outside the shared conftest.
- KEEP: 32 copy-pasted import-time bootstrap bodies where the shared conftest
re-export already works in 27 siblings — deletable today. Collapse, then a
grep for inline django.setup() outside the shared conftest.
- KEEP: Grep django.setup()/sys.path surgery outside the shared conftest,
after migrating the 32 copy-pasted _configure_django bodies (pattern already
proven in 27 siblings). Literal ban, loud.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
`grep -rln 'django.setup()' rules --include=test_*.py | wc -l` -> 33;
`_configure_django` -> 32. Cited example exact:
test_orch_template_resolution.py has `def _configure_django()` at line 25,
mkdtemp 28, sys.path.append 33, django.setup() 35, call at 38.
tests/server/conftest.py: sys.path.append 26-27, `_configure_django` 30-37,
call 40. md5 of all 31 rule-dir conftests: 17 share e52f4510, 10 share
3cdcd206, giving exactly 27 that carry `from tests.server.conftest import *`
(grep -rl confirms 2

Corrected statement of fact:
Every count in the proposal (33 / 32 / 27 / 17 / 10 / 37 / 32) is exact, as
are both line citations. The rationale is measurably backwards. The early `if
settings.configured: return` in all 32 copies means Django's one-shot
configure lets only the FIRST module in a process reach mkdtemp, so the leak
is one dir per process (per xdist worker), not 'one per module per run'. On
disk the inline copies account for 39 of 10,005 stale dirs; 9,966 come from
the two SHARED conftests the proposal wants everything consolidated onto — so
consolidation would not reduce the leak. Second correction: the canonical
bootstrap is not a drop-in, because it configures config.settings_light while
all 32 copies configure config.settings (the copies then pytest.skip when the
dashboard app is absent). A live defect does exist and is worth fixing
regardless of this rule, but it is in tests/server/conftest.py:34 and
aii_server/tests/conftest.py:33 — an un-cleaned tempfile.mkdtemp that has
accumulated 9,966 directories in /tmp.

## Collapsed 2026-09-03

The deletion this rule describes is done: 35 modules across 17 rule dirs no
longer bootstrap Django, and the whole `unit-tests` tree greps clean for
`django.setup()` / `_configure_django`. Two rule dirs had no conftest and got
one, byte-identical to the 17 siblings already carrying the plain shape.

Test counts, the 17 touched dirs, before and after: **863 passed, 0 failed,
0 skipped** each time — same tests, same verdicts, 20 fewer lines per module.

**Probes, both ways (2026-09-03).** `rules-grep --tree` greps the WORKING
tree, so the clean side is today's tree: the wired command exits **0** with no
output. The biting side is the same ERE and the same pathspec against the
content this change deleted — `git grep -nE 'django\.setup\(\)|
_configure_django' HEAD -- '<the pathspec>'` prints **103 lines across 35
files**. Same pattern, same pathspec, both verdicts, no staging required.

The `command` is double-quoted YAML, so its backslashes are doubled in the
file: 6 in the line, **3 in the value the engine's own parser returns**
(`rules.py::_parse_frontmatter`), and the shell receives
`django\.setup\(\)|_configure_django`. Checked through that parser rather
than through `yaml.safe_load` — the engine's is hand-rolled, and clause 5 of
`rule-pending-tree-approval-ready` exists because the two can disagree.

The description carried a `PENDING owner approval` prefix while the rule sat
in `rules-pending/`: clause 4 of that same rule requires the marker on every
parked rule and forbids it on every enforced one, so the prefix came off as
part of the approval `git mv` on 2026-09-03, not before it.

What the codes mean:

- **B** — the `_configure_django` body and its module-level call, plus the
  imports only it used (`os`, `sys`, `tempfile`, `pathlib.Path`, `django`,
  and `django.conf.settings` where no skip guard still reads it).
- **F** — an in-test `settings.configure()` + `django.setup()` fallback,
  guarded on `settings.configured` and already dead behind the conftest.
- **T** — `Path` survived only inside annotations, so it moved under
  `if TYPE_CHECKING:` (ruff TC003; `from __future__ import annotations` is
  already present in every one of them).
- **H** — the module's trailing import block moved above `pytestmark`. Only
  where NOTHING separated the two blocks once the bootstrap call went: a
  module-level `pytest.skip` guard is the one reason a `dashboard.` import
  must stay below, and every module carrying one keeps its split.

Conftest shapes: **re** = `from tests.server.conftest import *`; **re+D** =
that plus the DBOS `safety_net` pre-warm; **re\*** = the plain shape, created
by this change.

| module (`test_….py`) | cut | cf |
|---|---|---|
| **rule-claude-account-rotation** | | re\* |
| account_switch_scenarios | B+T | |
| audit_credentials_switch | B | |
| claude_session_bucket_endpoint | B+T | |
| credentials_manager_mode | B+T | |
| credentials_usage_cache | B | |
| the_usage_poll_stops_before_autologin_finishes | B | |
| **rule-server-account-bootstrap** | | re |
| email_link_logging | B+T | |
| staff_bootstrap | F | |
| **rule-server-account-deletion-scrub** | | re |
| delete_flat_run_dir | B | |
| **rule-server-api-auth-surface** | | re |
| api_auth_callable | B | |
| contact_endpoint | B | |
| contact_throttle_ident_is_not_caller_controlled | B | |
| **rule-server-backend-capacity** | | re\* |
| backend_capacity | B | |
| **rule-server-compute-tiers-caps** | | re |
| compute_floors | B+T | |
| **rule-server-cost-cache** | | re |
| runs_cost_offloads_compute | B+H | |
| **rule-server-fork-lineage** | | re+D |
| run_fork_dispatch | B | |
| run_lineage | B+H | |
| **rule-server-handler-async-offload** | | re |
| abilities_handlers_are_async | B+H | |
| network_handlers_offload | B+H | |
| run_files_endpoints | B+T | |
| **rule-server-orch-provisioning** | | re+D |
| orch_template_resolution | B | |
| runpod_provision | B | |
| runpod_provision_fork | B | |
| **rule-server-run-access-gate** | | re+D |
| provisioning_window_access | B | |
| require_run_access_cross_user | B | |
| run_id_shape | B | |
| **rule-server-run-config-api** | | re |
| openrouter_catalog_cache | B+H | |
| run_config_permission_modes | B | |
| run_config_presets_wire | B | |
| **rule-server-run-metadata** | | re |
| run_rename_title | B | |
| submit_review_score_bounds | B | |
| **rule-server-share-read-only** | | re |
| share_gate_read_only | B | |
| **rule-server-staging-uploads** | | re |
| staging_handlers_are_async | B+T+H | |
| **rule-server-start-admission** | | re+D |
| run_start_user_isolation | B+T | |
| **rule-server-stop-teardown** | | re+D |
| reap_run_pods | B | |

### What was KEPT, and why

**The `DJANGO_SETTINGS_MODULE` difference is not a difference.** Every
deleted copy named `config.settings` while the shared bootstrap names
`config.settings_light`, which reads like a behaviour change and is not one:
both call sites use `os.environ.setdefault`, Django's configure is one-shot
per process, and every one of these modules already ran under
`settings_light` — `aii_server/tests/conftest.py` is a `testpaths` entry, so
pytest imports it at startup in every worker and it wins the race. The
copies' `config.settings` had no reachable effect in any invocation shape
this suite supports. `settings_light` republishes `settings`, and the root
`conftest.py` pins `AII_WEB_APP_MODE=1`, so the `dashboard` app is present
either way.

**Every `if "dashboard" not in INSTALLED_APPS: pytest.skip(...)` guard
stays.** It is a capability check, not bootstrap, and it is what keeps a
`dashboard.` import below the guard rather than in the top block. The rule's
grep does not match it.

**No module needed a deliberately different bootstrap.** All 32 copies were
the same 12 lines with a different `mkdtemp` prefix; `staff_bootstrap`'s was
the same idea inlined in one test. Nothing was left behind as an exception.

### The leak this does NOT fix

The 2026-08-22 verification above is right, and it stays right: the
un-cleaned `tempfile.mkdtemp` is in the two SHARED conftests
(`tests/server/conftest.py:34`, `aii_server/tests/conftest.py:33`), which
accounted for 9,966 of 10,005 stale dirs against the inline copies' 39.
Consolidating onto the shared bootstrap moves those 39 onto the shared
path; it does not remove them. That defect is real, separate, and untouched
here — fixing it belongs in the shared conftest, where one fix covers every
consumer, which is the whole argument for having one door.

## Ported to the AST dispatcher — grep prefilter + AST confirm (2026-09-14)

ADDITIVE and INERT. `dispatch.py` sits BESIDE the regex line that is still
wired; nothing runs it yet. The merge owner swaps the `run:` line later —
it is written out below, deliberately not applied here, because
`amg-hooks/lefthook.yml` has one writer and this is not it.

Three files, the shape every landed port carries: `dispatch.py` (the
check), `scripts/run_static_check.py` (a thin per-hook entry, because the
one-pass dispatcher has no single-hook mode and nothing wires it in the
`self` set yet), and `test_django_bootstrap_shared_bites.py` (25 tests).

**The candidate source is the live ERE, and only the live ERE.**
`_CANDIDATE` is `django\.setup\(\)|_configure_django` translated to Python
`re` — every term is a literal, an escaped `.`/`(`/`)`, or `|`, so the two
spellings are character-identical. It is unanchored, so it is matched with
`re.search` one physical line at a time, the way `git grep` does. The AST
step only FILTERS that set. `_CANDIDATE` and `PATHSPEC` are not retyped in
the test: it parses the `run:` line out of `amg-hooks/lefthook.yml` and asserts
both against it, so widening the ERE without widening the port turns the
suite red instead of leaving the port checking something else.

**What the AST confirms.** Two shapes, both requiring real parsed code:

- `django.setup()` — a `Call` whose func is `Attribute(attr="setup")` on
  `Name(id="django")`. Arity is deliberately unchecked: the regex already
  pinned the empty-parens spelling textually.
- `_configure_django` — the identifier bound or referenced as code, in any
  spelling a hand-rolled bootstrap uses: the `def`, a bare call (`Name`), a
  method (`Attribute`), an `import` alias, a parameter, a keyword name, a
  `global`/`nonlocal`, an `except … as`, a class.

Each contributes the physical line its NAME TOKEN sits on — `node.lineno`
everywhere, `end_lineno` for an `Attribute`, whose `attr` is its last
token. A `FunctionDef`'s `end_lineno` spans the whole body and is NOT
used; it would re-admit every comment inside the function.

**The false positives it removes.** Both ERE alternatives are plain
substring matches with no word boundary, so the bare grep also flags:

- the call or the name in a `#` comment;
- either quoted in a string literal or a docstring — this is the live
  shape, and the only candidate anywhere in this repo's tracked `*.py` is
  `research-monorepo/hooks/security-headers-parity/scripts/check_header_parity.py`
  line 25, a module docstring saying "through ``django.setup()``";
- a lookalike NAME containing the token, on either side — `mydjango.setup()`
  is not the `django` module's `setup`, `my_configure_django` is not the
  banned bootstrap, and neither is `_configure_django_lines`, which this
  port's own source carries and which a leading-side-only reading misses.

**An ALIASED import is not a lookalike, and reading it as one was a false
negative.** `import django as mydjango` binds that name to the module, so
`mydjango.setup()` IS the bootstrap and the live regex reports it. The port
dropped it until 2026-09-14, because it compared the receiver `Name` to the
literal `"django"`; it now asks `astcheck.module_aliases(tree, "django")`
for every local name bound to the module. The lookalike row above still
holds for the shape it describes — `mydjango` bound to nothing, which is the
fixture this hook's tests pin — and `test_an_aliased_django_import_still_bites.py`
pins both directions so the two can never be confused again.

No separate `tokenize` pass is needed for the comment class: the parser
emits no node for comment or string bytes, so walking the AST for the two
real shapes excludes all of them for free. `tokenize` is used in the TEST
instead, as an independent classifier for the drop-set audit — blanking
the comment and string spans and re-running the ERE answers "was the match
only text?" without asking the code under test.

**Fail CLOSED.** An unparseable file cannot be walked, so its candidate
lines keep the regex verdict. A syntax error must not become a hole in the
ban, and `test_an_unparseable_candidate_file_is_reported` pins it.

### Drop-set audit (2026-09-14, this repo's index)

OLD is the live wired command — `git grep --cached -nE` with the same ERE
and pathspec. NEW is the dispatch run whole-tree (`AMG_HOOKS_SWEEP=1`) through
the shim. **ADDED is 0 in both populations**, which is the whole ratchet
argument: findings ⊆ candidates by construction, so the cutover can only
ever drop sites.

| population | files | OLD | NEW | DROPS | ADDED |
|---|---|---|---|---|---|
| the pathspec | 699 | 0 | 0 | 0 | **0** |
| all `*.py`, pre-port | 1208 | 1 | 0 | 1 | **0** |
| all `*.py`, this port in | 1211 | 58 | 0 | 58 | **0** |

The pathspec row is 0/0 because the 2026-09-03 collapse above left the
tree clean — that zero stock is exactly what earns the `--tree` lane, and
it is also why the audit is widened past the hook's own pathspec: without
the wider rows the FP class would have no live population to act on. The
one pre-port drop is `check_header_parity.py:25`, classified independently
by `tokenize` as a docstring; the 57 that arrive with this folder are its
own prose and fixtures, every one text-only or a lookalike. That third
figure moves with any prose edit here, which is why the test asserts
ADDED == 0 and classifies every drop rather than pinning a count.

Both halves of that widening were found by MEASURING rather than reading.
Staging the new files first is what produced those — an unstaged `git
grep --cached` cannot see them — and the third lookalike class
(`_configure_django_lines`, the token as a PREFIX) showed up only there,
as an unexplained drop that turned the audit red until the classifier
grew its trailing-side arm.

Every row is asserted by a test, so they stay true rather than staying
written down. Whole-index cost measured over three runs: 0.81 / 0.86 /
0.92 s, against a 5 s budget.

### Re-homed to research-monorepo (2026-09-15) — the cutover already applied

This hook used to live in the `self` set and police this repo's OWN vendored
copy of the research-monorepo unit tests, at `*/unit-tests/*/test_*.py` — a corpus
`b523c8aa` permanently deleted. The real tests were never gone, only never
checked from here: they live in the CONSUMER repo's own tree, at
`tests/unit/<group>/test_*.py`. This hook (and its sibling
`unit-test-docstring-present`) therefore moved to `research-monorepo/hooks/`, and
`self-ast-checks` — the `amg-hooks/lefthook.yml` command that used to discover
both — was removed, since it would otherwise own zero folders.

No new `research-monorepo/lefthook.yml` line was needed: `research-monorepo-ast-checks`
already discovers every `dispatch.py`-owned folder under `research-monorepo/hooks`
in one pass (`ast_dispatch.py {amg_hooks}/research-monorepo/hooks {staged_files}`),
so landing this hook's folder there was the whole cutover. `dispatch.py`'s
`PATHSPEC` and `GLOBS` moved from `*/unit-tests/*/test_*.py` to
`tests/unit/*/test_*.py`, and its vacuity floor was restored: an empty
population raises `CannotRunError` again rather than returning clean, exactly
as every sibling AST check's "no Python files scanned"-shaped floor does.

To run this hook ALONE (for the drop-set audit, or by hand), the shim in
`scripts/run_static_check.py` is still the entry point — `ast_dispatch.py`
has no single-hook mode.

Mode stays TREE and stays INTERNAL to `dispatch.py` — it ignores
`svc.sweeping` and judges the whole index. `run()` rebuilds its population
from `svc.tracked` regardless of `{staged_files}`, so the staged list only
gates whether the hook fires, never what it scans.
