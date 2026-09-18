| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 2s | self-gate |

# A unit-test group triggers on every consumer file its tests read as source

A group under `<set>/unit-tests/<group>/` runs at commit when a staged path
matches one of its `paths.txt` globs (`lib/amg_hooks/run_groups.py`). A test that reads
a consumer module's TEXT — `inspect.getsource`, `mod.__file__`, a
`ROOT / "a" / "b"` literal, a script named in a subprocess argv — is a function
of that file's exact bytes, so the day the file changes is the day the test has
an opinion about it. When no glob names that file, the group is not selected
that day, and the lane prints the groups it ran rather than the ones a staged
path used to select. The other groups whose globs are directory-wide keep
firing, so the run looks entirely normal.

## Measured

`research-monorepo/unit-tests` against the consumer's 2049 tracked paths, 2026-09-14:
108 live groups, 707 test modules, **14 groups reading 23 consumer paths their
own globs miss**.

| group | paths | the one that matters |
|---|---|---|
| `capacity-holds-pause-and-resume` | 4 | `_agent/_run.py` |
| `ci-coverage-parity` | 3 | `pytest.ini` |
| `server-stop-teardown` | 3 | `workflows/_phases.py` |
| `cost-accounting` | 2 | `concept_fig_gen.py` |
| `viz-figure-pipeline` | 2 | `aii-paper-to-latex/SKILL.md` |
| `docker-image-guards` | 1 | `aii_pipeline/…/prompts` |
| `free-router-endpoint-selection` | 1 | `dump_presets_fixture.py` |
| `lint-gates-actually-bite` | 1 | `aii-data-fig-gen/scripts` |
| `openapi-snapshot-integrity` | 1 | `aii_lib/…/__init__.py` |
| `openhands-backend` | 1 | `_agent/_run.py` |
| `pod-logs-survive-teardown` | 1 | `runpod/race_barrier.sh` |
| `public-sync-invariants` | 1 | `aii_config` |
| `runpod-api-failsafe` | 1 | `aii-runpod/scripts` |
| `server-account-bootstrap` | 1 | `aii_server.py` |

Three worth stating in full, because each is a guard that stops running on
exactly the commit it exists for:

* `server-stop-teardown` asserts on `_phases.__file__`, `_hypo_loop_iter` and
  `_invention_loop_iter` while carrying no `aii_pipeline` glob at all — 13
  globs, every one of them under `aii_server` or `aii_runpod`.
* `capacity-holds-pause-and-resume` runs `inspect.getsource(RunMixin.run)` over
  `terminal_claude_agent/_agent/_run.py` and triggers on `_helpers.py` and
  `_capacity.py`, its two siblings in the same split package.
* `ci-coverage-parity` collects `pytest.ini` to prove marker strictness, and
  triggers on `pyproject.toml`, `conftest.py` and `lefthook.yml`.

## The rule: source text, and nothing weaker

A dependency counts when the group's own `.py` files reach the consumer path by
one of four routes, each of which makes the target's BYTES part of an assertion:

| route | shape |
|---|---|
| module source | `inspect.getsource(x)`, `x.__file__` |
| literal path | `ROOT / "a" / "b"`, `Path("a/b")` |
| argv | a consumer path inside a `subprocess` call |
| fixed helper | `_frontend_src`, `_deploy_src`, `source_probe` |

**An import and an attribute patch are deliberately NOT flagged**, and that is
the whole of why this is shippable. A test that does
`patch("aii_lib.run.emit._emit")` or `monkeypatch.setattr(mod, "X", ...)` is
usually stubbing a module out precisely so it is NOT exercised:
`ci-watcher-honesty` patches `load_dbos_config` to keep a real config load out
of the way, and nothing about that module's content is under test. Measured on
the same tree, the wider rules cost far more than they find:

| rule | uncovered pairs | groups failing |
|---|---|---|
| every import counts | 292 | 82 of 107 |
| source text or patched | 86 | 46 of 107 |
| **source text only** | **23** | **14 of 108** |

Only the third is a red gate anyone can adopt, and it is the half that matches
the incident class exactly: a test that reads a module's text is green while
that module changes, because its group never ran.

## How this differs from `trigger-globs-survive-a-split`

Adjacent fault, opposite half of the same sentence. That hook asks whether a
glob still REACHES the module it names after the consumer splits it into a
sibling `_<stem>/` package — the target moved, the glob did not. This one asks
whether the module is in the globs AT ALL. A group can pass either and fail the
other: `server-stop-teardown`'s `aii_runpod/…/pod_infra/**` survives every
split and has never named `aii_pipeline`; a `runs_sidebar.py` glob names its
module exactly and stops reaching it the day it becomes `_runs_sidebar/`.

They also compose rather than overlap, because coverage here is decided with
`run_groups.load_groups`, which already carries the split form — so a glob that
names `foo.py` counts as covering `_foo/_part.py`, and this hook never asks for
a second glob that the other hook exists to make unnecessary.

## Mechanism

`check.py`, standalone, stdlib only — not a `dispatch.py`: the AST dispatcher
exists to share ONE parse of the staged file, and the files parsed here are the
group's tests, which are the subject rather than the staged path.

* the consumer is asked of git (`--show-superproject-working-tree`, then
  `--show-toplevel`), never counted off `__file__`, and a bare checkout of this
  repo is refused rather than judged: exit 2, with `cannot run:`;
* its population is `git ls-files` in the consumer — what a commit can STAGE,
  which is what a trigger glob is matched against. Gitlinks are kept: a
  submodule pointer bump stages the gitlink path, and `ci-coverage-parity`
  genuinely reads `.claude/skills/amg-hooks`;
* dependencies are `ast.parse` over the group's `*.py`, with no consumer
  import and no venv — the import table resolves a local name to a dotted
  module, and a package read through `__file__` resolves to its `__init__.py`
  rather than to the 245 modules beneath it;
* coverage is `run_groups.select()`'s own predicate against the patterns
  `load_groups` compiled, so `**`, the basename fallback and the `_<stem>/`
  split form are the lane's and not a second copy of them. `select()` itself
  cannot be called: with no staged files, or under `AMG_HOOKS_SWEEP=1`, it returns
  EVERY group — which is the whole-set lane, where that would mark every
  dependency covered and make the hook green by construction.

Scope is `relation`: the subject is a `paths.txt` paired with the tests beside
it. At commit the population is the groups the staged paths name; under
`AMG_HOOKS_SWEEP=1` it is every group, `judged_paths` having dropped lefthook's argv
chunk, and `sweep_once` keeps the second chunk from repeating the work.

A dependency with nothing tracked under it is dropped before it can become a
finding — an ignored or generated tree can never be staged, so no glob could
cover it and the finding would have no fix.

Cost: 1.1 s for all 108 groups (707 modules, one `git ls-files`, no consumer
venv); 0.08 s for a commit that stages one group.

## Stock

**14 groups, 23 paths — the table above, and every one of them is a real
trigger gap rather than a heuristic.** They are cleared in the commit that
follows this one, each by the narrowest glob that reaches the path it reads,
so the hook wires with no `.amg-hooks-debt` line and nothing is adopted as debt. The
adoption list also lives in the test as a ratchet: a group flagged that is not
in it is a trigger that has gone blind since, and that fails whatever the
stock is doing.

## Wiring

Not yet wired — `lefthook.yml` has one writer. The entry belongs in the ROOT
`lefthook.yml` beside `no-pytest-config-in-this-repo`, whose shape it shares: a
relative path, this repo only. It must NOT go in `amg-hooks/lefthook.yml`, the
`{amg_hooks}`-templated set: a consumer extending that file would run this against its
own tree, where `{amg_hooks}` is the submodule and the group folders sit one level
further down.

```yaml
    # A unit-test group triggers on every consumer file its tests read as
    # source text — getsource, __file__, a literal path, a subprocess argv
    unit-test-paths-cover-their-sources:
      glob:
        - "*/unit-tests/*/paths.txt"
        - "*/unit-tests/*/test_*.py"
        - "*/unit-tests/*/conftest.py"
      run: 'sup=$(git rev-parse --show-superproject-working-tree); [ -n "$sup" ] || { echo "skipped: this hook judges the groups against a consumer checkout"; exit 0; }; python3 amg-hooks/hooks/unit-test-paths-cover-their-sources/check.py {staged_files}'
```

The superproject guard is the same one every hook-test command in that file
carries, and for the same reason: a bare clone of this repo has no consumer, so
the checker exits 2 there by design and would block every commit. Inside the
consumer's submodule — the only checkout where the subject exists — it runs.
Both `conftest.py` and `test_*.py` are globbed because the checker parses every
`*.py` in the group; `*/unit-tests/*/…` reaches every set, since `*` does not
cross `/` in lefthook 2.1.9 and the group is always exactly one level down.

## Fragility

| refactor | effect | guard |
|---|---|---|
| a fifth source-text route | missed | the four tables |
| `select()`'s predicate moves | drift | the parity test |
| a helper is renamed | missed | its target vanishes |
| the consumer is not found | exit 2 | `cannot run:` |

The parity test is the load-bearing one. The predicate here is one line of
`select()` copied because `select()` cannot be called, so it is exactly the
kind of duplicate that goes stale in silence; the test drives both over the
same patterns and the same paths.

The fixed-helper table is consumer-specific by nature — `tests/_frontend_src`
and `tests/aii_runpod/_deploy_src` are that consumer's helpers — and each entry
is dropped where its path does not exist, so the table is inert in a consumer
that has none of them. A renamed helper is a silent miss, which is the same
exposure `guards-ask-git-what-is-tracked` carries for its own recogniser list.

## Delete-check

The dimension is "a group's trigger and its tests' dependencies are written in
two places". It goes when a group's triggers are DERIVED from its tests rather
than declared beside them — at which point this hook is the derivation and the
`paths.txt` files are the redundant half.
